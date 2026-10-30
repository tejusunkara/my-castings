"""Rule-based role matching against the artist profile.

Each criterion answers one question (does the age fit? the gender? the location?).
A role matches when every criterion passes; the per-criterion answers are stored as
saved_matches.match_reasons so the dashboard can show why something matched.

Missing profile data fails a criterion rather than passing it. Non-matching roles get
no saved_matches row and are re-evaluated on every sweep, so they'll match once the
profile is filled in; passing instead would mint permanent 'new' matches for everything.
Missing *role* data means the posting didn't restrict it, so that passes.

Extending to weighted scoring later: give criteria a score() and swap the all() in
evaluate_role() for a threshold. The MatchCriterion interface doesn't change.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.models import ArtistProfile, Role
from ingestion_core.parsing.text_normalize import gender_key

# Seeking-location values that mean "anywhere".
OPEN_LOCATIONS = {"worldwide", "nationwide", "anywhere", "remote", "united states", "usa"}

# City spellings that refer to the same place, keyed by the canonical name.
CITY_ALIASES = {
    "new york": {
        "new york city",
        "nyc",
        "manhattan",
        "brooklyn",
        "queens",
        "bronx",
        "the bronx",
        "staten island",
    },
    "los angeles": {"la", "hollywood"},
}
_CANONICAL_CITY = {alias: city for city, aliases in CITY_ALIASES.items() for alias in aliases}


@dataclass(frozen=True)
class MatchResult:
    is_match: bool
    reasons: dict[str, bool]


class MatchCriterion(Protocol):
    key: str

    def evaluate(self, role: Role, profile: ArtistProfile) -> bool: ...


class AgeCriterion:
    """The role's age range overlaps the artist's playing range (both inclusive).

    Casting ranges describe the ages a character reads as, so overlap is the test, not
    "real age inside the range": playing 16-30 fits an 18-24 role and an 18+ role.
    """

    key = "age"

    def evaluate(self, role: Role, profile: ArtistProfile) -> bool:
        if role.age_min is None and role.age_max is None:
            return True
        if profile.playing_age_min is None or profile.playing_age_max is None:
            return False
        if role.age_min is not None and role.age_min > profile.playing_age_max:
            return False
        return role.age_max is None or role.age_max >= profile.playing_age_min


class GenderCriterion:
    """Any of the profile's gender labels is among the role's; a role listing none (or
    "All Genders") is open to all. A profile label like "any gender" therefore matches
    exactly the open roles, which pass anyway."""

    key = "gender"

    def evaluate(self, role: Role, profile: ArtistProfile) -> bool:
        if not role.genders:
            return True
        wanted = {gender_key(g) for g in profile.genders}
        return not wanted.isdisjoint(gender_key(g) for g in role.genders)


class LocationCriterion:
    """Any seeking location is the profile's city (same state), or the artist travels."""

    key = "location"

    def evaluate(self, role: Role, profile: ArtistProfile) -> bool:
        locations = role.casting_call.seeking_locations
        if not locations or profile.willing_to_travel:
            return True
        if not (profile.location_city and profile.location_state):
            return False
        home = (canonical_city(profile.location_city), profile.location_state.strip().upper())
        return any(location_matches(loc, home) for loc in locations)


def canonical_city(city: str) -> str:
    """'New York City' -> 'new york', 'Brooklyn' -> 'new york', 'Boston' -> 'boston'."""
    value = " ".join(city.lower().split())
    return _CANONICAL_CITY.get(value, value)


def location_matches(location: str, home: tuple[str, str]) -> bool:
    """location is a seeking_locations entry: 'City, ST', 'ST', or e.g. 'Worldwide'."""
    if location.strip().lower() in OPEN_LOCATIONS:
        return True
    parts = [p.strip() for p in location.split(",")]
    if len(parts) == 2:
        return (canonical_city(parts[0]), parts[1].upper()) == home
    # A bare state code ("NY") means anywhere in that state.
    return len(parts) == 1 and parts[0].upper() == home[1]


DEFAULT_CRITERIA: Sequence[MatchCriterion] = (
    AgeCriterion(),
    GenderCriterion(),
    LocationCriterion(),
)


def evaluate_role(
    role: Role,
    profile: ArtistProfile,
    criteria: Sequence[MatchCriterion] = DEFAULT_CRITERIA,
) -> MatchResult:
    reasons = {c.key: c.evaluate(role, profile) for c in criteria}
    return MatchResult(is_match=all(reasons.values()), reasons=reasons)

"""Pure unit tests: models are built in memory, no database needed."""

import pytest

from app.models import ArtistProfile, CastingCall, Role
from app.services.matching import (
    AgeCriterion,
    GenderCriterion,
    LocationCriterion,
    canonical_city,
    evaluate_role,
)


def make_role(*, locations=(), **kwargs) -> Role:
    role = Role(role_name="Lead", **{"genders": [], **kwargs})
    role.casting_call = CastingCall(title="Film", seeking_locations=list(locations))
    return role


def make_profile(**kwargs) -> ArtistProfile:
    defaults = {
        "playing_age_min": 16,
        "playing_age_max": 30,
        "genders": ["female", "any gender", "femme presenting"],
        "location_city": "New York",
        "location_state": "NY",
        "willing_to_travel": False,
    }
    return ArtistProfile(**{**defaults, **kwargs})


@pytest.mark.parametrize(
    "age_min, age_max, expected",
    [
        (None, None, True),  # unrestricted
        (18, 24, True),  # inside
        (10, 16, True),  # touches lower bound
        (30, 45, True),  # touches upper bound
        (25, 40, True),  # partial overlap
        (10, 50, True),  # role range contains playing range
        (31, 40, False),
        (10, 15, False),
        (18, None, True),  # "18+"
        (31, None, False),
    ],
)
def test_age_overlaps_playing_range(age_min, age_max, expected):
    role = make_role(age_min=age_min, age_max=age_max)
    assert AgeCriterion().evaluate(role, make_profile()) is expected


def test_age_without_playing_range_fails_only_restricted_roles():
    profile = make_profile(playing_age_min=None, playing_age_max=None)
    assert AgeCriterion().evaluate(make_role(age_min=18), profile) is False
    assert AgeCriterion().evaluate(make_role(), profile) is True


@pytest.mark.parametrize(
    "role_genders, expected",
    [
        ([], True),  # omitted / "All Genders" = open to any
        (["female"], True),
        (["female", "trans female"], True),
        (["femme presenting"], True),
        (["Femme-Presenting"], True),  # spelling variants still match
        (["male"], False),
        (["trans female"], False),
    ],
)
def test_gender(role_genders, expected):
    role = make_role(genders=role_genders)
    assert GenderCriterion().evaluate(role, make_profile()) is expected


def test_gender_without_profile_genders_fails_only_restricted_roles():
    profile = make_profile(genders=[])
    assert GenderCriterion().evaluate(make_role(genders=["female"]), profile) is False
    assert GenderCriterion().evaluate(make_role(), profile) is True


@pytest.mark.parametrize(
    "locations, expected",
    [
        ([], True),  # unrestricted
        (["New York, NY"], True),
        (["New York City, NY"], True),  # real Backstage variant
        (["Brooklyn, NY"], True),  # borough alias
        (["new york , ny"], True),
        (["Leola, PA", "New York, NY"], True),  # any of several
        (["Worldwide"], True),
        (["NY"], True),  # bare state
        (["Boston, MA"], False),
        (["New York, PA"], False),  # same city name, different state
        (["Buffalo, NY"], False),
        (["Canada"], False),
    ],
)
def test_location(locations, expected):
    role = make_role(locations=locations)
    assert LocationCriterion().evaluate(role, make_profile()) is expected


def test_location_miss_passes_when_willing_to_travel():
    role = make_role(locations=["Boston, MA"])
    assert LocationCriterion().evaluate(role, make_profile(willing_to_travel=True))


def test_location_without_home_fails_only_restricted_roles():
    profile = make_profile(location_city=None)
    assert LocationCriterion().evaluate(make_role(locations=["New York, NY"]), profile) is False
    assert LocationCriterion().evaluate(make_role(), profile) is True


@pytest.mark.parametrize(
    "city, expected",
    [
        ("New York City", "new york"),
        ("Manhattan", "new york"),
        ("Hollywood", "los angeles"),
        ("Kansas City", "kansas city"),
        ("Union City", "union city"),  # not "union": a different NJ town
        ("Boston", "boston"),
    ],
)
def test_canonical_city(city, expected):
    assert canonical_city(city) == expected


def test_evaluate_role_reports_every_reason():
    role = make_role(age_min=35, age_max=45, genders=["female"], locations=["Boston, MA"])
    result = evaluate_role(role, make_profile())
    assert not result.is_match
    assert result.reasons == {"age": False, "gender": True, "location": False}


def test_evaluate_role_match():
    role = make_role(age_min=18, age_max=24, genders=["female"], locations=["New York City, NY"])
    result = evaluate_role(role, make_profile())
    assert result.is_match
    assert result.reasons == {"age": True, "gender": True, "location": True}


def test_custom_criteria():
    class UnionCriterion:
        key = "union"

        def evaluate(self, role, profile):
            return role.casting_call.union_status == profile.union_status

    role = make_role()
    role.casting_call.union_status = "union"
    result = evaluate_role(role, make_profile(union_status="nonunion"), [UnionCriterion()])
    assert result == type(result)(is_match=False, reasons={"union": False})

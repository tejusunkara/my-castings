"""Whitespace, union-status, gender, age-range and location normalization."""

import re

# "Multiple Genders" is how Casting Networks shows a role open to more than one gender
# without naming them; treated as open so a possible fit isn't hidden.
OPEN_GENDER_LABELS = {"all genders", "any gender", "any", "multiple genders"}

# Different sources' words for the same label (Casting Networks: "Woman"; Backstage:
# "Female"), keyed by the spelling that is kept.
GENDER_SYNONYMS = {
    "female": {"woman", "women"},
    "male": {"man", "men"},
}
_CANONICAL_GENDER = {alias: key for key, aliases in GENDER_SYNONYMS.items() for alias in aliases}

_AGE_RANGE_RE = re.compile(r"^(\d{1,3})\s*-\s*(\d{1,3})$")
_AGE_MIN_RE = re.compile(r"^(\d{1,3})\s*\+$")
_AGE_EXACT_RE = re.compile(r"^(\d{1,3})$")


def clean_text(text: str) -> str:
    """Collapse runs of whitespace (including the &nbsp; Backstage uses) to single spaces."""
    return " ".join(text.replace("\xa0", " ").split())


def normalize_union_status(tag: str | None) -> str | None:
    if not tag:
        return None
    # "Union And Nonunion" -> "unionandnonunion", "Non-Union" -> "nonunion"
    value = re.sub(r"[^a-z]", "", tag.lower())
    return {
        "union": "union",
        "nonunion": "nonunion",
        "unionandnonunion": "union_and_nonunion",
        "unionnonunion": "union_and_nonunion",
    }.get(value)


def gender_key(label: str) -> str:
    """Comparable form of a gender label: 'Femme-Presenting' -> 'femme presenting',
    'Woman' -> 'female'.

    Applied to both role labels and the profile's labels, so spelling variants match.
    """
    key = clean_text(re.sub(r"[-_]", " ", label)).lower()
    return _CANONICAL_GENDER.get(key, key)


def is_open_gender(label: str) -> bool:
    return gender_key(label) in OPEN_GENDER_LABELS


def normalize_genders(tokens: list[str]) -> list[str]:
    """A role's gender tokens as gender keys; [] (open to any) if any token is an open
    label, so "Female, All Genders" doesn't turn an open role into a female-only one."""
    keys = [gender_key(t) for t in tokens]
    if any(k in OPEN_GENDER_LABELS for k in keys):
        return []
    return [k for k in keys if k]


def parse_age_range(token: str) -> tuple[int, int | None]:
    """'18-24' -> (18, 24); '18+' -> (18, None); '21' -> (21, 21). Raises ValueError
    otherwise."""
    value = clean_text(token)
    if m := _AGE_RANGE_RE.match(value):
        low, high = int(m.group(1)), int(m.group(2))
        if low > high:
            raise ValueError(f"age range is inverted: {token!r}")
        return low, high
    if m := _AGE_MIN_RE.match(value):
        return int(m.group(1)), None
    if m := _AGE_EXACT_RE.match(value):
        return int(m.group(1)), int(m.group(1))
    raise ValueError(f"unparseable age range: {token!r}")


def split_locations(text: str) -> list[str]:
    """'Brooklyn, NY; New York, NY… More' -> ['Brooklyn, NY', 'New York, NY'].

    Drops the trailing truncation marker and empty city/state slots (Backstage renders
    a country-only location as ', , Canada').
    """
    value = re.sub(r"(…|\.\.\.)\s*More\s*$", "", clean_text(text))
    locations = []
    for chunk in value.split(";"):
        parts = [p.strip() for p in chunk.split(",") if p.strip()]
        if parts:
            locations.append(", ".join(parts))
    return locations

"""Whitespace, union-status, gender, age-range and location normalization."""

import re

OPEN_GENDER_LABELS = {"all genders", "any gender", "any"}

_AGE_RANGE_RE = re.compile(r"^(\d{1,3})\s*-\s*(\d{1,3})$")
_AGE_MIN_RE = re.compile(r"^(\d{1,3})\s*\+$")


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


def normalize_gender(token: str) -> str | None:
    """Lower-cased gender label, or None for "open to any" labels like "All Genders"."""
    value = clean_text(token).lower()
    if not value or value in OPEN_GENDER_LABELS:
        return None
    return value


def parse_age_range(token: str) -> tuple[int, int | None]:
    """'18-24' -> (18, 24); '18+' -> (18, None). Raises ValueError otherwise."""
    value = clean_text(token)
    if m := _AGE_RANGE_RE.match(value):
        low, high = int(m.group(1)), int(m.group(2))
        if low > high:
            raise ValueError(f"age range is inverted: {token!r}")
        return low, high
    if m := _AGE_MIN_RE.match(value):
        return int(m.group(1)), None
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

"""'Posted 1 day, 20 hours ago' -> timedelta."""

import re
from datetime import timedelta

from ingestion_core.parsing.text_normalize import clean_text

# "an hour ago" / "a day ago" use a word instead of 1.
_UNIT_RE = re.compile(r"\b(\d+|an?)\s*(minute|hour|day|week)s?\b", re.IGNORECASE)


def parse_relative_age(text: str) -> timedelta | None:
    """Returns None when no recognizable "<n> <unit>" component is present."""
    parts = _UNIT_RE.findall(clean_text(text))
    if not parts:
        return None
    total = timedelta()
    for amount, unit in parts:
        count = int(amount) if amount.isdigit() else 1
        total += timedelta(**{unit.lower() + "s": count})
    return total

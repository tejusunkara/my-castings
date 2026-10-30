from datetime import timedelta

import pytest

from ingestion_core.parsing.relative_time import parse_relative_age
from ingestion_core.parsing.text_normalize import (
    normalize_gender,
    normalize_union_status,
    parse_age_range,
    split_locations,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Posted 1 day, 20 hours ago", timedelta(days=1, hours=20)),
        ("Posted 3 hours ago", timedelta(hours=3)),
        ("Posted 1 week ago", timedelta(weeks=1)),
        ("Posted 45 minutes ago", timedelta(minutes=45)),
        ("Posted\xa02 days ago", timedelta(days=2)),
        ("Posted just now", None),
    ],
)
def test_parse_relative_age(text, expected):
    assert parse_relative_age(text) == expected


@pytest.mark.parametrize(
    "token, expected",
    [("18-24", (18, 24)), ("18 - 24", (18, 24)), ("18+", (18, None))],
)
def test_parse_age_range(token, expected):
    assert parse_age_range(token) == expected


@pytest.mark.parametrize("token", ["18 to 24", "30-20", "adult", ""])
def test_parse_age_range_rejects(token):
    with pytest.raises(ValueError):
        parse_age_range(token)


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("Union", "union"),
        ("Nonunion", "nonunion"),
        ("Non-Union", "nonunion"),
        ("Union And Nonunion", "union_and_nonunion"),
        ("Union/Non-Union", "union_and_nonunion"),
        ("SAG-AFTRA", None),
        (None, None),
    ],
)
def test_normalize_union_status(tag, expected):
    assert normalize_union_status(tag) == expected


@pytest.mark.parametrize(
    "token, expected",
    [("Female", "female"), ("Trans Female", "trans female"), ("All Genders", None), ("", None)],
)
def test_normalize_gender(token, expected):
    assert normalize_gender(token) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Brooklyn, NY; New York, NY… More", ["Brooklyn, NY", "New York, NY"]),
        ("Leola, PA; Philadelphia, PA", ["Leola, PA", "Philadelphia, PA"]),
        (", , Canada", ["Canada"]),
        ("Worldwide", ["Worldwide"]),
    ],
)
def test_split_locations(text, expected):
    assert split_locations(text) == expected

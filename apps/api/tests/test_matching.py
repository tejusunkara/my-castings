"""Pure unit tests: models are built in memory, no database needed."""

from datetime import date

import pytest

from app.models import ArtistProfile, CastingCall, Role
from app.services.matching import (
    AgeCriterion,
    GenderCriterion,
    LocationCriterion,
    canonical_city,
    evaluate_role,
)

TODAY = date(2026, 10, 30)
DOB_AGE_30 = date(1996, 5, 1)


def make_role(*, locations=(), **kwargs) -> Role:
    role = Role(role_name="Lead", **{"genders": [], **kwargs})
    role.casting_call = CastingCall(title="Film", seeking_locations=list(locations))
    return role


def make_profile(**kwargs) -> ArtistProfile:
    defaults = {
        "date_of_birth": DOB_AGE_30,
        "gender": "female",
        "location_city": "New York",
        "location_state": "NY",
        "willing_to_travel": False,
    }
    return ArtistProfile(**{**defaults, **kwargs})


@pytest.mark.parametrize(
    "age_min, age_max, expected",
    [
        (None, None, True),  # unrestricted
        (30, 40, True),  # lower boundary inclusive
        (20, 30, True),  # upper boundary inclusive
        (31, 40, False),
        (18, 29, False),
        (18, None, True),  # "18+"
        (31, None, False),
    ],
)
def test_age(age_min, age_max, expected):
    role = make_role(age_min=age_min, age_max=age_max)
    assert AgeCriterion().evaluate(role, make_profile(), TODAY) is expected


def test_age_uses_today_not_a_stored_age():
    role = make_role(age_min=18, age_max=29)
    profile = make_profile()
    assert AgeCriterion().evaluate(role, profile, date(2026, 4, 30)) is True  # still 29
    assert AgeCriterion().evaluate(role, profile, date(2026, 5, 1)) is False  # birthday


def test_age_without_dob_fails_only_restricted_roles():
    profile = make_profile(date_of_birth=None)
    assert AgeCriterion().evaluate(make_role(age_min=18), profile, TODAY) is False
    assert AgeCriterion().evaluate(make_role(), profile, TODAY) is True


@pytest.mark.parametrize(
    "role_genders, profile_gender, expected",
    [
        ([], "female", True),  # omitted = open to any
        ([], None, True),
        (["female", "trans female"], "female", True),
        (["female", "trans female"], "Trans Female", True),
        (["male"], "female", False),
        (["female"], None, False),
    ],
)
def test_gender(role_genders, profile_gender, expected):
    role = make_role(genders=role_genders)
    profile = make_profile(gender=profile_gender)
    assert GenderCriterion().evaluate(role, profile, TODAY) is expected


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
    assert LocationCriterion().evaluate(role, make_profile(), TODAY) is expected


def test_location_miss_passes_when_willing_to_travel():
    role = make_role(locations=["Boston, MA"])
    assert LocationCriterion().evaluate(role, make_profile(willing_to_travel=True), TODAY)


def test_location_without_home_fails_only_restricted_roles():
    profile = make_profile(location_city=None)
    assert (
        LocationCriterion().evaluate(make_role(locations=["New York, NY"]), profile, TODAY) is False
    )
    assert LocationCriterion().evaluate(make_role(), profile, TODAY) is True


@pytest.mark.parametrize(
    "city, expected",
    [
        ("New York City", "new york"),
        ("Manhattan", "new york"),
        ("Hollywood", "los angeles"),
        ("Kansas City", "kansas city"),
        ("Boston", "boston"),
        ("Union City", "union city"),  # not "union": a different NJ town,
    ],
)
def test_canonical_city(city, expected):
    assert canonical_city(city) == expected


def test_evaluate_role_reports_every_reason():
    role = make_role(age_min=18, age_max=25, genders=["female"], locations=["Boston, MA"])
    result = evaluate_role(role, make_profile(), TODAY)
    assert not result.is_match
    assert result.reasons == {"age": False, "gender": True, "location": False}


def test_evaluate_role_match():
    role = make_role(age_min=25, age_max=35, genders=["female"], locations=["New York City, NY"])
    result = evaluate_role(role, make_profile(), TODAY)
    assert result.is_match
    assert result.reasons == {"age": True, "gender": True, "location": True}


def test_custom_criteria():
    class UnionCriterion:
        key = "union"

        def evaluate(self, role, profile, today):
            return role.casting_call.union_status == profile.union_status

    role = make_role()
    role.casting_call.union_status = "union"
    result = evaluate_role(role, make_profile(union_status="nonunion"), TODAY, [UnionCriterion()])
    assert result == type(result)(is_match=False, reasons={"union": False})

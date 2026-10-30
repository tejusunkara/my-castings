from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.models import CastingSource, RawEmail, Role, SavedMatch
from app.services.ingestion import store_digest
from app.services.profile import upsert_profile
from app.services.sweeps import run_match_sweep
from ingestion_core.types import ParsedDigest, ParsedPosting, ParsedRole

PROFILE = {
    "playing_age_min": 16,
    "playing_age_max": 30,
    "genders": ["female"],
    "location_city": "New York City",
    "location_state": "NY",
    "willing_to_travel": False,
}


@pytest.fixture
def roles(db) -> dict[str, Role]:
    """Fits (age 18-24, female, NYC) and Misfit (age 50+, male)."""
    source = db.scalars(select(CastingSource).where(CastingSource.key == "backstage")).one()
    raw_email = RawEmail(
        s3_bucket="local", s3_key="x", received_at=datetime(2026, 10, 1, tzinfo=UTC)
    )
    db.add(raw_email)
    digest = ParsedDigest(
        postings=[
            ParsedPosting(
                title="Film",
                seeking_locations=["New York, NY"],
                roles=[
                    ParsedRole("Fits", genders=["female"], age_min=18, age_max=24),
                    ParsedRole("Misfit", genders=["male"], age_min=50),
                ],
            )
        ]
    )
    store_digest(db, raw_email, source, digest)
    return {r.role_name: r for r in db.scalars(select(Role))}


def matches(db) -> dict[str, SavedMatch]:
    db.expire_all()
    return {m.role.role_name: m for m in db.scalars(select(SavedMatch))}


def test_no_profile_skips(db, roles):
    assert run_match_sweep(db).skipped_no_profile
    assert matches(db) == {}


def test_creates_new_matches_with_reasons(db, roles):
    upsert_profile(db, PROFILE)
    result = run_match_sweep(db)
    assert result.created == 1
    fits = matches(db)["Fits"]
    assert fits.status == "new"
    assert fits.match_reasons == {"age": True, "gender": True, "location": True}


def test_idempotent(db, roles):
    upsert_profile(db, PROFILE)
    run_match_sweep(db)
    again = run_match_sweep(db)
    assert (again.created, again.removed) == (0, 0)
    assert list(matches(db)) == ["Fits"]


def test_profile_change_removes_stale_new_match_and_adds_new_fit(db, roles):
    upsert_profile(db, PROFILE)
    run_match_sweep(db)

    upsert_profile(db, {"playing_age_min": 45, "playing_age_max": 60, "genders": ["male"]})
    result = run_match_sweep(db)
    assert (result.removed, result.created) == (1, 1)
    assert list(matches(db)) == ["Misfit"]


@pytest.mark.parametrize("status", ["saved", "applied", "dismissed"])
def test_user_acted_matches_are_never_touched(db, roles, status):
    upsert_profile(db, PROFILE)
    run_match_sweep(db)
    matches(db)["Fits"].status = status
    db.flush()

    upsert_profile(db, {"genders": ["male"]})
    run_match_sweep(db)
    assert matches(db)["Fits"].status == status


def test_reasons_refreshed_on_still_matching_new_rows(db, roles):
    upsert_profile(db, PROFILE)
    run_match_sweep(db)
    fits = matches(db)["Fits"]
    fits.match_reasons = {"age": True}
    db.flush()

    run_match_sweep(db)
    assert matches(db)["Fits"].match_reasons == {"age": True, "gender": True, "location": True}

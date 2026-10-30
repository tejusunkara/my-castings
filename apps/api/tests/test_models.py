from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.models import (
    ArtistProfile,
    CastingCall,
    CastingSource,
    MediaAsset,
    RawEmail,
    Role,
    SavedMatch,
)

RECEIVED = datetime(2026, 10, 29, 18, 13, 43, tzinfo=UTC)


@pytest.fixture
def backstage(db):
    return db.scalars(select(CastingSource).where(CastingSource.key == "backstage")).one()


@pytest.fixture
def raw_email(db):
    email = RawEmail(s3_bucket="raw", s3_key="abc", received_at=RECEIVED)
    db.add(email)
    db.flush()
    return email


def make_call(raw_email, source, **roles_kwargs):
    call = CastingCall(raw_email=raw_email, source=source, title="Film")
    call.roles.append(Role(role_name="Lead", **roles_kwargs))
    return call


def test_migration_seeds_backstage_source(backstage):
    assert (backstage.display_name, backstage.sender_domain_match) == ("Backstage", "backstage.com")
    assert backstage.is_active


def test_server_defaults_apply_to_raw_sql_inserts(db):
    # The Lambda may write rows without going through these models.
    row = db.execute(
        text(
            "INSERT INTO raw_emails (s3_bucket, s3_key, received_at) "
            "VALUES ('raw', 'k', now()) RETURNING parse_status, sender_verified"
        )
    ).one()
    assert tuple(row) == ("pending", False)


def test_array_columns_round_trip(db, raw_email, backstage):
    call = make_call(raw_email, backstage, genders=["female", "trans female"], age_min=25)
    call.seeking_locations = ["Leola, PA", "Philadelphia, PA"]
    db.add(call)
    db.flush()
    db.expire_all()
    role = db.scalars(select(Role)).one()
    assert role.genders == ["female", "trans female"]
    assert role.casting_call.seeking_locations == ["Leola, PA", "Philadelphia, PA"]


def test_array_columns_default_empty(db, raw_email, backstage):
    db.add(make_call(raw_email, backstage))
    db.flush()
    db.expire_all()
    role = db.scalars(select(Role)).one()
    assert role.genders == [] and role.casting_call.seeking_locations == []


def test_deleting_raw_email_cascades_to_roles_and_matches(db, raw_email, backstage):
    call = make_call(raw_email, backstage)
    db.add(call)
    db.flush()
    db.add(SavedMatch(role_id=call.roles[0].id, match_reasons={"age": True}))
    db.flush()

    db.execute(text("DELETE FROM raw_emails WHERE id = :id"), {"id": raw_email.id})
    for model in (CastingCall, Role, SavedMatch):
        assert db.scalars(select(model)).all() == []


def test_one_saved_match_per_role(db, raw_email, backstage):
    call = make_call(raw_email, backstage)
    db.add(call)
    db.flush()
    db.add(SavedMatch(role_id=call.roles[0].id, match_reasons={}))
    db.flush()
    db.add(SavedMatch(role_id=call.roles[0].id, match_reasons={}))
    with pytest.raises(IntegrityError):
        db.flush()


def test_duplicate_s3_object_rejected(db, raw_email):
    db.add(RawEmail(s3_bucket="raw", s3_key="abc", received_at=RECEIVED))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize(
    "model, kwargs",
    [
        (
            RawEmail,
            {"s3_bucket": "b", "s3_key": "k", "received_at": RECEIVED, "parse_status": "ok"},
        ),
        (MediaAsset, {"asset_type": "photo"}),
        (MediaAsset, {"asset_type": "headshot", "upload_status": "uploading"}),
    ],
)
def test_check_constraints(db, model, kwargs):
    if model is MediaAsset:
        profile = ArtistProfile()
        db.add(profile)
        db.flush()
        kwargs = {"profile_id": profile.id, **kwargs}
    db.add(model(**kwargs))
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize(
    "dob, on, expected",
    [
        (date(2000, 5, 10), date(2026, 5, 9), 25),
        (date(2000, 5, 10), date(2026, 5, 10), 26),
        (date(2000, 2, 29), date(2026, 2, 28), 25),
        (date(2000, 2, 29), date(2026, 3, 1), 26),
        (None, date(2026, 5, 10), None),
    ],
)
def test_profile_age_on(dob, on, expected):
    assert ArtistProfile(date_of_birth=dob).age_on(on) == expected


@pytest.mark.parametrize("bounds", [(16, None), (None, 30), (30, 16)])
def test_playing_age_range_must_be_complete_and_ordered(db, bounds):
    db.add(ArtistProfile(playing_age_min=bounds[0], playing_age_max=bounds[1]))
    with pytest.raises(IntegrityError):
        db.flush()


def test_profile_genders_round_trip(db):
    profile = ArtistProfile(
        playing_age_min=16, playing_age_max=30, genders=["female", "femme presenting"]
    )
    db.add(profile)
    db.flush()
    db.expire_all()
    assert db.get(ArtistProfile, profile.id).genders == ["female", "femme presenting"]

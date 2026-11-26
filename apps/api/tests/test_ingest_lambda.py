"""The ingestion Lambda's work, against moto S3 and the test database."""

from datetime import UTC, datetime
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import select

from app import ingest_lambda
from app.models import ArtistProfile, CastingCall, RawEmail, SavedMatch
from app.services.raw_email_store import RawEmailNotFoundError, read_raw_email

FIXTURES = Path(__file__).resolve().parents[3] / "packages/ingestion_core/tests/fixtures"
BUCKET = "my-castings-raw-emails-test"
EVENT_TIME = datetime(2026, 11, 26, 14, 0, tzinfo=UTC)


@pytest.fixture
def s3(monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "testing")
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture
def lambda_db(db, monkeypatch):
    """Point the handler's SessionLocal.begin() at the test transaction."""
    from contextlib import contextmanager

    @contextmanager
    def begin():
        yield db
        db.flush()

    monkeypatch.setattr(ingest_lambda.SessionLocal, "begin", begin)
    db.add(
        ArtistProfile(
            playing_age_min=16,
            playing_age_max=30,
            genders=["female"],
            location_city="New York City",
            location_state="NY",
            willing_to_travel=True,
        )
    )
    db.flush()
    return db


def put(s3, key: str, fixture: str) -> None:
    s3.put_object(Bucket=BUCKET, Key=key, Body=(FIXTURES / fixture).read_bytes())


def event(key: str) -> dict:
    return {
        "time": "2026-11-26T14:00:00Z",
        "detail": {"bucket": {"name": BUCKET}, "object": {"key": key}},
    }


def test_new_email_is_ingested_and_matched(s3, lambda_db, monkeypatch):
    monkeypatch.setattr(ingest_lambda, "read_s3_object", _reader(s3))
    put(s3, "inbound/abc123", "backstage_sample.eml")

    summary = ingest_lambda.handler(event("inbound/abc123"))

    assert summary["status"] == "success" and summary["source"] == "backstage"
    assert summary["created_roles"] == 8 and summary["new_matches"] > 0
    raw = lambda_db.scalars(select(RawEmail)).one()
    assert (raw.s3_bucket, raw.s3_key) == (BUCKET, "inbound/abc123")
    # received_at comes from the email's Date header, not the event.
    assert raw.received_at == datetime(2026, 10, 29, 18, 13, 43, tzinfo=UTC)
    assert lambda_db.scalars(select(CastingCall)).all()
    assert lambda_db.scalars(select(SavedMatch)).all()


def test_redelivered_event_does_nothing(s3, lambda_db, monkeypatch):
    monkeypatch.setattr(ingest_lambda, "read_s3_object", _reader(s3))
    put(s3, "inbound/abc123", "backstage_sample.eml")
    ingest_lambda.handler(event("inbound/abc123"))
    calls = len(lambda_db.scalars(select(CastingCall)).all())

    assert ingest_lambda.handler(event("inbound/abc123"))["status"] == "duplicate"
    assert len(lambda_db.scalars(select(RawEmail)).all()) == 1
    assert len(lambda_db.scalars(select(CastingCall)).all()) == calls


def test_bad_email_is_recorded_not_raised(s3, lambda_db, monkeypatch):
    monkeypatch.setattr(ingest_lambda, "read_s3_object", _reader(s3))
    # A manual forward: verified (gmail.com) but no adapter claims it.
    put(s3, "inbound/manual", "actors_access_manual_forward.eml")
    summary = ingest_lambda.handler(event("inbound/manual"))
    assert summary["status"] == "failed"
    assert summary["error"] == "no adapter for sender 'redacted@gmail.com'"


def test_url_encoded_key_is_decoded(s3, lambda_db, monkeypatch):
    monkeypatch.setattr(ingest_lambda, "read_s3_object", _reader(s3))
    put(s3, "inbound/a b", "casting_networks_single_role.eml")
    assert ingest_lambda.handler(event("inbound/a+b"))["key"] == "inbound/a b"


def test_missing_object_raises_so_lambda_retries(s3, lambda_db, monkeypatch):
    monkeypatch.setattr(ingest_lambda, "read_s3_object", _reader(s3))
    with pytest.raises(RawEmailNotFoundError):
        ingest_lambda.handler(event("inbound/gone"))
    assert lambda_db.scalars(select(RawEmail)).all() == []


def test_reprocess_reads_from_s3(s3):
    put(s3, "inbound/abc", "backstage_sample.eml")
    raw = RawEmail(s3_bucket=BUCKET, s3_key="inbound/abc", received_at=EVENT_TIME)
    assert read_raw_email(raw, s3) == (FIXTURES / "backstage_sample.eml").read_bytes()
    with pytest.raises(RawEmailNotFoundError):
        read_raw_email(RawEmail(s3_bucket=BUCKET, s3_key="nope", received_at=EVENT_TIME), s3)


def _reader(s3):
    from app.services.raw_email_store import read_s3_object

    return lambda bucket, key, client=None: read_s3_object(bucket, key, s3)

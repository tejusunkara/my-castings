from collections.abc import Mapping
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import CastingCall, CastingSource, RawEmail, Role
from app.services.ingestion import ingest
from ingestion_core.adapters.backstage import BackstageAdapter
from ingestion_core.adapters.registry import AdapterRegistry

FIXTURES = Path(__file__).resolve().parents[3] / "packages/ingestion_core/tests/fixtures"
RECEIVED = datetime(2026, 10, 29, 18, 13, 43, tzinfo=UTC)

CARD_HTML = """<html><body><div class="section_job-card">
  <h2><a href="https://example.com/job">Spoofed Job</a></h2>
  <table><tbody><tr><td><h4>Lead</h4><ul><li>Lead, Female, 20-30</li></ul>
    <a class="primary-cta" href="https://evil.example/apply">Apply</a></td></tr></tbody></table>
</div></body></html>"""


@pytest.fixture
def raw_email(db):
    email = RawEmail(s3_bucket="local", s3_key="x.eml", received_at=RECEIVED)
    db.add(email)
    db.flush()
    return email


def synthetic(auth_results: str) -> bytes:
    msg = EmailMessage()
    msg["Authentication-Results"] = auth_results
    msg["From"] = "noreply@backstage.com"
    msg["Subject"] = "New Roles Available"
    msg.set_content("text")
    msg.add_alternative(CARD_HTML, subtype="html")
    return msg.as_bytes()


def test_verified_backstage_digest_is_stored(db, raw_email):
    result = ingest(db, raw_email, (FIXTURES / "backstage_sample.eml").read_bytes())
    assert raw_email.parse_status == "success"
    assert raw_email.sender_verified and raw_email.verdict_details["verified_by"] == "dkim"
    assert raw_email.source_key == "backstage"
    assert raw_email.from_address == "noreply@backstage.com"
    assert raw_email.subject.startswith("240 New Roles Available")
    assert result.created_roles == 8
    assert len(db.scalars(select(CastingCall)).all()) == 5


def test_unverified_sender_is_quarantined_and_stores_nothing(db, raw_email):
    raw = synthetic("amazonses.com; spf=fail envelope-from=x@evil.example; dkim=none;")
    ingest(db, raw_email, raw)
    assert raw_email.parse_status == "failed"
    assert raw_email.parse_error.startswith("quarantined: sender not verified")
    assert raw_email.sender_verified is False and raw_email.source is None
    assert db.scalars(select(Role)).all() == []


def test_header_not_from_ses_is_quarantined(db, raw_email):
    ingest(db, raw_email, synthetic("mx.google.com; dkim=pass header.i=@backstage.com"))
    assert "not SES" in raw_email.parse_error


def test_verified_sender_without_adapter(db, raw_email):
    ingest(db, raw_email, (FIXTURES / "casting_networks_sample.eml").read_bytes())
    assert raw_email.sender_verified
    assert raw_email.parse_status == "failed"
    assert raw_email.parse_error == "no adapter for sender 'notifications@castingnetworks.com'"
    assert raw_email.source is None


def test_ambiguous_adapters_fail(db, raw_email):
    class AlsoBackstage(BackstageAdapter):
        source_key = "also_backstage"

    registry = AdapterRegistry([BackstageAdapter(), AlsoBackstage()])
    raw = (FIXTURES / "backstage_sample.eml").read_bytes()
    ingest(db, raw_email, raw, registry=registry)
    assert raw_email.parse_status == "failed"
    assert "backstage, also_backstage" in raw_email.parse_error


def test_inactive_source_fails(db, raw_email):
    db.scalars(
        select(CastingSource).where(CastingSource.key == "backstage")
    ).one().is_active = False
    ingest(db, raw_email, (FIXTURES / "backstage_sample.eml").read_bytes())
    assert raw_email.parse_error == "no active casting source 'backstage'"


def test_failed_reingest_keeps_rows_from_earlier_success(db, raw_email):
    raw = (FIXTURES / "backstage_sample.eml").read_bytes()
    ingest(db, raw_email, raw)

    class BrokenAdapter(BackstageAdapter):
        def matches_sender(self, from_address: str, headers: Mapping[str, str]) -> bool:
            return True

        def parse(self, raw_mime, received_at):
            from ingestion_core.types import ParsedDigest

            return ParsedDigest(error="parser regression")

    ingest(db, raw_email, raw, registry=AdapterRegistry([BrokenAdapter()]))
    assert raw_email.parse_status == "failed"
    assert len(db.scalars(select(Role)).all()) == 8


def test_garbage_bytes_fail_without_raising(db, raw_email):
    ingest(db, raw_email, b"\x00\xff not an email")
    assert raw_email.parse_status == "failed"

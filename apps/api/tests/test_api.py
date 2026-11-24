"""Endpoint tests for profile, casting calls, matches and admin (logged-in client)."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models import ArtistProfile, RawEmail, SavedMatch
from app.services.ingestion import ingest
from ingestion_core.adapters.backstage import BackstageAdapter
from ingestion_core.adapters.registry import AdapterRegistry

FIXTURES = Path(__file__).resolve().parents[3] / "packages/ingestion_core/tests/fixtures"

PROFILE = {
    "playing_age_min": 16,
    "playing_age_max": 30,
    "genders": ["female", "any gender", "femme presenting"],
    "location_city": "New York City",
    "location_state": "ny",
    "willing_to_travel": True,
}


def load_fixture(db, name: str) -> RawEmail:
    raw = (FIXTURES / name).read_bytes()
    from ingestion_core.parsing.mime import load_message, sent_at

    raw_email = RawEmail(s3_bucket="local", s3_key=name, received_at=sent_at(load_message(raw)))
    db.add(raw_email)
    ingest(db, raw_email, raw)
    db.flush()
    return raw_email


@pytest.fixture
def seeded(db):
    return {
        name: load_fixture(db, name)
        for name in ("backstage_sample.eml", "backstage_badges.eml", "casting_networks_sample.eml")
    }


# --- profile ---


def test_profile_missing_then_created(client):
    assert client.get("/profile").status_code == 404
    response = client.put("/profile", json=PROFILE)
    assert response.status_code == 200
    body = response.json()
    assert body["location_state"] == "NY"  # normalized
    assert body["genders"] == PROFILE["genders"]
    assert client.get("/profile").json() == body


def test_second_put_updates_the_same_row(client, db):
    first = client.put("/profile", json=PROFILE).json()
    second = client.put("/profile", json={**PROFILE, "bio": "Actor"}).json()
    assert second["id"] == first["id"] and second["bio"] == "Actor"
    assert db.scalar(select(func.count()).select_from(ArtistProfile)) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"playing_age_min": 16, "playing_age_max": None},
        {"playing_age_min": 30, "playing_age_max": 16},
        {"location_state": "New York"},
        {"genders": ["female", "  "]},
    ],
)
def test_profile_validation(client, override):
    assert client.put("/profile", json={**PROFILE, **override}).status_code == 422


def test_profile_put_rematches_immediately(client, seeded):
    assert client.get("/matches").json() == []
    client.put("/profile", json=PROFILE)
    matched = client.get("/matches").json()
    assert matched and all(m["status"] == "new" for m in matched)


# --- casting calls ---


def test_casting_calls_newest_first_with_roles(client, seeded):
    calls = client.get("/casting-calls", params={"limit": 200}).json()
    assert len(calls) == 10 + 22
    # Casting Networks emails give no posting age, so those calls sort after Backstage's.
    backstage, casting_networks = calls[:10], calls[10:]
    assert all(c["source_key"] == "backstage" for c in backstage)
    posted = [c["posted_at"] for c in backstage]
    assert posted == sorted(posted, reverse=True)
    assert all(c["source_key"] == "casting_networks" for c in casting_networks)
    assert all(c["posted_at"] is None and c["submission_deadline"] for c in casting_networks)
    sparrow = next(r for c in calls for r in c["roles"] if r["role_name"] == "Sparrow Huang")
    assert sparrow["genders"] == ["female", "trans female"]

    detail = client.get(f"/casting-calls/{calls[0]['id']}").json()
    assert detail == calls[0]


def test_casting_call_404(client):
    assert client.get("/casting-calls/999999").status_code == 404


# --- matches ---


@pytest.fixture
def match_id(client, seeded):
    client.put("/profile", json=PROFILE)
    return client.get("/matches").json()[0]["id"]


def test_match_includes_role_and_casting_call(client, match_id):
    matches = client.get("/matches", params={"limit": 200}).json()
    match = matches[0]
    assert match["match_reasons"] == {"age": True, "gender": True, "location": True}
    assert match["role"]["apply_url"].startswith("https://")
    assert {m["casting_call"]["source_key"] for m in matches} == {"backstage", "casting_networks"}
    # Casting Networks' "Woman" matches the profile's "female".
    women = next(m for m in matches if m["role"]["role_name"] == "WOMEN 20s")
    assert women["role"]["genders"] == ["female"]


def test_apply_then_undo(client, match_id):
    applied = client.patch(f"/matches/{match_id}", json={"status": "applied"}).json()
    assert applied["status"] == "applied" and applied["applied_at"] is not None
    assert [m["id"] for m in client.get("/matches", params={"status": "applied"}).json()] == [
        match_id
    ]
    saved = client.patch(f"/matches/{match_id}", json={"status": "saved"}).json()
    assert saved["applied_at"] is None


def test_note_only_patch_leaves_status(client, match_id):
    body = client.patch(f"/matches/{match_id}", json={"user_note": "self-tape due Fri"}).json()
    assert (body["status"], body["user_note"]) == ("new", "self-tape due Fri")


@pytest.mark.parametrize("body", [{"status": None}, {"status": "maybe"}])
def test_invalid_status(client, match_id, body):
    assert client.patch(f"/matches/{match_id}", json=body).status_code == 422


def test_match_404(client):
    assert client.patch("/matches/999999", json={"status": "saved"}).status_code == 404


# --- admin ---


def test_needs_attention_lists_failures(client, db, seeded):
    raw = (FIXTURES / "casting_networks_single_role.eml").read_bytes()
    unrouted = RawEmail(
        s3_bucket="local",
        s3_key="unrouted.eml",
        received_at=seeded["casting_networks_sample.eml"].received_at,
    )
    db.add(unrouted)
    ingest(db, unrouted, raw, registry=AdapterRegistry([BackstageAdapter()]))
    db.flush()

    rows = client.get("/admin/raw-emails", params={"needs_attention": True}).json()
    assert [r["s3_key"] for r in rows] == ["unrouted.eml"]
    assert rows[0]["parse_error"].startswith("no adapter for sender")
    ok = client.get("/admin/raw-emails", params={"status": "success"}).json()
    assert len(ok) == 3


def test_unknown_status_filter(client):
    assert client.get("/admin/raw-emails", params={"status": "bogus"}).status_code == 422


def test_reprocess_preserves_user_state(client, db, seeded):
    client.put("/profile", json=PROFILE)
    match = client.get("/matches").json()[0]
    client.patch(f"/matches/{match['id']}", json={"status": "applied"})

    email_id = db.get(SavedMatch, match["id"]).casting_call.raw_email_id
    response = client.post(f"/admin/raw-emails/{email_id}/reprocess")
    assert response.status_code == 200
    body = response.json()
    assert body["raw_email"]["parse_status"] == "success"
    assert (body["created_roles"], body["deleted_roles"], body["new_matches"]) == (0, 0, 0)
    after = client.get("/matches", params={"status": "applied"}).json()
    assert [m["id"] for m in after] == [match["id"]]


def test_reprocess_missing_original(client, db):
    from datetime import UTC, datetime

    raw_email = RawEmail(s3_bucket="local", s3_key="gone.eml", received_at=datetime.now(UTC))
    db.add(raw_email)
    db.flush()
    response = client.post(f"/admin/raw-emails/{raw_email.id}/reprocess")
    assert response.status_code == 409


def test_reprocess_rejects_path_escape(client, db):
    from datetime import UTC, datetime

    raw_email = RawEmail(
        s3_bucket="local", s3_key="../../../pyproject.toml", received_at=datetime.now(UTC)
    )
    db.add(raw_email)
    db.flush()
    assert client.post(f"/admin/raw-emails/{raw_email.id}/reprocess").status_code == 409

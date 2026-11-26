"""Media library endpoints and sweep, against an in-memory S3 (moto)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
from moto import mock_aws
from sqlalchemy import select

from app.models import MediaAsset
from app.services.media_store import MediaStore, get_media_store
from app.services.sweeps import PENDING_UPLOAD_GRACE, run_media_sweep

PROFILE = {"playing_age_min": 16, "playing_age_max": 30, "genders": ["female"]}
JPEG = b"\xff\xd8\xff" + b"0" * 1000


@pytest.fixture
def store(settings, monkeypatch):
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        monkeypatch.setenv(name, "testing")
    with mock_aws():
        # The store builds its own client exactly as in production; moto intercepts it.
        store = MediaStore(settings.model_copy(update={"s3_endpoint_url": None}))
        store.client.create_bucket(Bucket=store.bucket)
        yield store


@pytest.fixture
def media_client(client, app, store):
    app.dependency_overrides[get_media_store] = lambda: store
    client.put("/profile", json=PROFILE)
    return client


def start(client, **overrides):
    body = {
        "asset_type": "headshot",
        "filename": "Ana – theatrical.jpg",
        "content_type": "image/jpeg",
        "size_bytes": len(JPEG),
        "label": "Theatrical",
        **overrides,
    }
    return client.post("/media/uploads", json=body)


def browser_upload(store, started, data=JPEG):
    """What the page does with the signed form (the key is pinned by the form)."""
    form = started["upload"]
    store.client.put_object(
        Bucket=store.bucket,
        Key=form["fields"]["key"],
        Body=data,
        ContentType=form["fields"]["Content-Type"],
    )


def test_upload_flow(media_client, store):
    started = start(media_client).json()
    asset = started["asset"]
    assert (asset["upload_status"], asset["view_url"], asset["is_current"]) == (
        "pending",
        None,
        True,
    )
    fields = started["upload"]["fields"]
    assert fields["key"].startswith("media/headshot/") and fields["key"].endswith(".jpg")
    assert fields["Content-Type"] == "image/jpeg"
    assert "policy" in fields and "x-amz-signature" in fields

    # Completing before the file arrives is refused, not faked.
    early = media_client.post(f"/media/{asset['id']}/complete")
    assert early.status_code == 409

    browser_upload(store, started)
    done = media_client.post(f"/media/{asset['id']}/complete").json()
    assert done["upload_status"] == "completed" and done["completed_at"]
    assert done["file_size_bytes"] == len(JPEG)
    assert "Signature=" in done["view_url"] or "X-Amz-Signature=" in done["view_url"]
    assert "filename" in httpx.URL(done["view_url"]).params["response-content-disposition"]

    listed = media_client.get("/media").json()
    assert [a["id"] for a in listed] == [asset["id"]]
    assert listed[0]["original_filename"] == "Ana – theatrical.jpg"


def test_upload_policy_pins_type_and_size(media_client):
    import base64
    import json

    started = start(media_client, asset_type="acting_reel", content_type="video/mp4").json()
    policy = json.loads(base64.b64decode(started["upload"]["fields"]["policy"]))
    conditions = policy["conditions"]
    assert ["content-length-range", 1, 2048 * 1024 * 1024] in conditions
    assert {"Content-Type": "video/mp4"} in conditions
    assert {"key": started["upload"]["fields"]["key"]} in conditions


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"content_type": "image/heic"}, "headshot files must be one of"),
        ({"size_bytes": 26 * 1024 * 1024}, "at most 25 MB"),
        ({"asset_type": "resume", "content_type": "image/jpeg"}, "application/pdf"),
        ({"asset_type": "social_link"}, "takes links, not files"),
    ],
)
def test_upload_rules(media_client, overrides, message):
    response = start(media_client, **overrides)
    assert response.status_code == 422
    assert message in response.json()["detail"]


def test_links(media_client):
    reel = media_client.post(
        "/media/links",
        json={"asset_type": "acting_reel", "url": "https://vimeo.com/123", "label": "2026 reel"},
    )
    assert reel.status_code == 201
    body = reel.json()
    assert (body["external_url"], body["upload_status"], body["view_url"]) == (
        "https://vimeo.com/123",
        "completed",
        None,
    )
    no_links = media_client.post(
        "/media/links", json={"asset_type": "headshot", "url": "https://example.com/a.jpg"}
    )
    assert no_links.status_code == 422
    not_a_url = media_client.post(
        "/media/links", json={"asset_type": "social_link", "url": "javascript:alert(1)"}
    )
    assert not_a_url.status_code == 422


def test_archive_relabel_and_order(media_client):
    old = media_client.post(
        "/media/links", json={"asset_type": "social_link", "url": "https://instagram.com/a"}
    ).json()
    new = media_client.post(
        "/media/links", json={"asset_type": "social_link", "url": "https://tiktok.com/@a"}
    ).json()
    archived = media_client.patch(f"/media/{old['id']}", json={"is_current": False}).json()
    assert archived["is_current"] is False
    relabeled = media_client.patch(f"/media/{new['id']}", json={"label": " TikTok "}).json()
    assert relabeled["label"] == "TikTok" and relabeled["is_current"] is True
    # Current first within a type.
    assert [a["id"] for a in media_client.get("/media").json()] == [new["id"], old["id"]]
    assert media_client.patch(f"/media/{old['id']}", json={"is_current": None}).status_code == 422


def test_delete_removes_the_file(media_client, store):
    started = start(media_client).json()
    browser_upload(store, started)
    asset_id = started["asset"]["id"]
    media_client.post(f"/media/{asset_id}/complete")
    key = started["upload"]["fields"]["key"]

    assert media_client.delete(f"/media/{asset_id}").status_code == 204
    assert store.object_size(key) is None
    assert media_client.get("/media").json() == []
    assert media_client.delete(f"/media/{asset_id}").status_code == 404


def test_media_needs_a_profile(client, app, store):
    app.dependency_overrides[get_media_store] = lambda: store
    assert start(client).status_code == 409


def test_media_requires_login(anon_client):
    assert anon_client.get("/media").status_code == 401


def test_sweep_settles_stale_pending_uploads(media_client, store, db):
    landed = start(media_client).json()
    browser_upload(store, landed)
    abandoned = start(media_client).json()
    fresh = start(media_client).json()

    old = datetime.now(UTC) - PENDING_UPLOAD_GRACE - timedelta(minutes=1)
    for started in (landed, abandoned):
        db.get(MediaAsset, started["asset"]["id"]).created_at = old
    db.flush()

    result = run_media_sweep(db, store)
    assert (result.completed, result.removed, result.unresolved) == (1, 1, 0)
    rows = {a.id: a for a in db.scalars(select(MediaAsset)).all()}
    assert rows[landed["asset"]["id"]].upload_status == "completed"
    assert abandoned["asset"]["id"] not in rows
    assert rows[fresh["asset"]["id"]].upload_status == "pending"  # still in its grace period


def test_sweep_never_deletes_on_an_ambiguous_error(media_client, store, db, monkeypatch):
    started = start(media_client).json()
    db.get(MediaAsset, started["asset"]["id"]).created_at = datetime.now(UTC) - timedelta(hours=1)
    db.flush()

    def flaky(key):
        raise TimeoutError("S3 timed out")

    monkeypatch.setattr(store, "object_size", flaky)
    result = run_media_sweep(db, store)
    assert (result.removed, result.unresolved) == (0, 1)
    assert db.get(MediaAsset, started["asset"]["id"]).upload_status == "pending"

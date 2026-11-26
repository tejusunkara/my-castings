"""The media library: headshots, digitals, reels, self-tapes, resume, social links.

Uploading a file is three steps, so large videos go straight from the browser to S3:
1. POST /media/uploads   -> a pending row plus a signed upload form
2. the browser POSTs the file to S3 with that form
3. POST /media/{id}/complete -> the API checks S3 has it, and marks it completed
A pending row whose upload never finished is cleaned up by the media sweep.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.deps import DB
from app.models import MediaAsset
from app.schemas.media import (
    LinkRequest,
    MediaAssetOut,
    MediaPatch,
    UploadFormOut,
    UploadRequest,
    UploadStarted,
)
from app.services.media import MediaRuleError, check_link, check_upload, object_key
from app.services.media_store import MediaStore, get_media_store
from app.services.profile import get_profile

router = APIRouter(prefix="/media", tags=["media"])

Store = Annotated[MediaStore, Depends(get_media_store)]


def _out(asset: MediaAsset, store: MediaStore) -> MediaAssetOut:
    out = MediaAssetOut.model_validate(asset)
    if asset.s3_key and asset.upload_status == "completed":
        out.view_url = store.view_url(asset.s3_key, asset.original_filename)
    return out


def _get(db, asset_id: int) -> MediaAsset:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "media not found")
    return asset


def _profile_id(db) -> int:
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "create your profile before adding media")
    return profile.id


def _rule_error(exc: MediaRuleError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


@router.get("", response_model=list[MediaAssetOut])
def list_media(db: DB, store: Store):
    assets = db.scalars(
        select(MediaAsset).order_by(
            MediaAsset.asset_type, MediaAsset.is_current.desc(), MediaAsset.created_at.desc()
        )
    ).all()
    return [_out(a, store) for a in assets]


@router.post("/uploads", response_model=UploadStarted, status_code=status.HTTP_201_CREATED)
def start_upload(body: UploadRequest, db: DB, store: Store):
    try:
        rule = check_upload(body.asset_type, body.content_type, body.size_bytes)
    except MediaRuleError as exc:
        raise _rule_error(exc) from exc
    key = object_key(body.asset_type, body.content_type)
    asset = MediaAsset(
        profile_id=_profile_id(db),
        asset_type=body.asset_type,
        s3_bucket=store.bucket,
        s3_key=key,
        content_type=body.content_type,
        file_size_bytes=body.size_bytes,
        original_filename=body.filename,
        label=body.label or None,
        upload_status="pending",
    )
    db.add(asset)
    db.commit()
    form = store.upload_form(key, body.content_type, rule.max_bytes)
    return UploadStarted(
        asset=_out(asset, store), upload=UploadFormOut(url=form.url, fields=form.fields)
    )


@router.post("/{asset_id}/complete", response_model=MediaAssetOut)
def complete_upload(asset_id: int, db: DB, store: Store):
    asset = _get(db, asset_id)
    if asset.s3_key is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "links have nothing to upload")
    if asset.upload_status != "completed":
        size = store.object_size(asset.s3_key)
        if size is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "the file hasn't reached storage yet")
        asset.file_size_bytes = size
        asset.upload_status = "completed"
        asset.completed_at = datetime.now(UTC)
        db.commit()
    return _out(asset, store)


@router.post("/links", response_model=MediaAssetOut, status_code=status.HTTP_201_CREATED)
def add_link(body: LinkRequest, db: DB, store: Store):
    try:
        check_link(body.asset_type)
    except MediaRuleError as exc:
        raise _rule_error(exc) from exc
    now = datetime.now(UTC)
    asset = MediaAsset(
        profile_id=_profile_id(db),
        asset_type=body.asset_type,
        external_url=str(body.url),
        label=body.label or None,
        upload_status="completed",
        completed_at=now,
    )
    db.add(asset)
    db.commit()
    return _out(asset, store)


@router.patch("/{asset_id}", response_model=MediaAssetOut)
def update_media(asset_id: int, body: MediaPatch, db: DB, store: Store):
    asset = _get(db, asset_id)
    changes = body.model_dump(exclude_unset=True)
    if "is_current" in changes:
        if changes["is_current"] is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "is_current can't be null")
        asset.is_current = changes["is_current"]
    if "label" in changes:
        asset.label = changes["label"] or None
    db.commit()
    return _out(asset, store)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(asset_id: int, db: DB, store: Store):
    asset = _get(db, asset_id)
    # The file goes first: if that fails the row stays, so nothing is left orphaned and
    # invisible in the bucket.
    if asset.s3_key:
        store.delete(asset.s3_key)
    db.delete(asset)
    db.commit()

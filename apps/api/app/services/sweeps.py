"""Periodic sweeps. The match sweep keeps saved_matches in step with roles and the
profile; the media sweep settles uploads that were started but never confirmed.

Match sweep:

Idempotent and safe to run any time (daily at 9am in production, after profile edits,
by the seed script):
- Roles with no saved_matches row are evaluated; matches get a 'new' row. Roles that
  don't match get no row, so they're re-evaluated on the next run (e.g. after the
  profile is edited).
- Existing 'new' rows are re-evaluated too: one that no longer matches (the profile
  changed) is removed, and a still-matching one gets fresh match_reasons. Rows the user
  has acted on (saved/applied/dismissed) are never touched.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.models import MediaAsset, Role, SavedMatch
from app.services.matching import evaluate_role
from app.services.profile import get_profile

if TYPE_CHECKING:
    from app.services.media_store import MediaStore

log = logging.getLogger(__name__)


@dataclass
class MatchSweepResult:
    evaluated: int = 0
    created: int = 0
    removed: int = 0  # stale 'new' matches that no longer fit the profile
    skipped_no_profile: bool = False


def run_match_sweep(db: Session) -> MatchSweepResult:
    result = MatchSweepResult()
    profile = get_profile(db)
    if profile is None:
        result.skipped_no_profile = True
        return result

    unmatched = db.scalars(
        select(Role)
        .where(~exists().where(SavedMatch.role_id == Role.id))
        .options(selectinload(Role.casting_call))
    ).all()
    for role in unmatched:
        result.evaluated += 1
        match = evaluate_role(role, profile)
        if match.is_match:
            # ON CONFLICT: a concurrent sweep may have inserted the row first.
            inserted_id = db.execute(
                insert(SavedMatch)
                .values(role_id=role.id, status="new", match_reasons=match.reasons)
                .on_conflict_do_nothing(index_elements=["role_id"])
                .returning(SavedMatch.id)
            ).scalar_one_or_none()
            result.created += inserted_id is not None

    untouched = db.scalars(
        select(SavedMatch)
        .where(SavedMatch.status == "new")
        .options(selectinload(SavedMatch.role).selectinload(Role.casting_call))
    ).all()
    for saved in untouched:
        result.evaluated += 1
        match = evaluate_role(saved.role, profile)
        if not match.is_match:
            db.delete(saved)
            result.removed += 1
        elif saved.match_reasons != match.reasons:
            saved.match_reasons = match.reasons

    db.flush()
    return result


# A pending upload younger than this may still be in flight.
PENDING_UPLOAD_GRACE = timedelta(minutes=30)


@dataclass
class MediaSweepResult:
    completed: int = 0  # the file had arrived; the browser just never confirmed
    removed: int = 0  # S3 says the file doesn't exist: the upload was abandoned
    unresolved: int = 0  # S3 couldn't say (timeout, throttling): try again next run


def run_media_sweep(
    db: Session, store: "MediaStore", now: datetime | None = None
) -> MediaSweepResult:
    """Settles pending uploads older than the grace period (see app/models/profile.py).

    Only an explicit "not found" from S3 deletes a row. Any other error leaves it pending,
    so a transient failure never loses an upload that actually landed.
    """
    now = now or datetime.now(UTC)
    result = MediaSweepResult()
    stale = db.scalars(
        select(MediaAsset).where(
            MediaAsset.upload_status == "pending",
            MediaAsset.created_at < now - PENDING_UPLOAD_GRACE,
        )
    ).all()
    for asset in stale:
        try:
            size = store.object_size(asset.s3_key)
        except Exception:
            log.warning("media sweep: couldn't check %s; leaving it pending", asset.s3_key)
            result.unresolved += 1
            continue
        if size is None:
            db.delete(asset)
            result.removed += 1
        else:
            asset.file_size_bytes = size
            asset.upload_status = "completed"
            asset.completed_at = now
            result.completed += 1
    db.flush()
    return result

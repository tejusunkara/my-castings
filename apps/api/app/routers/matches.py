from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DB
from app.models import CastingCall, Role, SavedMatch
from app.schemas.matches import MatchOut, MatchPatch, MatchStatus

router = APIRouter(prefix="/matches", tags=["matches"])

_EAGER = (
    selectinload(SavedMatch.role).selectinload(Role.casting_call).selectinload(CastingCall.source)
)


@router.get("", response_model=list[MatchOut])
def list_matches(
    db: DB,
    status_filter: Annotated[MatchStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(SavedMatch).options(_EAGER)
    if status_filter is not None:
        query = query.where(SavedMatch.status == status_filter)
    query = query.order_by(SavedMatch.matched_at.desc(), SavedMatch.id.desc())
    return db.scalars(query.limit(limit).offset(offset)).all()


@router.patch("/{match_id}", response_model=MatchOut)
def update_match(match_id: int, body: MatchPatch, db: DB):
    match = db.get(SavedMatch, match_id, options=[_EAGER])
    if match is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "match not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("status", match.status) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "status cannot be null")

    if "status" in changes and changes["status"] != match.status:
        # applied_at records when the artist applied; it goes away if they undo it.
        match.applied_at = datetime.now(UTC) if changes["status"] == "applied" else None
        match.status = changes["status"]
    if "user_note" in changes:
        match.user_note = changes["user_note"]
    db.commit()
    return match

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.orm import selectinload

from app.deps import DB
from app.models import CastingCall, CastingSource, Role, SavedMatch
from app.models.matches import MATCH_STATUSES
from app.schemas.matches import MatchOut, MatchPatch, MatchStatus, MatchSummary, SourceOut

router = APIRouter(prefix="/matches", tags=["matches"])

_EAGER = (
    selectinload(SavedMatch.role).selectinload(Role.casting_call).selectinload(CastingCall.source)
)

MatchSort = Literal["deadline", "matched", "posted"]


@dataclass
class MatchFilters:
    """Filters shared by the list and the summary. Status is applied separately, so the
    summary can count every status under the other filters."""

    source: Annotated[list[str] | None, Query(description="casting source keys")] = None
    project_type: Annotated[str | None, Query(max_length=200)] = None
    q: Annotated[str | None, Query(max_length=200, description="title, role name or location")] = (
        None
    )

    def apply(self, query: Select) -> Select:
        query = query.join(SavedMatch.role).join(Role.casting_call).join(CastingCall.source)
        if self.source:
            query = query.where(CastingSource.key.in_(self.source))
        if self.project_type:
            query = query.where(CastingCall.project_type == self.project_type)
        if self.q and self.q.strip():
            pattern = f"%{_escape_like(self.q.strip())}%"
            query = query.where(
                or_(
                    CastingCall.title.ilike(pattern, escape="\\"),
                    Role.role_name.ilike(pattern, escape="\\"),
                    func.array_to_string(CastingCall.seeking_locations, " ").ilike(
                        pattern, escape="\\"
                    ),
                )
            )
        return query


Filters = Annotated[MatchFilters, Depends()]


@router.get("", response_model=list[MatchOut])
def list_matches(
    db: DB,
    filters: Filters,
    status_filter: Annotated[list[MatchStatus] | None, Query(alias="status")] = None,
    sort: MatchSort = "matched",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = filters.apply(select(SavedMatch).options(_EAGER))
    if status_filter:
        query = query.where(SavedMatch.status.in_(status_filter))
    query = query.order_by(*_ORDER[sort](), SavedMatch.matched_at.desc(), SavedMatch.id.desc())
    return db.scalars(query.limit(limit).offset(offset)).all()


@router.get("/summary", response_model=MatchSummary)
def match_summary(db: DB, filters: Filters):
    """Counts per status under the given filters, plus the options the filters offer."""
    counts = dict(
        db.execute(
            filters.apply(select(SavedMatch.status, func.count())).group_by(SavedMatch.status)
        ).all()
    )
    project_types = db.scalars(
        select(CastingCall.project_type)
        .join(CastingCall.roles)
        .join(Role.saved_match)
        .where(CastingCall.project_type.is_not(None))
        .distinct()
    ).all()
    sources = db.scalars(
        select(CastingSource).where(CastingSource.is_active).order_by(CastingSource.display_name)
    ).all()
    return MatchSummary(
        status_counts={s: counts.get(s, 0) for s in MATCH_STATUSES},
        # Sorted here, not in SQL, so the order doesn't depend on the database collation.
        project_types=sorted(project_types, key=str.casefold),
        sources=[SourceOut.model_validate(s) for s in sources],
    )


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


def _deadline_order():
    """Open deadlines soonest first, then roles with no deadline, then closed ones
    (most recently closed first), so 'soonest' never leads with expired roles."""
    deadline = CastingCall.submission_deadline
    is_open = deadline >= func.now()
    return (
        case((is_open, 0), (deadline.is_(None), 1), else_=2),
        case((is_open, deadline)).asc(),
        deadline.desc(),
    )


_ORDER = {
    "deadline": _deadline_order,
    "matched": lambda: (),
    "posted": lambda: (CastingCall.posted_at.desc().nulls_last(),),
}


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

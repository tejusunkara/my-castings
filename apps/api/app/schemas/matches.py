from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.casting import CastingCallSummary, RoleOut

MatchStatus = Literal["new", "saved", "applied", "dismissed"]


class MatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: MatchStatus
    matched_at: datetime
    match_reasons: dict[str, bool]
    user_note: str | None
    applied_at: datetime | None
    role: RoleOut
    casting_call: CastingCallSummary


class MatchPatch(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    status: MatchStatus | None = None
    user_note: str | None = None


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    display_name: str


class MatchSummary(BaseModel):
    # Every status is present, zero included.
    status_counts: dict[MatchStatus, int]
    # Project types that occur among matches, for the filter dropdown.
    project_types: list[str]
    sources: list[SourceOut]

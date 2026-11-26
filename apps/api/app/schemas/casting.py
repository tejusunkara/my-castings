from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role_name: str
    billing_type: str | None
    genders: list[str]
    age_min: int | None
    age_max: int | None
    is_featured: bool
    pay: str | None
    # Personalized to the artist's account: open it, never share it.
    apply_url: str | None


class CastingCallSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_key: str
    title: str
    category_tag: str | None
    project_type: str | None
    union_status: str | None
    posted_at: datetime | None
    submission_deadline: datetime | None
    seeking_locations: list[str]
    is_featured: bool
    view_all_jobs_url: str | None


class RoleMatchOut(BaseModel):
    """The match state of a role, for views that start from the casting call."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    status: Literal["new", "saved", "applied", "dismissed"]
    user_note: str | None
    applied_at: datetime | None


class RoleDetailOut(RoleOut):
    # None when the role didn't match the profile.
    saved_match: RoleMatchOut | None


class CastingCallOut(CastingCallSummary):
    description: str | None
    roles: list[RoleDetailOut]

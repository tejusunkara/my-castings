from datetime import datetime

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


class CastingCallOut(CastingCallSummary):
    description: str | None
    roles: list[RoleOut]

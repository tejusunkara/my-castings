from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RawEmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    s3_bucket: str
    s3_key: str
    received_at: datetime
    subject: str | None
    from_address: str | None
    source_key: str | None
    sender_verified: bool
    verdict_details: dict[str, Any] | None
    parse_status: str
    parse_error: str | None
    parsed_at: datetime | None


class ReprocessOut(BaseModel):
    raw_email: RawEmailOut
    created_roles: int
    updated_roles: int
    deleted_roles: int
    # Roles the new parse no longer contains, kept because you acted on their match.
    kept_role_ids: list[int]
    new_matches: int

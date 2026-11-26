from datetime import datetime
from typing import Annotated, Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, StringConstraints

AssetType = Literal["headshot", "digital", "acting_reel", "self_tape", "resume", "social_link"]
Label = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_type: AssetType
    label: str | None
    is_current: bool
    upload_status: Literal["pending", "completed"]
    content_type: str | None
    file_size_bytes: int | None
    original_filename: str | None
    external_url: str | None
    created_at: datetime
    completed_at: datetime | None
    # Signed link to the stored file, valid for an hour. None for links and pending uploads.
    view_url: str | None = None


class UploadRequest(BaseModel):
    asset_type: AssetType
    filename: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    content_type: str
    size_bytes: Annotated[int, Field(gt=0)]
    label: Label | None = None


class UploadFormOut(BaseModel):
    url: str
    # Send every field, then the file last, as multipart/form-data.
    fields: dict[str, str]


class UploadStarted(BaseModel):
    asset: MediaAssetOut
    upload: UploadFormOut


class LinkRequest(BaseModel):
    asset_type: AssetType
    url: Annotated[AnyHttpUrl, Field(max_length=2000)]
    label: Label | None = None


class MediaPatch(BaseModel):
    """Partial update: only fields present in the request body are changed."""

    label: Label | None = None
    is_current: bool | None = None

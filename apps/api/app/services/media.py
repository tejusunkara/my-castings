"""What each media type accepts, and how stored files are named.

| type        | files                     | links |
|-------------|---------------------------|-------|
| headshot    | JPEG/PNG/WebP, 25 MB      | no    |
| digital     | JPEG/PNG/WebP, 25 MB      | no    |
| acting_reel | MP4/MOV, 2 GB             | yes   |
| self_tape   | MP4/MOV, 2 GB             | yes   |
| resume      | PDF, 10 MB                | no    |
| social_link | none                      | yes   |
"""

import uuid
from dataclasses import dataclass

MB = 1024 * 1024

IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
VIDEO_TYPES = {"video/mp4": ".mp4", "video/quicktime": ".mov"}
PDF_TYPES = {"application/pdf": ".pdf"}


@dataclass(frozen=True)
class MediaRule:
    file_types: dict[str, str]  # content type -> file extension
    max_bytes: int = 0
    links: bool = False


RULES: dict[str, MediaRule] = {
    "headshot": MediaRule(IMAGE_TYPES, 25 * MB),
    "digital": MediaRule(IMAGE_TYPES, 25 * MB),
    "acting_reel": MediaRule(VIDEO_TYPES, 2048 * MB, links=True),
    "self_tape": MediaRule(VIDEO_TYPES, 2048 * MB, links=True),
    "resume": MediaRule(PDF_TYPES, 10 * MB),
    "social_link": MediaRule({}, links=True),
}


class MediaRuleError(ValueError):
    pass


def check_upload(asset_type: str, content_type: str, size_bytes: int) -> MediaRule:
    rule = RULES[asset_type]
    if not rule.file_types:
        raise MediaRuleError(f"{asset_type} takes links, not files")
    if content_type not in rule.file_types:
        allowed = ", ".join(sorted(rule.file_types))
        raise MediaRuleError(f"{asset_type} files must be one of: {allowed}")
    if size_bytes > rule.max_bytes:
        raise MediaRuleError(f"{asset_type} files can be at most {rule.max_bytes // MB} MB")
    return rule


def check_link(asset_type: str) -> None:
    if not RULES[asset_type].links:
        raise MediaRuleError(f"{asset_type} takes file uploads, not links")


def object_key(asset_type: str, content_type: str) -> str:
    """Random, so names never collide or reveal anything; the original filename is kept
    in the database for display and downloads."""
    return f"media/{asset_type}/{uuid.uuid4()}{RULES[asset_type].file_types[content_type]}"

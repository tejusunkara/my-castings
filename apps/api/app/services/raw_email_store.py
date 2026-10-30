"""Fetches the original MIME bytes for a raw_emails row."""

from pathlib import Path

from app.config import get_settings
from app.models import RawEmail

LOCAL_BUCKET = "local"


class RawEmailNotFoundError(Exception):
    pass


def read_raw_email(raw_email: RawEmail) -> bytes:
    if raw_email.s3_bucket == LOCAL_BUCKET:
        return _read_local(get_settings().raw_email_local_dir, raw_email.s3_key)
    # The S3-backed read arrives with the AWS infrastructure (Phase 1b).
    raise NotImplementedError(f"no store for bucket {raw_email.s3_bucket!r} yet")


def _read_local(base_dir: Path, key: str) -> bytes:
    base = base_dir.resolve()
    path = (base / key).resolve()
    if not path.is_relative_to(base):
        raise RawEmailNotFoundError(f"key escapes the local store: {key!r}")
    if not path.is_file():
        raise RawEmailNotFoundError(f"no local raw email at {key!r}")
    return path.read_bytes()

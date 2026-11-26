"""Fetches the original MIME bytes for a raw_emails row: from S3 on AWS, or from a local
directory for rows whose bucket is "local" (development and the seed script)."""

from pathlib import Path

from botocore.exceptions import ClientError

from app.config import get_settings
from app.models import RawEmail
from app.services.media_store import s3_client

LOCAL_BUCKET = "local"


class RawEmailNotFoundError(Exception):
    pass


def read_raw_email(raw_email: RawEmail, s3=None) -> bytes:
    if raw_email.s3_bucket == LOCAL_BUCKET:
        return _read_local(get_settings().raw_email_local_dir, raw_email.s3_key)
    return read_s3_object(raw_email.s3_bucket, raw_email.s3_key, s3)


def read_s3_object(bucket: str, key: str, s3=None) -> bytes:
    s3 = s3 or s3_client(get_settings())
    try:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            raise RawEmailNotFoundError(f"no object s3://{bucket}/{key}") from exc
        raise


def _read_local(base_dir: Path, key: str) -> bytes:
    base = base_dir.resolve()
    path = (base / key).resolve()
    if not path.is_relative_to(base):
        raise RawEmailNotFoundError(f"key escapes the local store: {key!r}")
    if not path.is_file():
        raise RawEmailNotFoundError(f"no local raw email at {key!r}")
    return path.read_bytes()

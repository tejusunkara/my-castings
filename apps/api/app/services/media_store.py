"""The media bucket: signed upload forms, signed view links, existence checks, deletes.

The browser uploads straight to S3 with a presigned POST, so large videos never pass
through the API. The POST policy pins the object key, the content type and a size range,
and S3 itself rejects anything else: limits hold even if the page is bypassed.

Locally the same code talks to RustFS (S3-compatible, from docker-compose.yml).
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import Settings, get_settings

UPLOAD_FORM_TTL_SECONDS = 15 * 60
VIEW_LINK_TTL_SECONDS = 60 * 60

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


@dataclass
class UploadForm:
    url: str
    fields: dict[str, str]


class MediaStore:
    def __init__(self, settings: Settings, client: Any | None = None):
        self.bucket = settings.media_bucket
        self.cors_origins = settings.media_cors_origins
        self.client = client or boto3.client(
            "s3",
            region_name=settings.s3_region,
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=_secret(settings.s3_access_key_id),
            aws_secret_access_key=_secret(settings.s3_secret_access_key),
            # Path-style keeps local endpoints (http://localhost:9000/bucket/key) working.
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def upload_form(self, key: str, content_type: str, max_bytes: int) -> UploadForm:
        post = self.client.generate_presigned_post(
            self.bucket,
            key,
            Fields={"Content-Type": content_type},
            Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, max_bytes]],
            ExpiresIn=UPLOAD_FORM_TTL_SECONDS,
        )
        return UploadForm(url=post["url"], fields=post["fields"])

    def view_url(self, key: str, filename: str | None) -> str:
        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            # Shown inline, but "Save as" uses the original name rather than the key.
            safe = filename.replace('"', "").replace("\\", "")
            params["ResponseContentDisposition"] = f'inline; filename="{safe}"'
        return self.client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=VIEW_LINK_TTL_SECONDS
        )

    def object_size(self, key: str) -> int | None:
        """Size in bytes, or None when S3 says the object does not exist. Any other
        failure raises: callers must not treat a timeout as "missing"."""
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)["ContentLength"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in _NOT_FOUND:
                return None
            raise

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def ensure_bucket(self) -> None:
        """Local setup: create the bucket and allow the dev origin to upload and view.
        On AWS the bucket and its CORS rules come from CDK instead."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.client.create_bucket(Bucket=self.bucket)
        self.client.put_bucket_cors(
            Bucket=self.bucket,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedOrigins": self.cors_origins,
                        "AllowedMethods": ["GET", "HEAD", "POST"],
                        "AllowedHeaders": ["*"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )


def _secret(value) -> str | None:
    return value.get_secret_value() if value is not None else None


@lru_cache
def _default_store() -> MediaStore:
    return MediaStore(get_settings())


def get_media_store() -> MediaStore:
    """FastAPI dependency; tests override it."""
    return _default_store()

"""AWS Lambda entry point for the email pipeline.

SES saves each forwarded email to the raw-email bucket under inbound/; S3 tells
EventBridge, which invokes this function with an "Object Created" event. For each email:
read it from S3, record a raw_emails row, ingest it (verify sender, parse, store) and run
the match sweep so new matches show up at once.

Delivery is at least once, so the same object can arrive twice. The raw_emails row is
claimed with INSERT ... ON CONFLICT DO NOTHING on (bucket, key): a repeat does nothing.
A bad email never raises (ingest() records it as failed); only infrastructure errors (S3,
database) raise, so Lambda retries them and finally parks the event in the dead-letter
queue, which alerts by email. The email itself stays in S3 either way.
"""

import json
import logging
import os
from datetime import datetime
from urllib.parse import unquote_plus

import boto3


def _load_database_credentials() -> None:
    """The function gets the ARN of the secret RDS generated, not the password itself.
    Read it once per cold start, before app settings are first loaded."""
    arn = os.environ.get("MY_CASTINGS_DB_SECRET_ARN")
    if not arn or os.environ.get("MY_CASTINGS_DB_PASSWORD"):
        return
    secret = json.loads(
        boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]
    )
    os.environ.update(
        MY_CASTINGS_DB_HOST=secret["host"],
        MY_CASTINGS_DB_PORT=str(secret["port"]),
        MY_CASTINGS_DB_NAME=secret["dbname"],
        MY_CASTINGS_DB_USER=secret["username"],
        MY_CASTINGS_DB_PASSWORD=secret["password"],
    )


_load_database_credentials()

from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models import RawEmail  # noqa: E402
from app.services.ingestion import ingest  # noqa: E402
from app.services.raw_email_store import RawEmailNotFoundError, read_s3_object  # noqa: E402
from app.services.sweeps import run_match_sweep  # noqa: E402
from ingestion_core.parsing.mime import load_message, sent_at  # noqa: E402

log = logging.getLogger()
log.setLevel(logging.INFO)


def handler(event: dict, context: object = None) -> dict:
    detail = event["detail"]
    return process(
        detail["bucket"]["name"],
        detail["object"]["key"],
        datetime.fromisoformat(event["time"].replace("Z", "+00:00")),
    )


def process(bucket: str, key: str, event_time: datetime, s3=None) -> dict:
    raw_mime, key = _read(bucket, key, s3)
    received_at = sent_at(load_message(raw_mime)) or event_time

    with SessionLocal.begin() as db:
        claimed = db.execute(
            insert(RawEmail)
            .values(s3_bucket=bucket, s3_key=key, received_at=received_at)
            .on_conflict_do_nothing(constraint="uq_raw_emails_s3_object")
            .returning(RawEmail.id)
        ).scalar_one_or_none()
        if claimed is None:
            log.info("already ingested s3://%s/%s; nothing to do", bucket, key)
            return {"key": key, "status": "duplicate"}

        raw_email = db.get(RawEmail, claimed)
        result = ingest(db, raw_email, raw_mime)
        sweep = run_match_sweep(db)
        summary = {
            "key": key,
            "status": raw_email.parse_status,
            "source": raw_email.source_key,
            "error": raw_email.parse_error,
            "created_roles": result.created_roles,
            "new_matches": sweep.created,
        }
    log.info(json.dumps(summary))
    return summary


def _read(bucket: str, key: str, s3) -> tuple[bytes, str]:
    """S3 event keys can arrive URL-encoded; try the key as given, then decoded."""
    try:
        return read_s3_object(bucket, key, s3), key
    except RawEmailNotFoundError:
        decoded = unquote_plus(key)
        if decoded == key:
            raise
        return read_s3_object(bucket, decoded, s3), decoded

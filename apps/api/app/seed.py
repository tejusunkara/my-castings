"""Local development seed: `uv run python -m app.seed` (from apps/api).

Replays every .eml in the local raw-email directory through the real ingestion path,
creates the artist profile if none exists (never overwrites one edited in the app), and
runs the match sweep. Safe to re-run: existing emails are reprocessed in place.
"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import RawEmail
from app.services.ingestion import ingest
from app.services.profile import get_profile, upsert_profile
from app.services.raw_email_store import LOCAL_BUCKET
from app.services.sweeps import run_match_sweep
from ingestion_core.parsing.mime import load_message, sent_at

DEFAULT_PROFILE = {
    "playing_age_min": 16,
    "playing_age_max": 30,
    "genders": ["female", "any gender", "femme presenting"],
    "location_city": "New York City",
    "location_state": "NY",
    "willing_to_travel": True,
}


def seed() -> None:
    directory = get_settings().raw_email_local_dir
    with SessionLocal.begin() as db:
        for path in sorted(directory.glob("*.eml")):
            raw_mime = path.read_bytes()
            raw_email = db.scalars(
                select(RawEmail).where(
                    RawEmail.s3_bucket == LOCAL_BUCKET, RawEmail.s3_key == path.name
                )
            ).one_or_none()
            if raw_email is None:
                received = sent_at(load_message(raw_mime)) or datetime.now(UTC)
                raw_email = RawEmail(s3_bucket=LOCAL_BUCKET, s3_key=path.name, received_at=received)
                db.add(raw_email)
            result = ingest(db, raw_email, raw_mime)
            print(
                f"{path.name}: {raw_email.parse_status}"
                + (f" ({raw_email.parse_error})" if raw_email.parse_error else "")
                + f" +{result.created_roles} roles"
            )

        if get_profile(db) is None:
            upsert_profile(db, DEFAULT_PROFILE)
            print("created artist profile")
        sweep = run_match_sweep(db)
        print(f"match sweep: {sweep}")


if __name__ == "__main__":
    seed()

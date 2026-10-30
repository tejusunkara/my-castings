"""The single artist profile. No DB constraint enforces one row (so a user_id column
can be added later as an additive migration); these functions are the enforcement:
every read and write goes through "the one row if it exists, else create it"."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ArtistProfile


def get_profile(db: Session) -> ArtistProfile | None:
    return db.scalars(select(ArtistProfile).order_by(ArtistProfile.id).limit(1)).one_or_none()


def upsert_profile(db: Session, values: dict[str, Any]) -> ArtistProfile:
    profile = get_profile(db)
    if profile is None:
        profile = ArtistProfile()
        db.add(profile)
    for name, value in values.items():
        setattr(profile, name, value)
    db.flush()
    return profile

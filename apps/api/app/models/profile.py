"""The artist profile and its media.

media_assets.upload_status state machine:

    ┌─────────┐  POST /media/{id}/complete,     ┌───────────┐
    │ pending │ ──or sweep finds the S3 object─▶ │ completed │
    └────┬────┘                                  └───────────┘
         │ sweep, row older than 30 min AND S3 HEAD returns an explicit 404
         ▼
      (row deleted)

Any other HEAD failure (timeout, throttling) leaves the row pending for the next sweep:
never delete on an ambiguous error, or a transient blip loses a real upload.

A media asset is either a stored file (s3_key set) or a link (external_url set), never
both. is_current marks what the artist uses today; the rest is the archive.
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text, false, func, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, in_check

ASSET_TYPES = ("headshot", "digital", "acting_reel", "self_tape", "resume", "social_link")
UPLOAD_STATUSES = ("pending", "completed")


class ArtistProfile(Base):
    """Single row in v1. Not enforced in the DB (so adding user_id later is an additive
    migration); the profile service upserts "the one row" instead."""

    __tablename__ = "artist_profile"

    __table_args__ = (
        # Both bounds or neither; a half-set range would match ambiguously.
        CheckConstraint(
            "(playing_age_min IS NULL) = (playing_age_max IS NULL)"
            " AND playing_age_min <= playing_age_max",
            name="playing_age_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    # Reference only. Matching uses the playing range: casting age ranges describe the
    # ages a character reads as, not the actor's real age.
    date_of_birth: Mapped[date | None]
    playing_age_min: Mapped[int | None]
    playing_age_max: Mapped[int | None]
    # Role gender labels this artist wants matched, e.g. ["female", "femme presenting"].
    # Compared via ingestion_core's gender_key, so "Femme-Presenting" matches too.
    genders: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    location_city: Mapped[str | None] = mapped_column(Text)
    location_state: Mapped[str | None] = mapped_column(Text)
    union_status: Mapped[str | None] = mapped_column(Text)
    bio: Mapped[str | None] = mapped_column(Text)
    willing_to_travel: Mapped[bool] = mapped_column(server_default=false())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    media_assets: Mapped[list["MediaAsset"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )

    def age_on(self, day: date) -> int | None:
        if self.date_of_birth is None:
            return None
        dob = self.date_of_birth
        return day.year - dob.year - ((day.month, day.day) < (dob.month, dob.day))


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(in_check("asset_type", ASSET_TYPES), name="asset_type"),
        CheckConstraint(in_check("upload_status", UPLOAD_STATUSES), name="upload_status"),
        CheckConstraint("(s3_key IS NULL) <> (external_url IS NULL)", name="file_or_link"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("artist_profile.id", ondelete="CASCADE"), index=True
    )
    asset_type: Mapped[str] = mapped_column(Text)
    s3_bucket: Mapped[str | None] = mapped_column(Text)
    s3_key: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    original_filename: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)  # links: social, hosted reels
    label: Mapped[str | None] = mapped_column(Text)  # e.g. "Commercial", "Theatrical"
    is_current: Mapped[bool] = mapped_column(server_default=true())
    upload_status: Mapped[str] = mapped_column(Text, server_default="pending")
    created_at: Mapped[datetime] = created_at_column()
    completed_at: Mapped[datetime | None]

    profile: Mapped[ArtistProfile] = relationship(back_populates="media_assets")

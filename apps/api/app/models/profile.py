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
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, in_check

ASSET_TYPES = ("headshot", "self_tape", "voice_reel", "social_link")
UPLOAD_STATUSES = ("pending", "completed")


class ArtistProfile(Base):
    """Single row in v1. Not enforced in the DB (so adding user_id later is an additive
    migration); the profile service upserts "the one row" instead."""

    __tablename__ = "artist_profile"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    # DOB rather than age, so matching stays correct as time passes.
    date_of_birth: Mapped[date | None]
    gender: Mapped[str | None] = mapped_column(Text)
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
    external_url: Mapped[str | None] = mapped_column(Text)  # social_link rows
    label: Mapped[str | None] = mapped_column(Text)
    upload_status: Mapped[str] = mapped_column(Text, server_default="pending")
    created_at: Mapped[datetime] = created_at_column()

    profile: Mapped[ArtistProfile] = relationship(back_populates="media_assets")

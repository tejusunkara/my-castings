"""User state for roles that matched the profile.

status state machine (all transitions user-driven; the match sweep only ever inserts
'new' for roles with no row yet, so it never overwrites a user's choice):

    new ──▶ saved ──▶ applied
     │        │
     └────────┴─────▶ dismissed
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, in_check

if TYPE_CHECKING:
    from app.models.casting import CastingCall, Role

MATCH_STATUSES = ("new", "saved", "applied", "dismissed")


class SavedMatch(Base):
    __tablename__ = "saved_matches"
    __table_args__ = (
        CheckConstraint(in_check("status", MATCH_STATUSES), name="status"),
        Index("ix_saved_matches_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique: one row per role keeps the sweep idempotent even under concurrent runs.
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(Text, server_default="new")
    matched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    match_reasons: Mapped[dict[str, Any]] = mapped_column(JSONB)  # {"age": true, ...}
    user_note: Mapped[str | None] = mapped_column(Text)
    applied_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    role: Mapped["Role"] = relationship(back_populates="saved_match")

    @property
    def casting_call(self) -> "CastingCall":
        return self.role.casting_call

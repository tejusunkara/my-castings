from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text, false, true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column

if TYPE_CHECKING:
    from app.models.ingestion import RawEmail
    from app.models.matches import SavedMatch


class CastingSource(Base):
    __tablename__ = "casting_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)  # matches adapter.source_key
    display_name: Mapped[str] = mapped_column(Text)
    sender_domain_match: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=true())


class CastingCall(Base):
    """One posting/project within a digest."""

    __tablename__ = "casting_calls"
    __table_args__ = (Index("ix_casting_calls_posted_at", "posted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Cascade: deleting a raw email removes everything it produced. (Reprocessing does
    # not delete; it updates rows in place, see app/services/ingestion.py.)
    raw_email_id: Mapped[int] = mapped_column(
        ForeignKey("raw_emails.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("casting_sources.id"))
    external_ref: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    category_tag: Mapped[str | None] = mapped_column(Text)  # raw, e.g. "Feature Film · Union"
    project_type: Mapped[str | None] = mapped_column(Text)
    union_status: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None]  # received_at minus "Posted X days, Y hours ago"
    submission_deadline: Mapped[datetime | None]  # absolute, when the source gives one
    seeking_locations: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    is_featured: Mapped[bool] = mapped_column(server_default=false())  # posting-level badge
    view_all_jobs_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    raw_email: Mapped["RawEmail"] = relationship(back_populates="casting_calls")
    source: Mapped[CastingSource] = relationship()
    roles: Mapped[list["Role"]] = relationship(
        back_populates="casting_call",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Role.id",
    )

    @property
    def source_key(self) -> str:
        return self.source.key


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        Index("ix_roles_age_range", "age_min", "age_max"),
        Index("ix_roles_genders", "genders", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    casting_call_id: Mapped[int] = mapped_column(
        ForeignKey("casting_calls.id", ondelete="CASCADE"), index=True
    )
    role_name: Mapped[str] = mapped_column(Text)
    billing_type: Mapped[str | None] = mapped_column(Text)
    # Lower-cased labels; a role can list several ("female", "trans female").
    # Empty means open to any gender.
    genders: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    age_min: Mapped[int | None]
    age_max: Mapped[int | None]
    is_featured: Mapped[bool] = mapped_column(server_default=false())  # role-level badge
    # Personalized/tokenized link; stored exactly as received, never shared.
    apply_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    casting_call: Mapped[CastingCall] = relationship(back_populates="roles")
    saved_match: Mapped["SavedMatch | None"] = relationship(
        back_populates="role", cascade="all, delete-orphan", passive_deletes=True
    )

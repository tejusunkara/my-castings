"""Every inbound email, kept regardless of parse outcome.

parse_status state machine (mirrored in apps/ingestion_lambda/handler.py):

                    ┌─────────┐
                    │ pending │  (row created on S3 ObjectCreated, before parse attempt)
                    └────┬────┘
                         │ Lambda attempts parse
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌─────────┐ ┌─────────┐ ┌────────┐
        │ success │ │ partial │ │ failed │
        └─────────┘ └────┬────┘ └───┬────┘
                         │          │ admin clicks "reprocess"
                         │          ▼
                         │     ┌─────────┐
                         └────▶│ pending │ (re-enters the loop; a fixed
                               └─────────┘  parser can turn failed → success)

partial = stored what parsed; parse_error names the field(s) that didn't.
failed  = whole email unparseable, or AmbiguousAdapterMatchError.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, created_at_column, in_check

if TYPE_CHECKING:
    from app.models.casting import CastingCall, CastingSource

PARSE_STATUSES = ("pending", "success", "partial", "failed")


class RawEmail(Base):
    __tablename__ = "raw_emails"
    __table_args__ = (
        UniqueConstraint("s3_bucket", "s3_key", name="uq_raw_emails_s3_object"),
        CheckConstraint(in_check("parse_status", PARSE_STATUSES), name="parse_status"),
        Index("ix_raw_emails_parse_status", "parse_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    s3_bucket: Mapped[str] = mapped_column(Text)
    s3_key: Mapped[str] = mapped_column(Text)
    # Only linked when sender_verified is true; a matching From domain alone isn't trusted.
    source_id: Mapped[int | None] = mapped_column(ForeignKey("casting_sources.id"))
    received_at: Mapped[datetime]
    subject: Mapped[str | None] = mapped_column(Text)
    from_address: Mapped[str | None] = mapped_column(Text)
    sender_verified: Mapped[bool] = mapped_column(server_default=false())
    verdict_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    parse_status: Mapped[str] = mapped_column(Text, server_default="pending")
    parse_error: Mapped[str | None] = mapped_column(Text)
    parsed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at_column()

    source: Mapped["CastingSource | None"] = relationship()
    casting_calls: Mapped[list["CastingCall"]] = relationship(
        back_populates="raw_email", cascade="all, delete-orphan", passive_deletes=True
    )

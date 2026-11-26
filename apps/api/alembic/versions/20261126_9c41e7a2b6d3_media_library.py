"""media library: new asset types, current flag, file-or-link

Revision ID: 9c41e7a2b6d3
Revises: 5b2e9c7d41a8
Create Date: 2026-11-26 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c41e7a2b6d3"
down_revision: str | Sequence[str] | None = "5b2e9c7d41a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TYPES = "('headshot', 'digital', 'acting_reel', 'self_tape', 'resume', 'social_link')"
OLD_TYPES = "('headshot', 'self_tape', 'voice_reel', 'social_link')"


def upgrade() -> None:
    """Asset types become headshot / digital / acting_reel / self_tape / resume /
    social_link (voice_reel goes; no rows used it). Adds is_current, original_filename and
    completed_at, and requires every row to be exactly one of a file or a link."""
    op.drop_constraint(op.f("ck_media_assets_asset_type"), "media_assets", type_="check")
    op.create_check_constraint(
        op.f("ck_media_assets_asset_type"), "media_assets", f"asset_type IN {NEW_TYPES}"
    )
    op.add_column("media_assets", sa.Column("original_filename", sa.Text(), nullable=True))
    op.add_column(
        "media_assets",
        sa.Column("is_current", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "media_assets", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        op.f("ck_media_assets_file_or_link"),
        "media_assets",
        "(s3_key IS NULL) <> (external_url IS NULL)",
    )


def downgrade() -> None:
    """Fails if any row uses a type the old list doesn't have."""
    op.drop_constraint(op.f("ck_media_assets_file_or_link"), "media_assets", type_="check")
    op.drop_column("media_assets", "completed_at")
    op.drop_column("media_assets", "is_current")
    op.drop_column("media_assets", "original_filename")
    op.drop_constraint(op.f("ck_media_assets_asset_type"), "media_assets", type_="check")
    op.create_check_constraint(
        op.f("ck_media_assets_asset_type"), "media_assets", f"asset_type IN {OLD_TYPES}"
    )

"""casting networks source

Revision ID: c4e1a9d2f7b3
Revises: b76a33ee25f4
Create Date: 2026-11-24 16:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e1a9d2f7b3"
down_revision: str | Sequence[str] | None = "b76a33ee25f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Pair the CastingNetworksAdapter (source_key "casting_networks") with its row."""
    op.bulk_insert(
        sa.table(
            "casting_sources",
            sa.column("key", sa.Text),
            sa.column("display_name", sa.Text),
            sa.column("sender_domain_match", sa.Text),
        ),
        [
            {
                "key": "casting_networks",
                "display_name": "Casting Networks",
                "sender_domain_match": "castingnetworks.com",
            }
        ],
    )


def downgrade() -> None:
    """Fails if Casting Networks postings exist (casting_calls.source_id has no cascade)."""
    op.execute("DELETE FROM casting_sources WHERE key = 'casting_networks'")

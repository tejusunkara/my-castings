"""actors access source

Revision ID: 8ae6b638cb32
Revises: c4e1a9d2f7b3
Create Date: 2026-11-26 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ae6b638cb32"
down_revision: str | Sequence[str] | None = "c4e1a9d2f7b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Pair the ActorsAccessAdapter (source_key "actors_access") with its row."""
    op.bulk_insert(
        sa.table(
            "casting_sources",
            sa.column("key", sa.Text),
            sa.column("display_name", sa.Text),
            sa.column("sender_domain_match", sa.Text),
        ),
        [
            {
                "key": "actors_access",
                "display_name": "Actors Access",
                "sender_domain_match": "actorsaccess.com",
            }
        ],
    )


def downgrade() -> None:
    """Fails if Actors Access postings exist (casting_calls.source_id has no cascade)."""
    op.execute("DELETE FROM casting_sources WHERE key = 'actors_access'")

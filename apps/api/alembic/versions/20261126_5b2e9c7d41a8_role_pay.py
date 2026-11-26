"""role pay

Revision ID: 5b2e9c7d41a8
Revises: 8ae6b638cb32
Create Date: 2026-11-26 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b2e9c7d41a8"
down_revision: str | Sequence[str] | None = "8ae6b638cb32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Free-text pay per role. Existing rows stay NULL until their email is reprocessed."""
    op.add_column("roles", sa.Column("pay", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("roles", "pay")

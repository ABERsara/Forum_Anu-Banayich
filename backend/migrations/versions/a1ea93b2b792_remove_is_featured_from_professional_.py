"""remove is_featured from professional_queries

Revision ID: a1ea93b2b792
Revises: c73690be0286
Create Date: 2026-09-06 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1ea93b2b792"
down_revision: str | Sequence[str] | None = "c73690be0286"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("professional_queries", "is_featured")


def downgrade() -> None:
    """Downgrade schema."""
    # server_default so the NOT NULL column can be re-added to a table that
    # already has rows; dropped again right after to match the original schema.
    op.add_column(
        "professional_queries",
        sa.Column(
            "is_featured",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    with op.batch_alter_table("professional_queries") as batch_op:
        batch_op.alter_column("is_featured", server_default=None)

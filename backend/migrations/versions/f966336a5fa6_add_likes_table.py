"""add likes table

Revision ID: f966336a5fa6
Revises: 4fbb595f14de
Create Date: 2026-08-30 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f966336a5fa6"
down_revision: str | Sequence[str] | None = "4fbb595f14de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "likes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "target_type",
            sa.Enum("FORUM_POST", "PROFESSIONAL_QUERY", name="liketargettype"),
            nullable=False,
        ),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("user_id", "target_type", "target_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("likes")

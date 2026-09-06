"""add conversation_key and key_version to direct_messages

Revision ID: 5677b8e5c583
Revises: 4fbb595f14de
Create Date: 2026-08-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5677b8e5c583"
down_revision: str | Sequence[str] | None = "4fbb595f14de"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "direct_messages",
        sa.Column(
            "conversation_key", sa.String(length=80), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "direct_messages",
        sa.Column("key_version", sa.Integer(), nullable=False, server_default="1"),
    )
    # The server_default on conversation_key above only exists to satisfy
    # existing rows during the ALTER; new rows always set it explicitly via
    # the ORM (see app/models/forum.py), so drop the default afterward.
    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.alter_column("conversation_key", server_default=None)

    op.create_index(
        "ix_direct_messages_conversation_created",
        "direct_messages",
        ["conversation_key", "created_at"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_direct_messages_conversation_created", table_name="direct_messages"
    )
    op.drop_column("direct_messages", "key_version")
    op.drop_column("direct_messages", "conversation_key")

"""add recipient/unread index to direct_messages

Revision ID: 71468d6695fb
Revises: cd7c2f0dab77
Create Date: 2026-09-01 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "71468d6695fb"
down_revision: str | Sequence[str] | None = "cd7c2f0dab77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Supports the ABF-119 inbox's unread-count aggregation (per-conversation
    # SUM over recipient_id + is_read). The ticket names "(recipient_id,
    # read_at)" but the frozen ABF-118 schema has no read_at column — it's
    # `is_read: bool` — so the index is built on that instead.
    op.create_index(
        "ix_direct_messages_recipient_unread",
        "direct_messages",
        ["recipient_id", "is_read"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_direct_messages_recipient_unread", table_name="direct_messages"
    )

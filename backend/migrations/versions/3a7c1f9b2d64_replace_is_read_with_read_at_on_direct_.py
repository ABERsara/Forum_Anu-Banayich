"""replace is_read with read_at on direct_messages

Revision ID: 3a7c1f9b2d64
Revises: aac7e1fb8f49
Create Date: 2026-09-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a7c1f9b2d64"
down_revision: str | Sequence[str] | None = "aac7e1fb8f49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UNREAD_INDEX = "ix_direct_messages_recipient_unread"

# A lightweight table handle for the data steps. Using SQLAlchemy expressions
# rather than a literal SQL string keeps the boolean comparison dialect-correct:
# `is_read IS true` on PostgreSQL and `is_read IS 1` on SQLite are the same
# expression here, and a hand-written `= 1` would have failed on PostgreSQL.
direct_messages = sa.table(
    "direct_messages",
    sa.column("is_read", sa.Boolean),
    sa.column("read_at", sa.DateTime),
    sa.column("created_at", sa.DateTime),
)


def upgrade() -> None:
    """Upgrade schema."""
    # ABF-119 built this index on (recipient_id, is_read); the column it points
    # at is about to disappear, so it is rebuilt on read_at at the end.
    op.drop_index(UNREAD_INDEX, table_name="direct_messages")

    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.add_column(sa.Column("read_at", sa.DateTime(), nullable=True))

    # An already-read message keeps *a* timestamp rather than none: is_read
    # carried no time, and created_at is the only instant the row can prove.
    # It is a lower bound — a message was certainly not read before it was
    # sent — which is what a receipt needs. Stamping "now" instead would
    # claim every historical message was read at deploy time.
    op.execute(
        direct_messages.update()
        .where(direct_messages.c.is_read.is_(True))
        .values(read_at=direct_messages.c.created_at)
    )

    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.drop_column("is_read")

    op.create_index(UNREAD_INDEX, "direct_messages", ["recipient_id", "read_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(UNREAD_INDEX, table_name="direct_messages")

    # server_default="0" only so the NOT NULL column can be added to a table
    # that already has rows; it is dropped again right after the backfill, so
    # the restored schema matches what ABF-118 created exactly.
    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_read",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.execute(
        direct_messages.update()
        .where(direct_messages.c.read_at.isnot(None))
        .values(is_read=True)
    )

    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.alter_column("is_read", server_default=None)
        batch_op.drop_column("read_at")

    op.create_index(UNREAD_INDEX, "direct_messages", ["recipient_id", "is_read"])

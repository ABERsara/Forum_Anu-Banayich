"""add hidden_at to direct_messages and direct_message_report_viewed to auditaction

Revision ID: 2480f359ccd7
Revises: a4d7c81f0e93
Create Date: 2026-09-14 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2480f359ccd7"
down_revision: str | Sequence[str] | None = "a4d7c81f0e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ABF-113: a moderator upholding a report on a private message needs
    # somewhere to record that — see models/forum.py's DirectMessage.hidden_at.
    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.add_column(sa.Column("hidden_at", sa.DateTime(), nullable=True))

    # PostgreSQL only — see b3e9f2a6c1d4 for why: SQLite's Enum(AuditAction)
    # is a plain VARCHAR + CHECK that create_all() rebuilds from the Python
    # enum every time, so only the real Postgres type needs teaching. ADD
    # VALUE cannot run inside the transaction env.py wraps migrations in, so
    # this runs in its own autocommit block. The literal string (not an
    # f-string) is deliberate — test_migration_enum_consistency.py scans for
    # this exact `ALTER TYPE ... ADD VALUE` shape.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS "
                "'DIRECT_MESSAGE_REPORT_VIEWED'"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE — same trade-off already
    # accepted for CLOSED_ACCOUNT_DELETED (b3e9f2a6c1d4): reversing would mean
    # rebuilding the enum type and everything built on it, for a value
    # nothing downstream requires removing.
    with op.batch_alter_table("direct_messages") as batch_op:
        batch_op.drop_column("hidden_at")

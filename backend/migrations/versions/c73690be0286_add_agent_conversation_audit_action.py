"""add AGENT_CONVERSATION to auditaction

Revision ID: c73690be0286
Revises: aac7e1fb8f49
Create Date: 2026-09-03 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c73690be0286"
down_revision: str | Sequence[str] | None = "aac7e1fb8f49"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # PostgreSQL: extend the native `auditaction` enum type. `ALTER TYPE ... ADD
    # VALUE` cannot run inside a transaction block on PostgreSQL < 12, so it goes
    # in an autocommit_block (a no-op wrapper on 12+); IF NOT EXISTS keeps it
    # idempotent. On SQLite the enum column is plain VARCHAR with no CHECK, so
    # there is nothing to alter.
    if op.get_bind().dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'AGENT_CONVERSATION'"
        )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL cannot remove a value from an enum type.
    pass

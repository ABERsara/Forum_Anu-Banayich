"""add AGENT_CONVERSATION to auditaction

Revision ID: c73690be0286
Revises: 3a7c1f9b2d64
Create Date: 2026-09-03 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c73690be0286"
down_revision: str | Sequence[str] | None = "3a7c1f9b2d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # PostgreSQL: extend the native `auditaction` enum type. PostgreSQL 12+
    # allows `ALTER TYPE ... ADD VALUE` inside a transaction as long as the new
    # value is not *used* in the same transaction (it is not here), so this runs
    # in the migration's own transaction and stays atomic with the rest of the
    # `alembic upgrade` run. IF NOT EXISTS keeps it idempotent on re-run. On
    # SQLite the enum column is plain VARCHAR with no CHECK, so nothing to alter.
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'AGENT_CONVERSATION'")


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL cannot remove a value from an enum type.
    pass

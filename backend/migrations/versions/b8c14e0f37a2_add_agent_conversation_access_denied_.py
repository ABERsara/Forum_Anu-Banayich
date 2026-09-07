"""add AGENT_CONVERSATION_ACCESS_DENIED to auditaction

Revision ID: b8c14e0f37a2
Revises: 79daa6708dd8
Create Date: 2026-09-07 00:00:00.000000

ABF-122 owns this value. ABF-148 added AGENT_CONVERSATION (the successful
exchange); the refusal is a separate action written by
agent_service._deny(), and nothing before this ticket emitted it. Shape copied
from c73690be0286 — same enum type, same dialect guard.

Sitting on ABF-120's agent tables (79daa6708dd8) rather than on main's head:
this branch is stacked on feat/ABF-120-agent-data-model-permissions, whose own
migration is the tip after it was re-pointed past the ABF-122 revert. One head
stays one head.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c14e0f37a2"
down_revision: str | Sequence[str] | None = "79daa6708dd8"
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
    op.execute(
        "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS "
        "'AGENT_CONVERSATION_ACCESS_DENIED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL cannot remove a value from an enum type.
    pass

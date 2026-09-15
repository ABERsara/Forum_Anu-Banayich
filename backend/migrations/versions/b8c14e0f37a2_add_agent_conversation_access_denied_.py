"""add AGENT_CONVERSATION_ACCESS_DENIED to auditaction

Revision ID: b8c14e0f37a2
Revises: d4a1c7e93b52
Create Date: 2026-09-15 00:00:00.000000

ABF-122 owns this value. ABF-147 added AGENT_CONVERSATION (the successful
exchange) in c73690be0286; the refusal is a separate action written by
agent_service._deny(), and nothing before this ticket emitted it. Shape copied
from that migration — same enum type, same dialect guard.

Sits on ABF-121's agent_knowledge_chunks migration (d4a1c7e93b52), which is
main's head now that ABF-121 has merged (PR #135). One head stays one head.

A separate migration rather than an edit to 91c4a53eec32_initial.py, per
CONTRIBUTING §2 ("אין לשנות migration קיים"):
test_migration_enum_consistency.py walks every `op.execute(...)` in an
`upgrade()` and folds the values it finds into the expected set, so a
standalone ALTER TYPE satisfies it without anyone touching a shipped file.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c14e0f37a2"
down_revision: str | Sequence[str] | None = "d4a1c7e93b52"
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

"""restore auditaction enum values dropped from the initial migration

Revision ID: 6c92de4f1a37
Revises: d3f0a6b71c58
Create Date: 2026-09-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c92de4f1a37"
down_revision: str | Sequence[str] | None = "d3f0a6b71c58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# These six values were previously added by editing 91c4a53eec32_initial.py
# in place across several tickets (ABF-118 and others). Alembic never re-runs
# a revision that already executed, so any database that ran the initial
# migration before those edits landed — including production — was left with
# an auditaction type missing all six. 91c4a53eec32 has been restored to the
# 14 values it actually created; this migration adds the rest the correct
# way, with IF NOT EXISTS so it is a no-op wherever a value already exists
# (e.g. databases built fresh from the corrected initial migration).
#
# Each statement is written out literally (not built from a loop) because
# test_migration_enum_consistency statically greps this file's source text
# for `ALTER TYPE ... ADD VALUE '...'` — a templated value wouldn't be visible
# to it.


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'MODERATOR_UPDATED'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'MODERATOR_REMOVED'")
    op.execute(
        "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'DIRECT_MESSAGE_ACCESS_DENIED'"
    )
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'DIRECT_MESSAGE_PRUNED'")
    op.execute("ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'AGENT_CONVERSATION'")
    op.execute(
        "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS "
        "'AGENT_CONVERSATION_ACCESS_DENIED'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE — removing an enum value
    # would require rebuilding the type, which is unsafe to do blindly here
    # since existing rows may already reference these values.
    pass

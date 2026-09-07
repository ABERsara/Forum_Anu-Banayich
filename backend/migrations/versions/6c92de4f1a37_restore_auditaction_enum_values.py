"""restore auditaction enum values dropped from the initial migration

Revision ID: 6c92de4f1a37
Revises: 3a7c1f9b2d64
Create Date: 2026-09-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6c92de4f1a37"
down_revision: str | Sequence[str] | None = "3a7c1f9b2d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# These four values were previously added by editing 91c4a53eec32_initial.py
# in place across several tickets (ABF-118 and others). Alembic never re-runs
# a revision that already executed, so any database that ran the initial
# migration before those edits landed — including production — was left with
# an auditaction type missing all four. 91c4a53eec32 has been restored to the
# 14 values it actually created; this migration adds the rest the correct
# way, with IF NOT EXISTS so it is a no-op wherever a value already exists
# (e.g. databases built fresh from the corrected initial migration).
#
# AGENT_CONVERSATION and AGENT_CONVERSATION_ACCESS_DENIED, also missing on
# production, are deliberately not added here — the agent-conversation
# feature that used them (ABF-122) was reverted on main after this branch
# was created, and they are no longer members of AuditAction.
#
# Each statement is written out literally (not built from a loop) because
# test_migration_enum_consistency reads this file via ast.parse() and looks
# for `ALTER TYPE ... ADD VALUE '...'` in the resolved string constant — a
# templated value wouldn't be visible to it.


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


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE — removing an enum value
    # would require rebuilding the type, which is unsafe to do blindly here
    # since existing rows may already reference these values.
    pass

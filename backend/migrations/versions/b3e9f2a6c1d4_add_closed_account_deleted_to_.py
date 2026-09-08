"""add closed_account_deleted to reportdecision

Revision ID: b3e9f2a6c1d4
Revises: 3a7c1f9b2d64
Create Date: 2026-09-07 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3e9f2a6c1d4"
down_revision: str | Sequence[str] | None = "3a7c1f9b2d64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ABF-117: a report on a private message auto-closes with this decision
    # when the reported-on user deletes their account (spec §9.4) — see
    # retention_service.purge_user_direct_messages().
    #
    # PostgreSQL only: `Enum(ReportDecision)` on SQLite (dev/tests) is a plain
    # VARCHAR + CHECK constraint that SQLAlchemy rebuilds from the Python enum
    # on every `create_all()`, so there is nothing to migrate there — only the
    # real `reportdecision` type on PostgreSQL needs a new value taught to it.
    #
    # ADD VALUE cannot run inside the transaction env.py wraps every migration
    # in (PostgreSQL forbids using a new enum value in the same transaction
    # that added it, and disallows the statement in one at all before PG 12),
    # so this step runs in its own autocommit block instead.
    #
    # A shipped migration is never edited in place — not even 91c4a53eec32,
    # not even to add this value to its own sa.Enum(...) list — so this new
    # migration is the only place this value is ever added, for every
    # database, deployed or not. The literal string (not an f-string built
    # from a shared constant) is deliberate: test_migration_enum_consistency.py
    # finds it by scanning for this exact `ALTER TYPE ... ADD VALUE` shape.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE reportdecision ADD VALUE IF NOT EXISTS 'CLOSED_ACCOUNT_DELETED'"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE. Reversing this would mean
    # recreating the enum type and every column/index built on it, which is
    # more risk than a value nothing downstream requires removing is worth —
    # same trade-off already accepted for every other enum in this project.
    pass

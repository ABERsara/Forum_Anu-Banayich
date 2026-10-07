"""add meeting_updated and meeting_cancelled to auditaction

Revision ID: cf7edfee3fd8
Revises: e8d502aea547
Create Date: 2026-10-07 00:10:00.000000

ABF-163 owns these two values: a professional editing a meeting she
created, and calling it off — see meeting_service.update_meeting() and
meeting_service.cancel_meeting().

A separate migration rather than an edit to 91c4a53eec32_initial.py, per
CONTRIBUTING §2 ("אין לשנות migration קיים"):
test_migration_enum_consistency.py folds every `ALTER TYPE ... ADD VALUE` it
finds in an `upgrade()` into the expected set. Shape copied from 5d2e8b7f1c60
(PROFILE_UPDATED) and 8a1d6c4b2f93 (MEETING_CREATED).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cf7edfee3fd8"
down_revision: str | Sequence[str] | None = "e8d502aea547"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # PostgreSQL only: on SQLite (dev/tests) an enum column is a VARCHAR that
    # SQLAlchemy rebuilds from the Python enum, so there is nothing to migrate.
    #
    # ADD VALUE runs in an autocommit block, as in 8a1d6c4b2f93, so it never
    # shares a transaction with a statement that uses the new value.
    #
    # The literal strings rather than f-strings off the constants are
    # deliberate: test_migration_enum_consistency.py finds the values by
    # scanning for this exact `ALTER TYPE ... ADD VALUE` shape.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'MEETING_UPDATED'"
            )
            op.execute(
                "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'MEETING_CANCELLED'"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE, and recreating the type
    # would mean rebuilding every column built on it — the same trade-off
    # already accepted for every other enum value in this project
    # (see b3e9f2a6c1d4).
    pass

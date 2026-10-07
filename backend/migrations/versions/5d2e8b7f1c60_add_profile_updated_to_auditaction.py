"""add profile_updated to auditaction

Revision ID: 5d2e8b7f1c60
Revises: e7b3f19c4a06
Create Date: 2026-10-05 00:00:00.000000

ABF-165 owns this value: a user editing their own profile through
PUT /users/me — see user_service.update_own_profile().

Sits on main's head (e7b3f19c4a06, the ABF-156/ABF-154 merge), so one head
stays one head.

A separate migration rather than an edit to 91c4a53eec32_initial.py, per
CONTRIBUTING §2 ("אין לשנות migration קיים"):
test_migration_enum_consistency.py folds every `ALTER TYPE ... ADD VALUE` it
finds in an `upgrade()` into the expected set. Shape copied from 8a1d6c4b2f93
(MEETING_CREATED).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5d2e8b7f1c60"
down_revision: str | Sequence[str] | None = "e7b3f19c4a06"
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
    # The literal string rather than an f-string off the constant is
    # deliberate: test_migration_enum_consistency.py finds the value by
    # scanning for this exact `ALTER TYPE ... ADD VALUE` shape.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'PROFILE_UPDATED'"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE, and recreating the type
    # would mean rebuilding every column built on it — the same trade-off
    # already accepted for every other enum value in this project
    # (see b3e9f2a6c1d4).
    pass

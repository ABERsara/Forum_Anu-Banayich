"""add meeting_created to auditaction

Revision ID: 8a1d6c4b2f93
Revises: 7f3c2b8d1e40
Create Date: 2026-09-15 10:05:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a1d6c4b2f93"
down_revision: str | Sequence[str] | None = "7f3c2b8d1e40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # ABF-156: a professional scheduling a Google Meet is an audited action —
    # see meeting_service.create_meeting().
    #
    # Its own migration, separate from 7f3c2b8d1e40 which creates the tables:
    # ADD VALUE cannot run inside the transaction env.py wraps a migration in,
    # so it needs an autocommit block, and keeping the schema changes in a
    # migration that is wholly transactional means a failure there rolls back
    # cleanly.
    #
    # PostgreSQL only: on SQLite (dev/tests) an enum column is a VARCHAR that
    # SQLAlchemy rebuilds from the Python enum, so there is nothing to migrate.
    #
    # The literal string rather than an f-string off the constant is
    # deliberate: test_migration_enum_consistency.py finds the value by
    # scanning for this exact `ALTER TYPE ... ADD VALUE` shape.
    if op.get_bind().dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE auditaction ADD VALUE IF NOT EXISTS 'MEETING_CREATED'"
            )


def downgrade() -> None:
    """Downgrade schema."""
    # PostgreSQL has no ALTER TYPE ... DROP VALUE, and recreating the type
    # would mean rebuilding every column built on it — the same trade-off
    # already accepted for every other enum value in this project
    # (see b3e9f2a6c1d4).
    pass

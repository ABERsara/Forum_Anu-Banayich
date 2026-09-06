"""add asker_user_type/asker_sector to professional_queries

Revision ID: e65bae5f13ea
Revises: cd7c2f0dab77
Create Date: 2026-08-31 13:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e65bae5f13ea"
down_revision: str | Sequence[str] | None = "cd7c2f0dab77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # create_type=False: "usertype"/"sector" already exist in Postgres (created
    # by the initial migration for users.user_type/users.sector) — these
    # columns reuse the same enum types, they don't define new ones.
    op.add_column(
        "professional_queries",
        sa.Column(
            "asker_user_type",
            sa.Enum(
                "WIDOWER",
                "WIDOW",
                "ORPHAN_MALE",
                "ORPHAN_FEMALE",
                name="usertype",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "professional_queries",
        sa.Column(
            "asker_sector",
            sa.Enum(
                "HASIDIC",
                "LITVISH",
                "SEPHARDIC",
                "GENERAL",
                name="sector",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # Backfill from each asker's current profile — the only historical
    # approximation available, since the cell wasn't captured before this
    # migration. A correlated subquery per column, portable across SQLite
    # (tests) and PostgreSQL (prod): where the asker's user_type/sector is
    # itself NULL, the subquery yields NULL and the column is simply left
    # NULL — not an error, that question just never appears in the public
    # feed. Future rows always have both fields set directly by
    # create_query(), so this backfill never runs again after this release.
    op.execute(
        """
        UPDATE professional_queries
        SET asker_user_type = (
            SELECT users.user_type FROM users WHERE users.id = professional_queries.asker_id
        ),
        asker_sector = (
            SELECT users.sector FROM users WHERE users.id = professional_queries.asker_id
        )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("professional_queries", "asker_sector")
    op.drop_column("professional_queries", "asker_user_type")

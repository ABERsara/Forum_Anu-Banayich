"""add cancelled_at to forum_posts

Revision ID: e8d502aea547
Revises: 2d0766bdb16c
Create Date: 2026-10-07 00:05:00.000000

ABF-163: DELETE /meetings/{id} marks the meeting's announcement as
cancelled. The marker is a column of its own rather than a PostStatus value,
because moderation writes `status` back (see the model's comment on
ForumPost.cancelled_at).

Nullable with no default: every post that already exists is a post whose
meeting, if it has one, was never cancelled — NULL is the correct value for
all of them, so there is nothing to backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8d502aea547"
down_revision: str | Sequence[str] | None = "2d0766bdb16c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "forum_posts", sa.Column("cancelled_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("forum_posts", "cancelled_at")

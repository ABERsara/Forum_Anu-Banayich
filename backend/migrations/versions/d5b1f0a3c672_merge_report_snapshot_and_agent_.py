"""merge the report-snapshot and agent-conversation heads

Revision ID: d5b1f0a3c672
Revises: b8e41c9d7a35, c73690be0286
Create Date: 2026-09-09 00:00:00.000000

Both parents hang off 6c92de4f1a37, so merging main into this branch left the
graph with two heads and no file for git to report a conflict in:

  * b8e41c9d7a35 — ABF-112's report snapshot, written here.
  * c73690be0286 — main's AGENT_CONVERSATION, reached through 037332dbf22d,
    the merge revision ABF-117 needed for the same reason.

`alembic upgrade head` refuses to run against two of them ("Multiple head
revisions are present"), which is what test_migration.py's `upgrade(cfg,
"head")` would have hit. Nothing to do on either side of the join: both
parents have already made their changes, and this only says they are one
history again.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d5b1f0a3c672"
down_revision: str | Sequence[str] | None = ("b8e41c9d7a35", "c73690be0286")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

"""merge the ABF-112 snapshot and agent-tables heads

Revision ID: 45019c151eb8
Revises: d5b1f0a3c672, 79daa6708dd8
Create Date: 2026-09-10 00:00:00.000000

The second time this branch has had to close a split, and for the same reason
as d5b1f0a3c672: both parents hang off c73690be0286, so merging main left two
heads and nothing for git to report a conflict in.

  * d5b1f0a3c672 — this branch's own merge revision, which already joined
    ABF-112's report snapshot (b8e41c9d7a35) to main's AGENT_CONVERSATION.
  * 79daa6708dd8 — main's agent tables, which landed with PR #113 (ABF-120)
    after that join was written.

`alembic upgrade head` refuses to run against two of them ("Multiple head
revisions are present"), which is what test_migration.py's `upgrade(cfg,
"head")` would have hit. Nothing to do on either side of the join: both
parents have already made their changes, and this only says they are one
history again.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "45019c151eb8"
down_revision: str | Sequence[str] | None = ("d5b1f0a3c672", "79daa6708dd8")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

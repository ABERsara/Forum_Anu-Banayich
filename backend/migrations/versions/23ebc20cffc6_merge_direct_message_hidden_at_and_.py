"""merge the direct-message hidden_at and agent-knowledge-chunks heads

Revision ID: 23ebc20cffc6
Revises: 2480f359ccd7, d4a1c7e93b52
Create Date: 2026-09-15 00:00:00.000000

Both parents hang off a4d7c81f0e93 (the user_restrictions migration), so
merging main into this branch left the graph with two heads and no file for
git to report a conflict in:

  * 2480f359ccd7 — ABF-113's DirectMessage.hidden_at and
    DIRECT_MESSAGE_REPORT_VIEWED, written here.
  * d4a1c7e93b52 — main's agent knowledge chunks, from ABF-121.

`alembic upgrade head` refuses to run against two of them ("Multiple head
revisions are present"), which is what test_migration.py's `upgrade(cfg,
"head")` hits. Nothing to do on either side of the join: both parents have
already made their changes, and this only says they are one history again.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "23ebc20cffc6"
down_revision: str | Sequence[str] | None = ("2480f359ccd7", "d4a1c7e93b52")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

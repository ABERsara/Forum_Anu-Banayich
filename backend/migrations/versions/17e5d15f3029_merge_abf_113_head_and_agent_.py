"""merge the ABF-113 head and the agent-conversation-access-denied head

Revision ID: 17e5d15f3029
Revises: 23ebc20cffc6, b8c14e0f37a2
Create Date: 2026-09-16 00:00:00.000000

Both parents hang off d4a1c7e93b52 (ABF-121's agent knowledge chunks), so
merging main into this branch a second time left the graph with two heads
again:

  * 23ebc20cffc6 — this branch's own earlier merge of ABF-113's hidden_at
    migration with d4a1c7e93b52, written here.
  * b8c14e0f37a2 — main's agent conversation access-denied auditing, from
    ABF-122, which branched off d4a1c7e93b52 independently and landed on
    main after 23ebc20cffc6 already had.

`alembic upgrade head` refuses to run against two of them ("Multiple head
revisions are present"), which is what test_migration.py's `upgrade(cfg,
"head")` hits. Nothing to do on either side of the join: both parents have
already made their changes, and this only says they are one history again.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "17e5d15f3029"
down_revision: str | Sequence[str] | None = ("23ebc20cffc6", "b8c14e0f37a2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

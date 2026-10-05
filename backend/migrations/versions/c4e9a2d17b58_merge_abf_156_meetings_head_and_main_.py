"""merge the ABF-156 meetings head and main's ABF-113/ABF-122 head

Revision ID: c4e9a2d17b58
Revises: 17e5d15f3029, 8a1d6c4b2f93
Create Date: 2026-09-16 00:00:00.000000

ABF-156's migrations branched off d4a1c7e93b52 (ABF-121's agent knowledge
chunks) before main moved on, so merging main into
feat/ABF-156-google-meet-integration left the graph with two heads:

  * 17e5d15f3029 — main's merge of ABF-113 (direct_messages.hidden_at) and
    ABF-122 (agent conversation access-denied auditing).
  * 8a1d6c4b2f93 — ABF-156's meetings, Google Calendar credentials and
    forum post type (7f3c2b8d1e40), then MEETING_CREATED on auditaction.

`alembic upgrade head` refuses to run against two of them ("Multiple head
revisions are present"). Joined here rather than by re-pointing
7f3c2b8d1e40 at main's head: that revision has already been applied to local
databases, and moving its parent would make Alembic treat main's migrations as
applied there too — skipping them without an error. Nothing to do on either
side of the join: both parents have already made their changes.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c4e9a2d17b58"
down_revision: str | Sequence[str] | None = ("17e5d15f3029", "8a1d6c4b2f93")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

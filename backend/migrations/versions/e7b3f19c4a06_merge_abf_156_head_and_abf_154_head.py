"""merge the ABF-156 head and main's ABF-154 head

Revision ID: e7b3f19c4a06
Revises: c4e9a2d17b58, c5a90f47e2d1
Create Date: 2026-09-17 00:00:00.000000

A second merge of main into feat/ABF-156-google-meet-integration, for the same
reason as c4e9a2d17b58: both sides moved on from 17e5d15f3029 independently,
leaving the graph with two heads:

  * c4e9a2d17b58 — ABF-156's earlier merge of its meetings head with main.
  * c5a90f47e2d1 — ABF-154's users.is_report_restricted.

Joined here rather than by re-pointing either revision, for the reason
c4e9a2d17b58 gives. Nothing to do on either side of the join: both parents
have already made their changes.

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e7b3f19c4a06"
down_revision: str | Sequence[str] | None = ("c4e9a2d17b58", "c5a90f47e2d1")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

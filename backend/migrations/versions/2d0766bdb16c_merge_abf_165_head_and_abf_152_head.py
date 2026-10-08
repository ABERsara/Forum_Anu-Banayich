"""merge the ABF-165 head and the ABF-152 head

Revision ID: 2d0766bdb16c
Revises: 5d2e8b7f1c60, a80e87afe0fa
Create Date: 2026-10-07 00:00:00.000000

main has had two heads since PR #146 merged after PR #150. Both migrations
were written on top of e7b3f19c4a06, and neither PR conflicted with the other
because they touch different files:

  * 5d2e8b7f1c60 — ABF-165's PROFILE_UPDATED on auditaction.
  * a80e87afe0fa — ABF-152's audit_logs filter/sort indexes.

With two heads every `alembic upgrade head` fails with "Multiple head
revisions are present", including test_migration.py on main. ABF-163 needs
a single head to add its own migrations on, so it joins the two here, the
same way e7b3f19c4a06 and c4e9a2d17b58 did. Neither parent is re-pointed:
both are already on main and may already have been applied somewhere.

Neither side has anything left to do: each parent has already made its
change.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "2d0766bdb16c"
down_revision: str | Sequence[str] | None = ("5d2e8b7f1c60", "a80e87afe0fa")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

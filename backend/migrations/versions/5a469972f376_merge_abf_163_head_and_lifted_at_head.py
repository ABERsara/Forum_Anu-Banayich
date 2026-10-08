"""merge the ABF-163 head and the report_restriction_lifted_at head

Revision ID: 5a469972f376
Revises: cf7edfee3fd8, 953f562dc226
Create Date: 2026-10-08 00:00:00.000000

ABF-163 and PR #156 (the lift clean-slate window) both built on
2d0766bdb16c, and neither touches the other's migration files, so merging
main into ABF-163 leaves two heads:

  * cf7edfee3fd8 — ABF-163's MEETING_UPDATED/MEETING_CANCELLED on auditaction
    (on top of e8d502aea547, forum_posts.cancelled_at).
  * 953f562dc226 — users.report_restriction_lifted_at, already on main.

With two heads every `alembic upgrade head` fails with "Multiple head
revisions are present". They are joined here the same way 2d0766bdb16c joined
the previous pair. Neither parent is re-pointed: 953f562dc226 is already on
main and may already have been applied somewhere.

Neither side has anything left to do: each parent has already made its
change.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "5a469972f376"
down_revision: str | Sequence[str] | None = ("cf7edfee3fd8", "953f562dc226")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

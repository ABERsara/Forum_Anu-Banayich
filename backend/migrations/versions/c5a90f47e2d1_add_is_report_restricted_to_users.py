"""add is_report_restricted to users

Revision ID: c5a90f47e2d1
Revises: 17e5d15f3029
Create Date: 2026-09-16 09:00:00.000000

ABF-154, §7.2's second row. The flag a member carries once her reports have
been dismissed FALSE_REPORT_LIMIT times inside FALSE_REPORT_DAYS_WINDOW —
report_service._check_frequent_false_reporter() sets it, file_report() refuses
on it.

A column on `users` rather than another `user_restrictions` row, and the model
docstring gives the reason: every row in that table is bounded by `expires_at`,
and this measure has no end date. Nothing here keeps a *count* — the counts are
still read from `reports` on every evaluation (restriction_service's own note on
why), so there is no second copy of the truth for this column to drift from.

`server_default` stays on the column rather than being set for the backfill and
dropped again. It is what lets a NOT NULL column be added to a table that
already has rows, and `models/user.py` declares the same default — so keeping
it is what stops the next `alembic revision --autogenerate` from emitting a
drift it would have to be told to ignore. Same shape as agent_knowledge_domains
.is_active (79daa6708dd8).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c5a90f47e2d1"
down_revision: str | Sequence[str] | None = "17e5d15f3029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column(
            "is_report_restricted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "is_report_restricted")

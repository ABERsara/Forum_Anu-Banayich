"""merge report-decision and auditaction-restore heads

Revision ID: 037332dbf22d
Revises: b3e9f2a6c1d4, 6c92de4f1a37
Create Date: 2026-09-08 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "037332dbf22d"
down_revision: str | Sequence[str] | None = ("b3e9f2a6c1d4", "6c92de4f1a37")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

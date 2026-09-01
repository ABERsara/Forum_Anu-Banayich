"""merge inbox-index and asker-cell heads

Revision ID: aac7e1fb8f49
Revises: 71468d6695fb, e65bae5f13ea
Create Date: 2026-09-01 00:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "aac7e1fb8f49"
down_revision: str | Sequence[str] | None = ("71468d6695fb", "e65bae5f13ea")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

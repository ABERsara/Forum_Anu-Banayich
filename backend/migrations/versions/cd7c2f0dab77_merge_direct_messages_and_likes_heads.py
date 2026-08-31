"""merge direct-messages and likes heads

Revision ID: cd7c2f0dab77
Revises: 5677b8e5c583, f966336a5fa6
Create Date: 2026-08-31 10:49:44.898680

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "cd7c2f0dab77"
down_revision: str | Sequence[str] | None = ("5677b8e5c583", "f966336a5fa6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass

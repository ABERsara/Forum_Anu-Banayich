"""
Like model.

Any user who can view a piece of content can like it — a general,
polymorphic model (like Report, see report.py) so it can serve likes on
ProfessionalQuery today and ForumPost later, without another migration.

Composite primary key (user_id, target_type, target_id) instead of a
surrogate id + UniqueConstraint: a row's identity already is "this user
liked this target once", so the constraint that enforces that is the key.
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import LikeTargetType
from app.db.base import Base


class Like(Base):
    __tablename__ = "likes"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), primary_key=True
    )
    target_type: Mapped[LikeTargetType] = mapped_column(
        Enum(LikeTargetType), primary_key=True
    )
    # ID of the ProfessionalQuery / ForumPost
    target_id: Mapped[str] = mapped_column(String(36), primary_key=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Like user={self.user_id} target={self.target_type}:{self.target_id}>"

"""
Forum post and direct message models.

ForumPost – publicly visible within the visibility scope.
DirectMessage – private 1:1 message between two users.

Key rule (enforced in forum_service.py):
    A user can ONLY read posts where:
        group_visibility == user.user_type  OR  group_visibility == "all"
        AND
        sector_visibility == user.sector    OR  sector_visibility == "all"
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import GroupVisibility, PostStatus, SectorVisibility
from app.db.base import Base


class ForumPost(Base):
    __tablename__ = "forum_posts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    author_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # ------------------------------------------------------------------
    # Visibility (content filter matrix)
    # ------------------------------------------------------------------
    group_visibility: Mapped[GroupVisibility] = mapped_column(
        Enum(GroupVisibility), nullable=False
    )
    sector_visibility: Mapped[SectorVisibility] = mapped_column(
        Enum(SectorVisibility), nullable=False
    )

    # ------------------------------------------------------------------
    # Content (stored encrypted)
    # ------------------------------------------------------------------
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted
    attachment_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------
    status: Mapped[PostStatus] = mapped_column(
        Enum(PostStatus), nullable=False, default=PostStatus.VISIBLE
    )
    report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    author: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="forum_posts", foreign_keys=[author_id]
    )
    reports: Mapped[list["Report"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Report",
        primaryjoin="and_(Report.target_id == ForumPost.id, Report.target_type == 'forum_post')",
        foreign_keys="Report.target_id",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<ForumPost id={self.id} status={self.status}>"


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Stored encrypted (server-side encryption)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    is_read: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    sender: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="sent_messages", foreign_keys=[sender_id]
    )
    recipient: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="received_messages", foreign_keys=[recipient_id]
    )

    def __repr__(self) -> str:
        return f"<DirectMessage id={self.id} from={self.sender_id}>"

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
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text, func
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
    __table_args__ = (
        Index(
            "ix_direct_messages_conversation_created",
            "conversation_key",
            "created_at",
        ),
        # The inbox's per-conversation unread aggregation (ABF-119) filters on
        # recipient_id + "not read yet". Declared here as well as in the
        # migration that first created it: the model is what
        # Base.metadata.create_all() builds, so an index that lives only in a
        # migration silently does not exist for anything created that way.
        Index(
            "ix_direct_messages_recipient_unread",
            "recipient_id",
            "read_at",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    sender_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    recipient_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Deterministic key derived from the two participant ids (sorted, joined) –
    # see forum_service.build_conversation_key(). No separate "conversation"
    # entity exists (spec has none); this is what §5.3's "1,000 messages per
    # conversation" groups by.
    conversation_key: Mapped[str] = mapped_column(String(80), nullable=False)

    # Which MESSAGE_ENCRYPTION_KEY epoch encrypted `content` – see
    # app/core/encryption.py. Only version 1 exists today; key rotation is
    # out of scope for ABF-118.
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Stored encrypted (server-side encryption, AES-256-GCM – see
    # app/core/encryption.py)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # When the RECIPIENT opened the conversation — NULL until then, and the
    # single source of truth for "read" (there is no is_read boolean beside
    # it to drift from). A timestamp rather than a flag because the receipt
    # the sender sees is "read", and a flag cannot answer "when".
    #
    # Only ever written for the viewer's own received messages, never for the
    # ones they sent — see mark_conversation_read().
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Python-side default *as well as* the server one, unlike the rest of the
    # models here. SQLite's CURRENT_TIMESTAMP resolves to whole seconds, so
    # every message sent inside the same second shared a created_at — and the
    # history cursor (ABF-120) orders by exactly this column. A shared sort
    # key is what makes a paged list repeat or skip a row at the page seam.
    # datetime.now(UTC) is microsecond-precise on both databases; naive-UTC to
    # match what func.now() already writes and what user_service.py compares
    # created_at against.
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        server_default=func.now(),
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

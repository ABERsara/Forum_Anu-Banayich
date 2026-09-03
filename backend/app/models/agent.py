"""
AI agent conversation models (ABF-120).

AgentConversation – one thread between a user and one agent domain.
AgentMessage      – a single turn inside that thread, user or agent.

Key rules (enforced in agent_service.py):
    A conversation belongs to exactly one user and one AgentDomain; the
    agent never reads across domains, because each domain has its own
    knowledge base (SPEC §12).

    Only the owner (or an ADMIN) may read a conversation. There is no
    group/sector visibility axis here – unlike ForumPost, a conversation is
    never shown to anyone but the person who had it.

Message content is stored in the clear, the same as ForumPost.content and
unlike DirectMessage.content: these are questions put to a machine, not a
private exchange between two people, and ABF-123 has to render them back.
What never gets a second copy is the audit trail – the AuditLog row
agent_service.chat() writes records that a conversation happened and how well
grounded the answer was, never a word of what was said (SPEC §9.3).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import AgentDomain, AgentMessageRole
from app.db.base import Base


def _utc_now() -> datetime:
    """Naive-UTC wall clock, the convention every datetime column here uses.

    These two tables are the one place in the schema that writes timestamps
    from Python rather than with ``server_default=func.now()``, and both
    reasons are specific to a chat:

    1. **Ordering.** One POST /chat writes the user turn and the agent turn
       inside the same request. SQLite's CURRENT_TIMESTAMP has one-second
       granularity, so both rows would carry the *same* value and the
       ``order_by(created_at)`` that rebuilds the thread would be free to put
       the answer before the question. ``datetime.now()`` is microsecond
       resolution, so the two turns always sort the way they were said.

    2. **Comparability.** rate_limit_chat() counts messages newer than
       ``datetime.now(UTC).replace(tzinfo=None) - 24h`` — the same threshold
       shape as user_service.escalate_pending_registrations(). Writing the
       column from the same clock that builds the threshold keeps the window
       exact instead of relying on the DB server's timezone matching UTC.
    """
    return datetime.now(UTC).replace(tzinfo=None)


class AgentConversation(Base):
    __tablename__ = "agent_conversations"
    __table_args__ = (
        # rate_limit_chat() counts a user's messages across every agent in the
        # last 24h, and get_conversation() loads one user's thread. Both start
        # from user_id.
        Index("ix_agent_conversations_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Which agent this thread is with. Fixed at creation – a follow-up question
    # cannot move a conversation to another knowledge base.
    domain: Mapped[AgentDomain] = mapped_column(Enum(AgentDomain), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utc_now, onupdate=_utc_now
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", foreign_keys=[user_id]
    )
    messages: Mapped[list["AgentMessage"]] = relationship(
        "AgentMessage",
        back_populates="conversation",
        order_by="AgentMessage.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AgentConversation id={self.id} domain={self.domain}>"


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        # The two reads this table has: the last AGENT_HISTORY_TURNS turns of
        # one conversation, and the 24h rate-limit count. Both filter on
        # conversation_id and order/filter by created_at.
        Index(
            "ix_agent_messages_conversation_created", "conversation_id", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_conversations.id"), nullable=False
    )

    role: Mapped[AgentMessageRole] = mapped_column(
        Enum(AgentMessageRole), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=_utc_now
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    conversation: Mapped["AgentConversation"] = relationship(
        "AgentConversation", back_populates="messages"
    )

    def __repr__(self) -> str:
        return f"<AgentMessage id={self.id} role={self.role}>"

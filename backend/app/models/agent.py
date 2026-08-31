"""
AI agent data model.

AgentDomain          – a subject area an agent serves, gated by group/sector
                       visibility exactly like ForumPost.
AgentKnowledgeEntry  – one content item in a domain's knowledge base.
AgentConversation    – one user↔agent conversation within a domain.
AgentMessage         – one message in a conversation (from the user or the agent).

No AI capability lives here yet – this is the schema the RAG/LLM/chat
tickets (ABF-121/122) build on.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import (
    AgentMessageRole,
    GroupVisibility,
    ProfessionalDomain,
    SectorVisibility,
)
from app.db.base import Base


class AgentDomain(Base):
    __tablename__ = "agent_domains"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Visibility – same single-enum matrix as ForumPost (not JSON arrays).
    group_visibility: Mapped[GroupVisibility] = mapped_column(
        Enum(GroupVisibility), nullable=False
    )
    sector_visibility: Mapped[SectorVisibility] = mapped_column(
        Enum(SectorVisibility), nullable=False
    )

    # Which professional discipline may edit this domain's knowledge base
    # (same enum as User.professional_domain).
    professional_domain: Mapped[ProfessionalDomain] = mapped_column(
        Enum(ProfessionalDomain), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AgentDomain id={self.id} name={self.name}>"


class AgentKnowledgeEntry(Base):
    __tablename__ = "agent_knowledge_entries"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    domain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_domains.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Provenance, shown for transparency only – never fetched live.
    source_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AgentKnowledgeEntry id={self.id} domain={self.domain_id}>"


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    domain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_domains.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AgentConversation id={self.id} user={self.user_id} "
            f"domain={self.domain_id}>"
        )


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_conversations.id"), nullable=False
    )
    role: Mapped[AgentMessageRole] = mapped_column(
        Enum(AgentMessageRole), nullable=False
    )

    # Server-side encrypted (AES-256-GCM), same mechanism as
    # DirectMessage.content. Until ABF-118 merges and ABF-121 wires
    # encrypt_message(), this holds plain text; key_version is the
    # MESSAGE_ENCRYPTION_KEY epoch, only version 1 exists.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AgentMessage id={self.id} conversation={self.conversation_id} "
            f"role={self.role}>"
        )

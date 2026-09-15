"""
AI agent data model.

AgentDomain          – a subject area an agent serves, gated by group/sector
                       visibility exactly like ForumPost.
AgentKnowledgeEntry  – one content item in a domain's knowledge base.
AgentKnowledgeChunk  – one embedded slice of an entry, the unit RAG retrieves.
AgentConversation    – one user↔agent conversation within a domain.
AgentMessage         – one message in a conversation (from the user or the agent).

The chunk table carries the retrieval index; the conversation tables hold the
chat history that is built on top of it.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import (
    AgentMessageRole,
    GroupVisibility,
    ProfessionalDomain,
    SectorVisibility,
)
from app.db.base import Base

# Gemini's text-embedding-004 returns 768 numbers. The migration hard-codes the
# same width, so pointing GEMINI_EMBED_MODEL at a model of another dimension
# needs a migration and a full re-index, not just a config edit.
EMBEDDING_DIMENSIONS = 768

# pgvector's VECTOR type exists on PostgreSQL only. SQLite (tests, local dev)
# accepts the column and stores values as text, but reflects the type back as
# NUMERIC(768) — which test_no_agent_model_migration_drift reads as
# model/migration drift. Naming the SQLite side explicitly keeps the two
# dialects in step. Nothing writes an embedding on SQLite: the tests that
# exercise indexing and retrieval need a real vector type and are Postgres-only.
EmbeddingVector = Vector(EMBEDDING_DIMENSIONS).with_variant(Text(), "sqlite")


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

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
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
        String(36),
        ForeignKey("agent_domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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

    # delete-orphan so an entry deleted through the ORM takes its chunks with
    # it in the same flush; the FK's ON DELETE CASCADE covers the same thing
    # DB-side, for a row deleted by SQL that never passes through a session.
    #
    # Not passive_deletes: SQLite enforces ON DELETE only with
    # `PRAGMA foreign_keys=ON`, which this project does not set, so leaving the
    # cascade to the database would orphan every chunk in development and in
    # the test suite while looking correct in production.
    chunks: Mapped[list["AgentKnowledgeChunk"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<AgentKnowledgeEntry id={self.id} domain={self.domain_id}>"


class AgentKnowledgeChunk(Base):
    """One slice of an entry's content, with its embedding.

    Retrieval works on chunks rather than whole entries so an answer is built
    from the few paragraphs that bear on the question instead of every word the
    professional ever wrote about the subject.

    Chunks are derived data, never authored: rag_service.index_entry() rebuilds
    the whole set for an entry from scratch on every run (delete-then-insert),
    which is what keeps UNIQUE(entry_id, chunk_index) from ever blocking a
    re-index after a failed one.
    """

    __tablename__ = "agent_knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "entry_id", "chunk_index", name="uq_agent_knowledge_chunks_entry_index"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    entry_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_knowledge_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Position of this chunk inside its entry, 0-based, in reading order.
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(EmbeddingVector, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    entry: Mapped["AgentKnowledgeEntry"] = relationship(back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<AgentKnowledgeChunk id={self.id} entry={self.entry_id} "
            f"index={self.chunk_index}>"
        )


class AgentConversation(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    domain_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_domains.id"), nullable=False, index=True
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
    # Composite, like DirectMessage: messages are always read time-ordered
    # within a conversation (WHERE conversation_id = ? ORDER BY created_at).
    # This also serves plain conversation_id lookups, so no separate
    # single-column index is needed.
    __table_args__ = (
        Index(
            "ix_agent_messages_conversation_created",
            "conversation_id",
            "created_at",
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

    # Server-side encrypted (AES-256-GCM), same mechanism as
    # DirectMessage.content (app/core/encryption.py). Until ABF-122 wires
    # encrypt_message() this holds plain text; key_version is the
    # MESSAGE_ENCRYPTION_KEY epoch, only version 1 exists.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<AgentMessage id={self.id} conversation={self.conversation_id} "
            f"role={self.role}>"
        )

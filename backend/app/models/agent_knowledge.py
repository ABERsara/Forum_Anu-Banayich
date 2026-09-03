"""
Agent knowledge base model (ABF-121).

AgentKnowledgeChunk – one retrievable passage of curated source material,
scoped to a single AgentDomain.

The agent is allowed to say only what these rows say (SPEC §12: "בסיס ידע
ייעודי לכל סוכן — מוגבל לתחומו בלבד"). rag_service.retrieve() is the only
reader; nothing else in the codebase queries this table.

Rows are curated content, not user input: they are loaded by the association's
staff, so there is no endpoint that writes here and no visibility axis on them
beyond `domain`.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.constants import AgentDomain
from app.db.base import Base


class AgentKnowledgeChunk(Base):
    __tablename__ = "agent_knowledge_chunks"
    __table_args__ = (
        # Every retrieval is "all chunks of one domain" — the agent never
        # reads across domains.
        Index("ix_agent_knowledge_chunks_domain", "domain"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    domain: Mapped[AgentDomain] = mapped_column(Enum(AgentDomain), nullable=False)

    # Shown to the user as the citation under the answer, so it has to read
    # as a heading and not as an internal id.
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Where the passage came from — a law, a regulation, a National Insurance
    # page. Optional: some material is written in-house by the association.
    source: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<AgentKnowledgeChunk id={self.id} domain={self.domain}>"

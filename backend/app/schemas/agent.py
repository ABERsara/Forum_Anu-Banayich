"""
Pydantic schemas for the AI agent chat.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.constants import AgentDomain, AgentMessageRole


class AgentChatRequest(BaseModel):
    """POST /agents/{domain_id}/chat – ask the agent a question."""

    # The ceiling is settings.AGENT_MAX_MESSAGE_LENGTH so it can be tuned per
    # deployment, and it is enforced here rather than in the service so that
    # an over-long question is a 422 on the field that caused it — the same
    # contract every other write endpoint has.
    message: str = Field(
        ..., min_length=1, max_length=settings.AGENT_MAX_MESSAGE_LENGTH
    )

    # Omitted on the first question of a thread; supplied on every follow-up,
    # which is what lets the agent see what was already asked.
    conversation_id: str | None = None

    @field_validator("message", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        """Trim before the length checks, so trailing whitespace neither
        passes an empty message nor fails a message that is exactly at the
        limit."""
        return value.strip() if isinstance(value, str) else value


class AgentSourceOut(BaseModel):
    """A knowledge-base passage the answer was drawn from.

    Returned so the reader can see the answer is grounded, and so that a
    question the agent could not settle can be taken to a professional with
    the document name in hand.
    """

    title: str
    source: str | None = None

    model_config = {"from_attributes": True}


class AgentMessageOut(BaseModel):
    """One turn of a conversation, user or agent."""

    id: str
    role: AgentMessageRole
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AgentChatResponse(BaseModel):
    """The result of one exchange: both rows that were written, plus sources.

    The question is echoed back rather than left to the client to remember,
    because its `id` and `created_at` are the server's, and ABF-123 renders
    the thread from them.
    """

    conversation_id: str
    question: AgentMessageOut
    answer: AgentMessageOut
    sources: list[AgentSourceOut]


class AgentConversationOut(BaseModel):
    """GET /agents/{domain_id}/conversations/{id} – a whole thread."""

    id: str
    domain: AgentDomain
    created_at: datetime
    updated_at: datetime
    messages: list[AgentMessageOut]

    model_config = {"from_attributes": True}

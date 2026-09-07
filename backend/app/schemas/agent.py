"""
Pydantic schemas for the AI agents — the domain catalog (ABF-120) and the
chat flow (ABF-122).

Naming follows the rest of `app/schemas` and ABF-120's own
``AgentDomainResponse``: ``...Response`` for what goes out, ``...Request`` for
what comes in. (The reverted first attempt at ABF-122 used ``...Out``; that
form does not appear anywhere else in the codebase.)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.constants import AgentMessageRole


class AgentDomainResponse(BaseModel):
    """GET /agents – one agent domain in the catalog visible to the user."""

    id: str
    name: str
    description: str

    model_config = {"from_attributes": True}


class AgentChatRequest(BaseModel):
    """POST /agents/{domain_id}/chat – ask the agent a question."""

    # The ceiling is settings.AGENT_MAX_MESSAGE_LENGTH so it can be tuned per
    # deployment, and it is enforced here rather than in the service so that
    # an over-long question is a 422 on the field that caused it — the same
    # contract every other write endpoint has.
    #
    # Read at import time, which is what pydantic's Field() requires: raising
    # the limit needs a restart, not just an .env edit. That is the same trade
    # every other schema-level bound in this codebase makes, and the limits
    # that must move without a restart (the daily quota, the history window)
    # are read through `settings` at call time instead.
    message: str = Field(
        ..., min_length=1, max_length=settings.AGENT_MAX_MESSAGE_LENGTH
    )

    # Omitted on the first question of a thread; supplied on every follow-up,
    # which is what lets the agent see what was already asked.
    #
    # Bounded at the width of the column it is matched against
    # (agent_conversations.id, String(36)): the value is only ever a uuid the
    # server itself issued, and without a ceiling the one unbounded string in
    # this request would be an id nobody can hold. Over-long is a 422 rather
    # than the 404 an unknown id gets, which is the honest answer — a
    # 40,000-character id is a malformed field, not a thread that was deleted.
    conversation_id: str | None = Field(default=None, max_length=36)

    @field_validator("message", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        """Trim before the length checks, so trailing whitespace neither
        passes an empty message nor fails a message that is exactly at the
        limit."""
        return value.strip() if isinstance(value, str) else value


class AgentSourceResponse(BaseModel):
    """A knowledge-base passage the answer was drawn from.

    Returned so the reader can see the answer is grounded, and so that a
    question the agent could not settle can be taken to a professional with
    the document name in hand. Provenance is the two fields ABF-120 stores —
    a readable name and a checkable link — and either may be absent, because
    some material is written in-house by the association.
    """

    title: str
    source_name: str | None = None
    source_url: str | None = None

    model_config = {"from_attributes": True}


class AgentMessageResponse(BaseModel):
    """One turn of a conversation, user or agent.

    **No `from_attributes`, deliberately.** agent_messages.content is
    encrypted at rest (AES-256-GCM, the same mechanism as
    DirectMessage.content), so validating an ORM row straight into this schema
    would ship base64 ciphertext to the client. The service decrypts and
    constructs these explicitly — the rule forum_service._to_response_dict()
    already follows for direct messages.

    `key_version` is omitted on purpose: it is a storage detail of the
    encryption epoch and no client has any use for it.
    """

    id: str
    role: AgentMessageRole
    content: str
    created_at: datetime


class AgentChatResponse(BaseModel):
    """The result of one exchange: both rows that were written, plus sources.

    The question is echoed back rather than left to the client to remember,
    because its `id` and `created_at` are the server's, and ABF-123 renders
    the thread from them.
    """

    conversation_id: str
    question: AgentMessageResponse
    answer: AgentMessageResponse
    sources: list[AgentSourceResponse]


class AgentConversationResponse(BaseModel):
    """GET /agents/{domain_id}/conversations/{id} – a whole thread.

    `started_at` / `last_message_at` are ABF-120's column names; ABF-123 sorts
    a member's threads by the latter, which is why agent_service advances it
    explicitly on every exchange.
    """

    id: str
    domain_id: str
    started_at: datetime
    last_message_at: datetime
    messages: list[AgentMessageResponse]

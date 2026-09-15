"""
Pydantic schemas for the AI agents — the domain catalog and its knowledge base
(ABF-120/121) and the chat flow (ABF-122).

Naming follows the rest of `app/schemas`: ``...Response`` for what goes out,
``...Request`` / ``...Create`` / ``...Update`` for what comes in. (The reverted
first attempt at ABF-122 used ``...Out``; that form does not appear anywhere
else in the codebase.)
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.constants import AgentMessageRole
from app.core.i18n import translate

# Mirrors the column widths on AgentKnowledgeEntry, so an over-long title comes
# back as a 422 naming the field instead of a database error naming nothing.
TITLE_MAX_LENGTH = 256
SOURCE_NAME_MAX_LENGTH = 256
SOURCE_URL_MAX_LENGTH = 1024


class AgentDomainResponse(BaseModel):
    """GET /agents – one agent domain in the catalog visible to the user."""

    id: str
    name: str
    description: str

    model_config = {"from_attributes": True}


class AgentKnowledgeEntryCreate(BaseModel):
    """POST /agents/{domain_id}/knowledge-entries – new knowledge base content.

    No domain_id: it is in the path, and accepting it in the body too would
    create a second, unauthorized way to say which domain is being written to.
    No updated_by either — that is the authenticated caller, not their claim.
    """

    title: str = Field(min_length=1, max_length=TITLE_MAX_LENGTH)
    content: str = Field(min_length=1)
    source_name: str | None = Field(None, max_length=SOURCE_NAME_MAX_LENGTH)
    source_url: str | None = Field(None, max_length=SOURCE_URL_MAX_LENGTH)


class AgentKnowledgeEntryUpdate(BaseModel):
    """PATCH /agents/{domain_id}/knowledge-entries/{entry_id} – partial update.

    Every field is optional, and only those actually present in the body are
    written. That is what lets a typo in a title be fixed without re-sending the
    content — and, because re-indexing is triggered by `content` being present,
    without paying for a round of embeddings that would produce identical
    chunks.

    `source_name` and `source_url` accept an explicit null, which clears them;
    both are nullable columns and a source that turns out to be wrong should be
    removable. `title` and `content` do not — they are NOT NULL, and an entry
    with no content is not a state the knowledge base has.
    """

    title: str | None = Field(None, min_length=1, max_length=TITLE_MAX_LENGTH)
    content: str | None = Field(None, min_length=1)
    source_name: str | None = Field(None, max_length=SOURCE_NAME_MAX_LENGTH)
    source_url: str | None = Field(None, max_length=SOURCE_URL_MAX_LENGTH)

    @field_validator("title", "content", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: Any) -> Any:
        """
        Runs only for keys actually present in the body — an omitted field keeps
        its `None` default and is skipped by the partial update.
        """
        if value is None:
            raise ValueError(translate("validation.field_not_clearable"))
        return value


class AgentKnowledgeEntryResponse(BaseModel):
    """One knowledge base entry, as returned to the professional who edits it.

    Chunks are not here. They are derived data with no meaning outside
    retrieval, and their count is an implementation detail of the chunker
    rather than something the editor authored.
    """

    id: str
    domain_id: str
    title: str
    content: str
    source_name: str | None
    source_url: str | None
    updated_by: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# The chat flow (ABF-122)
# ---------------------------------------------------------------------------


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
    # that must move without a restart (the daily quota, the history window,
    # the relevance floor) are read through `settings` at call time instead.
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
    """A knowledge-base document the answer was drawn from.

    Returned so the reader can see the answer is grounded, and so that a
    question the agent could not settle can be taken to a professional with
    the document name in hand. Provenance is the two fields ABF-120 stores —
    a readable name and a checkable link — and either may be absent, because
    some material is written in-house by the association.

    One entry per source, not per retrieved chunk: a long entry can contribute
    several chunks to one answer, and listing its title three times tells the
    reader nothing extra. agent_service._to_sources() does the collapsing.

    No `from_attributes`: these are built from rag_service.RetrievedChunk,
    which also carries a similarity `score` that has no business on screen.
    """

    title: str
    source_name: str | None = None
    source_url: str | None = None


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

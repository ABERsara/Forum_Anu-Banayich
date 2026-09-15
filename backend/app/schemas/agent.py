"""
Pydantic schemas for AI agent domains and their knowledge bases.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

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

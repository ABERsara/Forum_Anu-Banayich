"""
Pydantic schemas for professional queries.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import ProfessionalDomain, QueryStatus
from app.schemas.user import ProfessionalProfile, UserPublic


class ProfessionalQueryCreate(BaseModel):
    """POST /advice/questions – ask a professional question."""

    content: str = Field(..., min_length=10, max_length=2000)
    is_public: bool = False
    show_real_name: bool = False

    # If targeting a specific professional:
    professional_id: str | None = None

    # If asking a general question (professional_id is None):
    domain: ProfessionalDomain | None = None


class ProfessionalQueryResponse(BaseModel):
    """A question as seen by the asker or the professional."""

    id: str
    content: str
    answer: str | None = None
    is_public: bool
    status: QueryStatus
    is_featured: bool
    domain: ProfessionalDomain | None = None
    professional: ProfessionalProfile | None = None
    # Asker info: only shown if show_real_name=True, otherwise alias
    asker_alias: str  # e.g. "אלמנה – ספרדי"
    asker: UserPublic | None = None  # only if show_real_name=True
    created_at: datetime
    answered_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProfessionalAnswerRequest(BaseModel):
    """PUT /advice/questions/{id}/answer – professional submits an answer."""

    answer: str = Field(..., min_length=10, max_length=5000)


class PublicQAResponse(BaseModel):
    """A public answered question visible to the whole group/sector."""

    id: str
    content: str
    answer: str
    domain: ProfessionalDomain | None = None
    is_featured: bool
    answered_at: datetime | None = None

    model_config = {"from_attributes": True}

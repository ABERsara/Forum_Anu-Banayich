"""
Pydantic schemas for user-related endpoints.

UserPublic      → what any user sees about another user (name only, no PII)
UserProfile     → what a user sees about themselves
UserAdminView   → what an admin sees (includes status, documents)
RegistrationItem → pending registration in admin queue

Registration review (SPEC §8.2 – the admin deciding on one request):
DocumentAdminView     → one uploaded document, metadata only
RegistrationDetailView → the whole request as the deciding admin reads it
"""

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import (
    AccountStatus,
    DocumentType,
    ProfessionalDomain,
    Sector,
    UserRole,
    UserType,
)


class UserPublic(BaseModel):
    """Minimal info shown to other users (name only – no contact details)."""

    id: str
    first_name: str
    last_name: str

    model_config = {"from_attributes": True}


class UserProfile(BaseModel):
    """Full profile for the authenticated user themselves."""

    id: str
    first_name: str
    last_name: str
    email: EmailStr
    role: UserRole
    user_type: UserType | None = None
    sector: Sector | None = None
    birth_date: date | None = None
    account_status: AccountStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class UserAdminView(BaseModel):
    """Admin sees this when reviewing a registration."""

    id: str
    first_name: str
    last_name: str
    email: str
    phone: str | None = None
    role: UserRole
    user_type: UserType | None = None
    sector: Sector | None = None
    birth_date: date | None = None
    id_number: str | None = None
    account_status: AccountStatus
    first_approver_id: str | None = None
    second_approver_id: str | None = None
    approved_at: datetime | None = None
    rejection_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentAdminView(BaseModel):
    """
    One document uploaded with a registration — metadata only.

    What the file *is*, when it arrived and how long it stays valid is what
    tells the admin whether the request is complete; the file itself is opened
    through a time-limited presigned URL (SPEC §9.1), which is not built yet.

    Two columns are deliberately not in this contract:
      - `storage_url` — the path inside the bucket. It is not a link anyone
        can open, and handing it out is a private detail of how files are
        stored, not part of reviewing a registration.
      - `content_hash` — an integrity check that belongs to downloading the
        file. On its own it is a fingerprint of the document's contents, and
        an admin cannot decide anything from it.
    """

    id: str
    doc_type: DocumentType
    #: Some documents carry their own expiry (an ID card, a passport); most do not.
    expires_on: date | None = None
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class RegistrationDetailView(UserAdminView):
    """
    One registration as the deciding admin reads it: the whole applicant
    profile UserAdminView carries, plus the documents uploaded with it.

    The queue (GET /admin/registrations) stays on UserAdminView. It answers
    "who is waiting", and it never renders a document, so fetching every
    applicant's documents there would be a query per row for nothing.
    """

    #: Oldest upload first — the order the applicant filed them in.
    documents: list[DocumentAdminView] = Field(default_factory=list)


class RegistrationApproveRequest(BaseModel):
    """Admin approves a pending registration."""

    pass  # no body needed – the action is clear from the endpoint


class RegistrationRejectRequest(BaseModel):
    """Admin rejects a pending registration."""

    reason: str = Field(..., min_length=5, max_length=100)


class SuspendUserRequest(BaseModel):
    """Suspend a user for N hours."""

    hours: int = Field(48, gt=0)
    reason: str = Field(..., min_length=5, max_length=100)


class ProfessionalProfile(BaseModel):
    """What a regular user sees when browsing professionals."""

    id: str
    first_name: str
    last_name: str
    professional_domain: ProfessionalDomain
    professional_description: str | None = None
    # No email, phone, or other PII

    model_config = {"from_attributes": True}


class ProfessionalUpdateRequest(BaseModel):
    """Admin updates a professional's profile."""

    professional_domain: ProfessionalDomain | None = None
    professional_groups: list[str] | None = None
    professional_sectors: list[str] | None = None
    professional_description: str | None = None
    is_active_professional: bool | None = None

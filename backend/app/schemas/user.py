"""
Pydantic schemas for user-related endpoints.

UserPublic      → what any user sees about another user (name only, no PII)
UserProfile     → what a user sees about themselves
UserAdminView   → what an admin sees (includes status, documents)
RegistrationItem → pending registration in admin queue
"""

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.core.constants import (
    AccountStatus,
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

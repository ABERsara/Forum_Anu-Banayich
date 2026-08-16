"""
Pydantic schemas for user-related endpoints.

UserPublic      → what any user sees about another user (name only, no PII)
UserProfile     → what a user sees about themselves
UserAdminView   → what an admin sees (includes status, documents)
RegistrationItem → pending registration in admin queue

Professional catalog (SPEC §6.1):
ProfessionalProfile        → what a member browsing the catalog sees (no PII)
ProfessionalAdminView      → what the admin managing the catalog sees
ProfessionalCreateRequest  → admin adds a professional
ProfessionalUpdateRequest  → admin edits a professional (partial update)
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.constants import (
    AccountStatus,
    GroupVisibility,
    ProfessionalDomain,
    Sector,
    SectorVisibility,
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


#: Longest "short description" the catalog will show (SPEC §6.1 – "תיאור קצר").
PROFESSIONAL_DESCRIPTION_MAX_LENGTH = 500

#: Which bereavement groups a professional serves. "all" (GroupVisibility.ALL)
#: means every group; anything else is an explicit UserType value.
ProfessionalGroups = list[GroupVisibility]

#: Which sectors a professional serves. "all" (SectorVisibility.ALL) means every
#: sector; anything else is an explicit Sector value.
ProfessionalSectors = list[SectorVisibility]


class ProfessionalAdminView(BaseModel):
    """
    A professional as the admin managing the catalog sees them.

    Unlike ProfessionalProfile (member-facing, no PII) this carries the contact
    details and the routing fields the admin edits: which groups and sectors the
    professional serves and whether they are listed at all.
    """

    id: str
    first_name: str
    last_name: str
    # str, not EmailStr, like UserAdminView: a read model must not fail on rows
    # that are already in the database. Input is validated on the way in.
    email: str
    phone: str | None = None
    role: UserRole
    account_status: AccountStatus
    professional_domain: ProfessionalDomain | None = None
    professional_groups: ProfessionalGroups = Field(default_factory=list)
    professional_sectors: ProfessionalSectors = Field(default_factory=list)
    professional_description: str | None = None
    is_active_professional: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("professional_groups", "professional_sectors", mode="before")
    @classmethod
    def _null_reads_as_empty(cls, value: Any) -> Any:
        """
        Rows created before the catalog existed hold NULL in these JSON columns;
        the API contract is always a list, so the client never branches on null.
        """
        return [] if value is None else value


class ProfessionalCreateRequest(BaseModel):
    """
    Admin adds a professional to the catalog (POST /admin/professionals).

    No password: the account is created without usable credentials and the
    professional receives them through the invitation flow (Sprint 5).
    """

    first_name: str = Field(..., min_length=2, max_length=100, examples=["ישראל"])
    last_name: str = Field(..., min_length=2, max_length=100, examples=["כהן"])
    email: EmailStr = Field(..., examples=["cohen.law@example.com"])
    phone: str | None = Field(
        None, min_length=9, max_length=15, examples=["0501234567"]
    )
    professional_domain: ProfessionalDomain = Field(
        ..., examples=[ProfessionalDomain.LAWYER]
    )
    # min_length=1: a professional serving no group (or no sector) is invisible
    # to every member, which is never what the admin meant to create.
    professional_groups: ProfessionalGroups = Field(
        ..., min_length=1, examples=[[GroupVisibility.ALL]]
    )
    professional_sectors: ProfessionalSectors = Field(
        ..., min_length=1, examples=[[SectorVisibility.HASIDIC]]
    )
    professional_description: str | None = Field(
        None, max_length=PROFESSIONAL_DESCRIPTION_MAX_LENGTH
    )
    is_active_professional: bool = True


class ProfessionalUpdateRequest(BaseModel):
    """
    Admin updates a professional's profile (PUT /admin/professionals/{id}).

    Partial update: only the fields present in the request body are written, so
    an admin toggling `is_active_professional` cannot accidentally blank out the
    description. Sending `professional_description: null` clears it on purpose;
    the other fields reject an explicit null, because a professional with no
    domain, no groups or no sectors would drop out of the catalog silently.
    """

    professional_domain: ProfessionalDomain | None = None
    professional_groups: ProfessionalGroups | None = Field(None, min_length=1)
    professional_sectors: ProfessionalSectors | None = Field(None, min_length=1)
    professional_description: str | None = Field(
        None, max_length=PROFESSIONAL_DESCRIPTION_MAX_LENGTH
    )
    is_active_professional: bool | None = None

    @field_validator(
        "professional_domain",
        "professional_groups",
        "professional_sectors",
        "is_active_professional",
        mode="before",
    )
    @classmethod
    def _reject_explicit_null(cls, value: Any) -> Any:
        """
        Runs only for keys actually present in the body — an omitted field keeps
        its `None` default and is skipped by the partial update.
        """
        if value is None:
            raise ValueError("לא ניתן לרוקן שדה זה. יש להשמיטו כדי להשאירו ללא שינוי.")
        return value

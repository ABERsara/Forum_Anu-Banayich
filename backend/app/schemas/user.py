"""
Pydantic schemas for user-related endpoints.

UserPublic      → what any user sees about another user (name only, no PII)
UserProfile     → what a user sees about themselves
UserAdminView   → what an admin sees (includes status, documents)
RegistrationItem → pending registration in admin queue

Moderator roster (SPEC §7 – the admin side of moderation):
ModeratorCell           → one group×sector cell a moderator oversees
ModeratorAdminView      → a moderator as the admin managing the roster sees them
ModeratorCreateRequest  → admin adds a moderator
ModeratorUpdateRequest  → admin edits a moderator (partial update)
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator

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


# ---------------------------------------------------------------------------
# Moderator roster – admin side (SPEC §7)
#
# The platform's content is organised as a matrix of cells: one bereavement
# group (UserType) crossed with one sector (Sector). A moderator oversees a
# set of those cells, e.g. "widows in the Sephardic sector".
# ---------------------------------------------------------------------------


class ModeratorCell(BaseModel):
    """
    One cell of the group×sector matrix a moderator oversees.

    This is the S2 contract, and it is the same shape in all three places:
    the JSON stored in User.moderator_cells, the body the admin UI submits,
    and the objects it renders — `{"group": "widow", "sector": "sephardic"}`.

    Both axes are the concrete enums, never the "all" wildcard the *content*
    visibility enums carry: a moderator is responsible for named cells, so
    "every cell" is expressed by ticking them, and the roster shows exactly
    what a moderator answers for.
    """

    group: UserType = Field(..., examples=[UserType.WIDOW])
    sector: Sector = Field(..., examples=[Sector.SEPHARDIC])

    # frozen → hashable, which is what lets duplicates collapse below.
    model_config = {"frozen": True}


#: Declaration order of the two enums, so cells sort into the same order the
#: admin UI lays its matrix out in.
_GROUP_ORDER: dict[UserType, int] = {group: i for i, group in enumerate(UserType)}
_SECTOR_ORDER: dict[Sector, int] = {sector: i for i, sector in enumerate(Sector)}


def _canonical_cells(cells: list[ModeratorCell]) -> list[ModeratorCell]:
    """
    Drop duplicates and sort into one canonical order.

    Two admins ticking the same cells in a different order must produce the
    same stored JSON: it keeps the audit trail free of edits that changed
    nothing, and it lets the client compare what it sent with what came back.
    """
    unique = dict.fromkeys(cells)  # dedupes, first occurrence wins
    return sorted(
        unique,
        key=lambda cell: (_GROUP_ORDER[cell.group], _SECTOR_ORDER[cell.sector]),
    )


class _CanonicalCellsMixin(BaseModel):
    """
    Normalises `moderator_cells` on the way in.

    Shared by the create and update requests so the rule cannot drift between
    them; `check_fields=False` because the field itself lives on the subclasses.
    """

    @field_validator("moderator_cells", check_fields=False)
    @classmethod
    def _normalise(
        cls, value: list[ModeratorCell] | None
    ) -> list[ModeratorCell] | None:
        return None if value is None else _canonical_cells(value)


class ModeratorAdminView(BaseModel):
    """
    A moderator as the admin managing the roster sees them: who they are, the
    cells they were assigned, and where their alerts are sent.
    """

    id: str
    first_name: str
    last_name: str
    # str, not EmailStr, like UserAdminView: a read model must not fail on rows
    # that are already in the database. Input is validated on the way in.
    email: str
    role: UserRole
    account_status: AccountStatus
    moderator_cells: list[ModeratorCell] = Field(default_factory=list)
    alert_email: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("moderator_cells", mode="before")
    @classmethod
    def _null_reads_as_empty(cls, value: Any) -> Any:
        """
        A moderator row can hold NULL in the JSON column; the API contract is
        always a list, so the client never branches on null.
        """
        return [] if value is None else value


class ModeratorCreateRequest(_CanonicalCellsMixin):
    """
    Admin adds a moderator (POST /admin/moderators).

    No password: the account is created without usable credentials and the
    moderator receives them through the invitation flow (out of scope here).
    """

    first_name: str = Field(..., min_length=2, max_length=100, examples=["שרה"])
    last_name: str = Field(..., min_length=2, max_length=100, examples=["לוי"])
    email: EmailStr = Field(..., examples=["sara.levi@example.com"])
    # min_length=1: a moderator overseeing no cell oversees nothing, which is
    # never what the admin meant to create.
    moderator_cells: list[ModeratorCell] = Field(
        ...,
        min_length=1,
        examples=[
            [
                {"group": UserType.WIDOW, "sector": Sector.SEPHARDIC},
                {"group": UserType.WIDOWER, "sector": Sector.SEPHARDIC},
            ]
        ],
    )
    #: Where report alerts go. Optional — without it they go to `email`.
    alert_email: EmailStr | None = Field(None, examples=["alerts.sara@example.com"])


class ModeratorUpdateRequest(_CanonicalCellsMixin):
    """
    Admin updates a moderator (PATCH /admin/moderators/{id}).

    Partial update: only the fields present in the request body are written,
    so changing the alert address cannot silently drop the cell assignment.

    Sending `alert_email: null` clears it on purpose — alerts fall back to the
    moderator's own address. `moderator_cells` rejects an explicit null,
    because a moderator with no cells would answer for nothing while still
    appearing on the roster; removing them is what DELETE is for.
    """

    moderator_cells: list[ModeratorCell] | None = Field(None, min_length=1)
    alert_email: EmailStr | None = None

    @field_validator("moderator_cells", mode="before")
    @classmethod
    def _reject_explicit_null(cls, value: Any) -> Any:
        """
        Runs only for keys actually present in the body — an omitted field
        keeps its `None` default and is skipped by the partial update.
        """
        if value is None:
            raise ValueError("לא ניתן לרוקן שדה זה. יש להשמיטו כדי להשאירו ללא שינוי.")
        return value

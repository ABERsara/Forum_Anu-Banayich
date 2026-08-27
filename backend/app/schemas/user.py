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

Registration review (SPEC §8.2 – the admin deciding on one request):
DocumentAdminView     → one uploaded document, metadata only
RegistrationDetailView → the whole request as the deciding admin reads it

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
    DocumentType,
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


class UserModerationCard(BaseModel):
    """
    GET /moderator/users/{id}/card – one user's moderation history, as the
    moderator responsible for their cell sees it (SPEC §7.3, "כרטיס משתמש").

    Deliberately without contact details: a moderator moderates content, and
    the decision in front of them rests on the counts and the cell, not on
    the person's email, phone or ID number. UserAdminView carries those, and
    is an admin view for exactly that reason.
    """

    id: str
    first_name: str
    last_name: str
    user_type: UserType | None = None
    sector: Sector | None = None
    account_status: AccountStatus

    # Reports filed against this user. "valid" and "invalid" are the
    # moderator decisions already made; the rest are still pending.
    reports_against_total: int
    reports_against_valid: int
    reports_against_invalid: int

    # Reports this user filed about others. A high false_reports_filed is
    # what SPEC §7.2 calls a "מדווח-שגוי תכוף".
    reports_filed_total: int
    false_reports_filed: int

    is_suspended: bool
    suspended_until: datetime | None = None


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

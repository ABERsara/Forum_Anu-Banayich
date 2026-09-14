"""
Pydantic schemas for content reports.
"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.core.constants import (
    PostStatus,
    ReportDecision,
    ReportReason,
    ReportTargetType,
)
from app.core.i18n import translate


class ReportCreate(BaseModel):
    """POST /forum/posts/{id}/report (or similar) – file a report."""

    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    description: str | None = None


class ReportResponse(BaseModel):
    """A single report as seen by a moderator."""

    id: str
    #: Null once the reporter's account is closed and the report is anonymized
    #: (§9.4 keeps reports for five years, without the person). Nothing in
    #: ABF-112 writes null; the deletion flow is task 8's.
    reporter_id: str | None
    reported_user_id: str
    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    description: str | None = None
    decision: ReportDecision
    moderator_id: str | None = None
    moderator_note: str | None = None
    decided_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportWithContent(ReportResponse):
    """
    A report enriched with the reported content, for moderator views.

    One shape for both target types, since a list mixes them (SPEC §7.3) —
    each group of fields is populated only for its own target_type, and left
    at its default for the other. FORUM_POST content is always present on a
    row of that type (a post is never hard-deleted); DIRECT_MESSAGE content
    is present only in a single report's detail view, never in a list — see
    moderator.py's _to_report_with_content() and get_report().
    """

    # FORUM_POST only.
    content_title: str | None = None
    content_text: str | None = None
    content_status: PostStatus | None = None
    report_count: int | None = None

    # DIRECT_MESSAGE only.
    #: The decrypted message, populated exclusively by GET /reports/{id} —
    #: an audited read (ABF-113, spec §9.3) — and never by the pending or
    #: history list. None on CLOSED_ACCOUNT_DELETED even there: §9.4 keeps
    #: the report once the reported-on account is deleted, not its content.
    message_content: str | None = None
    #: Whether a moderator's VALID decision hid this message (hidden_at is
    #: not None) — a state, not content, so unlike message_content this is
    #: safe to show in list views too.
    message_hidden: bool | None = None


class ReportDecideRequest(BaseModel):
    """POST /moderator/reports/{id}/decide – moderator makes a decision."""

    decision: ReportDecision
    # Required, unlike Report.moderator_note being nullable in the DB: rows
    # predating this endpoint have no note, but no new decision may be made
    # without one. The note is the moderator's justification for deleting a
    # bereaved user's post or for dismissing their report (SPEC §7.3,
    # "הערת מבקר (לתיעוד)"), and it is the only record of *why* once the
    # content itself is gone.
    note: str = Field(..., min_length=5, max_length=1000)

    @field_validator("decision")
    @classmethod
    def decision_must_resolve_the_report(cls, v: ReportDecision) -> ReportDecision:
        """PENDING is the state a report starts in, not a decision to submit."""
        if v == ReportDecision.PENDING:
            raise ValueError(translate("validation.decision_required"))
        return v

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, v: str) -> str:
        """min_length alone would accept a note of five spaces."""
        note = v.strip()
        if len(note) < 5:
            raise ValueError(translate("validation.review_note_too_short"))
        return note


class ReportListResponse(BaseModel):
    items: list[ReportWithContent]
    total: int
    pending_count: int


class ReportHistoryResponse(BaseModel):
    """
    GET /moderator/reports/history – reports this moderator's cells already
    processed. Paginated (unlike the pending list, which is a work queue the
    moderator is meant to empty): history only grows.
    """

    items: list[ReportWithContent]
    total: int
    page: int
    page_size: int

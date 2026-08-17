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


class ReportCreate(BaseModel):
    """POST /forum/posts/{id}/report (or similar) – file a report."""

    target_type: ReportTargetType
    target_id: str
    reason: ReportReason
    description: str | None = None


class ReportResponse(BaseModel):
    """A single report as seen by a moderator."""

    id: str
    reporter_id: str
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
    """A report enriched with the reported content, for moderator views."""

    content_title: str
    content_text: str
    content_status: PostStatus
    report_count: int


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
            raise ValueError("יש לבחור החלטה: מוצדק או שגוי")
        return v

    @field_validator("note")
    @classmethod
    def note_must_not_be_blank(cls, v: str) -> str:
        """min_length alone would accept a note of five spaces."""
        note = v.strip()
        if len(note) < 5:
            raise ValueError("הערת המבקר חייבת לכלול לפחות 5 תווים")
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

"""
Pydantic schemas for content reports.
"""

from datetime import datetime

from pydantic import BaseModel

from app.core.constants import ReportDecision, ReportReason, ReportTargetType


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


class ReportDecideRequest(BaseModel):
    """POST /moderator/reports/{id}/decide – moderator makes a decision."""

    decision: ReportDecision
    note: str | None = None


class ReportListResponse(BaseModel):
    items: list[ReportResponse]
    total: int
    pending_count: int

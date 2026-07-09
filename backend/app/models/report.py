"""
Report model.

Any user can report a ForumPost, DirectMessage, or ProfessionalQuery.

Automation rules (enforced in report_service.py):
    1st report  → email notification to responsible moderator
    2nd report  → auto-hide the content + urgent notification
    3+ reports  → repeated contact attempt with moderator
    3+ valid reports in 7 days → auto-suspend user 48h
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import ReportDecision, ReportReason, ReportTargetType
from app.db.base import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # ------------------------------------------------------------------
    # Who reported
    # ------------------------------------------------------------------
    reporter_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # ------------------------------------------------------------------
    # What was reported
    # ------------------------------------------------------------------
    target_type: Mapped[ReportTargetType] = mapped_column(
        Enum(ReportTargetType), nullable=False
    )
    # ID of the ForumPost / DirectMessage / ProfessionalQuery
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # The user who authored the reported content
    reported_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # ------------------------------------------------------------------
    # Report details
    # ------------------------------------------------------------------
    reason: Mapped[ReportReason] = mapped_column(Enum(ReportReason), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------
    decision: Mapped[ReportDecision] = mapped_column(
        Enum(ReportDecision), nullable=False, default=ReportDecision.PENDING
    )
    moderator_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    moderator_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------
    reporter: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="reports_filed", foreign_keys=[reporter_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Report id={self.id} target={self.target_type} decision={self.decision}>"
        )

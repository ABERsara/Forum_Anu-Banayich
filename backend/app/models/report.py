"""
Report model.

Any user can report a ForumPost or a DirectMessage she received
(ProfessionalQuery reporting has no endpoint yet).

Automation rules (enforced in report_service.py):
    1st report  → email notification to responsible moderator
    2nd report  → auto-hide the content + urgent notification
    3+ reports  → repeated contact attempt with moderator
    3+ valid reports in 7 days → auto-suspend user 48h
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
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
    #: NULL means "anonymized" — the reporter closed her account and §9.4 keeps
    #: the report (5 years) while removing the person from it. Nullable rather
    #: than pointed at a shared "deleted user" row: a placeholder row is still
    #: a join target, and anything that can be joined can be correlated back
    #: across every report it appears on.
    #:
    #: Nothing in ABF-112 writes NULL — filing always records the reporter.
    #: The column is nullable now because the report schema is frozen for
    #: tasks 6-8, and the deletion flow (task 8) must not need a migration of
    #: its own to run.
    reporter_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
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
    # The reported content, captured at report time (ABF-112)
    # ------------------------------------------------------------------
    #: The reported private message, encrypted with the same AES-256-GCM
    #: scheme as DirectMessage.content (app/core/encryption.py). NULL for a
    #: forum-post report, whose content the moderator reads from the still-
    #: visible post itself.
    #:
    #: A copy rather than a read through target_id, for two reasons that both
    #: end with the moderator seeing nothing:
    #:
    #:   * §5.3's 1,000-message cap deletes old messages. Pruning skips a
    #:     message under an *open* report, but the moment a report is decided
    #:     the exemption lapses — and a decided report still has to say what
    #:     it was about for the 5 years §9.4 keeps it.
    #:   * it pins the text to what was actually reported, so a later message
    #:     cannot be presented as the one that was.
    #:
    #: Encrypted rather than stored in the clear because copying a private
    #: message out of `direct_messages` into `reports` must not be the step
    #: that quietly declassifies it: exactly one message, still sealed, and
    #: read only through the moderator path (task 6).
    reported_content: Mapped[str | None] = mapped_column(Text, nullable=True)

    #: Which MESSAGE_ENCRYPTION_KEY epoch encrypted `reported_content` — same
    #: role as DirectMessage.key_version, and NULL exactly when there is no
    #: snapshot to decrypt.
    reported_content_key_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

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
    reporter: Mapped["User | None"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "User", back_populates="reports_filed", foreign_keys=[reporter_id]
    )

    def __repr__(self) -> str:
        return (
            f"<Report id={self.id} target={self.target_type} decision={self.decision}>"
        )

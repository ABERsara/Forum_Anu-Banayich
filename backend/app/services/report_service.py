"""
Report and moderation service.

Implements the automated protection rules from spec section 7.

Rules:
  1st report on a post  → email to responsible moderator
  2nd report (different user) → auto-hide post + urgent notification
  3+ valid reports on a USER in 7 days → auto-suspend 48h + notify admin
  5+ false reports from same USER in 30 days → restrict that user's reporting

TODO list for junior developer:
  [ ] implement file_report()
  [ ] implement decide_report()
  [ ] implement get_pending_reports() (for moderator)
  [ ] implement _check_auto_suspension()
  [ ] implement _check_frequent_false_reporter()
"""

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import PostStatus, ReportTargetType, UserRole
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDecideRequest
from app.services.email_service import send_moderator_alert, send_urgent_moderator_alert

logger = logging.getLogger(__name__)


def file_report(db: Session, data: ReportCreate, reporter: User) -> Report:
    """
    File a new report on a piece of content.

    Only FORUM_POST is supported today – DIRECT_MESSAGE and PROFESSIONAL_QUERY
    reporting are out of scope for this sprint (no endpoint wires them yet).
    """
    if data.target_type != ReportTargetType.FORUM_POST:
        raise HTTPException(
            status_code=400, detail="סוג תוכן זה אינו נתמך לדיווח כרגע."
        )

    # Row-level lock: two reports racing on the same post must not lose an
    # increment. No-op on SQLite (dev), enforced on PostgreSQL (production) –
    # same pattern as forum_service.delete_post().
    post = (
        db.query(ForumPost)
        .filter(ForumPost.id == data.target_id)
        .with_for_update()
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")

    _ensure_not_duplicate_report(db, reporter, data)

    report = Report(
        reporter_id=reporter.id,
        target_type=data.target_type,
        target_id=data.target_id,
        reported_user_id=post.author_id,
        reason=data.reason,
        description=data.description,
    )
    db.add(report)
    # report.id is a client-side default (uuid4) — only populated once flushed.
    db.flush()

    post.report_count += 1
    if post.report_count == 2:
        post.status = PostStatus.HIDDEN

    db.commit()
    db.refresh(report)

    # Notifications run strictly after the commit: if the commit had failed,
    # a moderator must never be alerted about a report that was never saved.
    # A failure to notify must equally never turn an already-saved report
    # into a failed request — log it and move on, same policy as
    # send_otp_email()'s SMTP failure handling.
    try:
        _notify_moderators(db, post, report)
    except Exception:
        logger.exception("Failed to notify moderators for report %s", report.id)

    return report


def _ensure_not_duplicate_report(
    db: Session, reporter: User, data: ReportCreate
) -> None:
    """Block a second report from the same user on the same target."""
    existing = (
        db.query(Report)
        .filter(
            Report.reporter_id == reporter.id,
            Report.target_type == data.target_type,
            Report.target_id == data.target_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="כבר דיווחת על תוכן זה.")


def _notify_moderators(db: Session, post: ForumPost, report: Report) -> None:
    """
    Send the escalation email(s) for this report, based on the post's
    already-committed report_count (spec section 7.1):
      1st report  → email to moderators
      2nd+ report → urgent email (repeated on every report from here on)

    Runs strictly after file_report()'s db.commit() — if the commit had
    failed, a moderator must never be alerted about a report that was never
    actually saved.
    """
    if post.report_count == 1:
        for email in _moderator_emails_for(db):
            send_moderator_alert(email, report.id, post.content[:100])
    elif post.report_count >= 2:
        for email in _moderator_emails_for(db):
            send_urgent_moderator_alert(email, report.id)


def _moderator_emails_for(db: Session) -> list[str]:
    """
    Return contact addresses for all active moderators.

    TEMPORARY: broadcasts to every moderator, regardless of which group/sector
    they're actually responsible for — moderator_cells matching isn't
    implemented anywhere yet. Sprint 4 will replace only this function's body
    with a real lookup (e.g. get_moderator_for_cell(post.group_visibility,
    post.sector_visibility)) once that mechanism exists; callers in
    file_report()/_escalate() won't need to change.
    """
    moderators = db.query(User).filter(User.role == UserRole.MODERATOR).all()
    return [m.alert_email or m.email for m in moderators]


def decide_report(
    db: Session,
    report_id: str,
    data: ReportDecideRequest,
    moderator: User,
) -> Report:
    """
    Moderator decides on a report (VALID or INVALID).

    TODO:
      1. Load report, verify it's PENDING
      2. Update decision, moderator_id, decided_at, moderator_note
      3. If VALID:
           - If target is a ForumPost: delete it (status = DELETED)
           - Notify the reported user
           - Call _check_auto_suspension() for the reported user
      4. If INVALID:
           - If content was auto-hidden (status == HIDDEN): restore to VISIBLE
           - Call _check_frequent_false_reporter() for the original reporter
      5. Log to audit_log
      6. Return updated report
    """
    # TODO: implement this function
    raise NotImplementedError("decide_report() is not yet implemented")


def get_pending_reports(db: Session, moderator: User) -> list[Report]:
    """
    Return pending reports for the moderator's assigned cells.

    TODO:
      1. Load moderator.moderator_cells (JSON list of {group, sector} dicts)
      2. For each cell, find reports on content authored by users in that cell
      3. Filter decision == PENDING
      4. Order by report_count DESC (most-reported first)
    """
    # TODO: implement this function
    raise NotImplementedError("get_pending_reports() is not yet implemented")


def _check_auto_suspension(db: Session, reported_user: User) -> None:
    """
    Check if the reported user should be automatically suspended.

    Rule: 3+ valid reports in 7 days → suspend 48 hours + notify admin

    TODO:
      1. Count reports with decision=VALID against reported_user in last 7 days
      2. If >= 3 and not already suspended: call suspend_user()
    """
    # TODO: implement this function
    pass


def _check_frequent_false_reporter(db: Session, reporter: User) -> None:
    """
    Check if this user is filing too many false reports.

    Rule: 5+ INVALID reports filed by same user in 30 days → restrict + notify moderator

    TODO:
      1. Count reports filed BY reporter with decision=INVALID in last 30 days
      2. If >= 5: add a report limit flag on the user
    """
    # TODO: implement this function
    pass

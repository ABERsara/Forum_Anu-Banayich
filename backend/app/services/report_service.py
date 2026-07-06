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


from sqlalchemy.orm import Session

from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDecideRequest


def file_report(db: Session, data: ReportCreate, reporter: User) -> Report:
    """
    File a new report on a piece of content.

    TODO:
      1. Verify target exists and reporter hasn't already reported this target
      2. Create Report object, save to DB
      3. Increment report_count on the target
      4. If report_count == 1 → send email to moderator (find the right one)
      5. If report_count == 2 → auto-hide content + send urgent notification
      6. Return the report
    """
    # TODO: implement this function
    raise NotImplementedError("file_report() is not yet implemented")


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

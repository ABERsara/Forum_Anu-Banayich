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
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import Session

from app.core.constants import (
    AccountStatus,
    AuditAction,
    PostStatus,
    ReportDecision,
    ReportTargetType,
    UserRole,
)
from app.models.forum import DirectMessage, ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDecideRequest
from app.services import forum_service
from app.services.audit_service import build_entry
from app.services.email_service import (
    send_direct_message_report_alert,
    send_moderator_alert,
    send_urgent_moderator_alert,
)

logger = logging.getLogger(__name__)

#: A content type nothing wires a report endpoint to yet. Translation keys
#: rather than display text, per the i18n rule that the server names the
#: reason and the client renders it in the reader's language.
_UNSUPPORTED_TARGET_MESSAGE = "errors.report_unsupported_target"

#: The reported content is not there. Only ever raised for a forum post — a
#: private message that does not exist is answered by the same 403 as one
#: belonging to somebody else, so that neither reply confirms an id.
_TARGET_NOT_FOUND_MESSAGE = "errors.report_target_not_found"

#: §7.1 step 4 — one report per user per piece of content.
_DUPLICATE_MESSAGE = "errors.report_duplicate"

#: Moderator-side keys, replacing the Hebrew literals that stood here before
#: ABF-112. Same three distinctions as before — no such report, no such
#: content, not your cell — none of which say anything a moderator does not
#: already know from her own report list.
_REPORT_NOT_FOUND_MESSAGE = "errors.report_not_found"
_REPORTED_CONTENT_NOT_FOUND_MESSAGE = "errors.reported_content_not_found"
_REPORT_FORBIDDEN_MESSAGE = "errors.report_forbidden"


def file_report(db: Session, data: ReportCreate, reporter: User) -> Report:
    """
    File a new report on a piece of content, and alert the moderators
    responsible for the cell it came from (§7.1).

    Two content types are wired: FORUM_POST, and — since ABF-112 — a
    DIRECT_MESSAGE the reporter received. PROFESSIONAL_QUERY has no endpoint
    yet and is refused here rather than half-handled.

    The two paths diverge enough to be separate functions: a reported post
    stays readable where it is and carries a report_count that drives §7.1's
    auto-hide, while a reported private message is unreadable by anybody but
    its two participants and so has to be captured into the report itself.
    What they share — one report per user per target, and who gets told —
    stays shared.
    """
    if data.target_type == ReportTargetType.DIRECT_MESSAGE:
        return _file_direct_message_report(db, data, reporter)
    if data.target_type != ReportTargetType.FORUM_POST:
        raise HTTPException(status_code=400, detail=_UNSUPPORTED_TARGET_MESSAGE)

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
        raise HTTPException(status_code=404, detail=_TARGET_NOT_FOUND_MESSAGE)

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


def _file_direct_message_report(
    db: Session, data: ReportCreate, reporter: User
) -> Report:
    """
    Report one private message the reporter received (§7.1 steps 3-5).

    Exactly one message ends up in the report, and it is the one that was
    reported: `get_received_message()` resolves the id the caller named, and
    nothing here ever widens that to the conversation it sits in. A moderator
    reading this report therefore has no handle on the message before or
    after it — §5.3 lets her see content a user consented to hand over, and
    consent was given for one message.

    The snapshot is the message's stored ciphertext, copied byte for byte
    along with its key_version. Not decrypt-then-re-encrypt: this way the
    plaintext is never materialised while filing a report, so there is no
    moment at which it could reach a log line, a traceback frame or an error
    body. It also cannot drift from what was reported, which a second
    encryption of freshly-read text could.

    Why a copy at all, rather than reading `target_id` when a moderator opens
    the report: §5.3's 1,000-message cap deletes old messages, and the
    exemption that protects a reported one lasts only while its report is
    PENDING. Without the copy a decided report would, sooner or later, be a
    report about nothing — for the remaining years of the five §9.4 keeps it.
    """
    message = forum_service.get_received_message(db, reporter, data.target_id)

    _ensure_not_duplicate_report(db, reporter, data)

    report = Report(
        reporter_id=reporter.id,
        target_type=data.target_type,
        target_id=message.id,
        reported_user_id=message.sender_id,
        reason=data.reason,
        description=data.description,
        reported_content=message.content,
        reported_content_key_version=message.key_version,
    )
    db.add(report)
    # report.id is a client-side default (uuid4) — only populated once flushed,
    # and the audit entry below has to name it.
    db.flush()

    # §9.3: filing this report is what opens someone else's private message to
    # a moderator, so the consent itself is the auditable event — not the
    # later read. Built rather than log_action()'d because log_action() commits
    # on its own: a report that is saved without its audit row, or an audit row
    # for a report that was never saved, are both worse than neither.
    #
    # Ids and a reason code only. The one thing this entry must never carry is
    # the message it is about.
    db.add(
        build_entry(
            actor=reporter,
            action=AuditAction.DIRECT_MESSAGE_REPORTED,
            entity_type="DirectMessage",
            entity_id=message.id,
            details={"report_id": report.id, "reason": report.reason.value},
        )
    )
    db.commit()
    db.refresh(report)

    # After the commit, and never able to fail the request — same policy as
    # the forum path: a saved report must not be undone by a mail server, and
    # a moderator must not be alerted about a report that was not saved.
    try:
        _notify_direct_message_moderators(db, message, report)
    except Exception:
        logger.exception("Failed to notify moderators for report %s", report.id)

    return report


def _notify_direct_message_moderators(
    db: Session, message: DirectMessage, report: Report
) -> None:
    """
    §7.1 step 5 — tell the moderators responsible for the sender's cell.

    The alert carries the report id and nothing else. The forum path can put a
    hundred characters of the post in its email because that post is already
    visible to a whole cell; a private message is visible to two people, and
    mail is not the channel the reader consented to. She reads it in the
    moderator view, behind an authenticated, audited request — task 6's.

    No auto-hide and no urgency escalation here: §7.1's second-report rule
    hides *content*, and a private message has no visibility to withdraw —
    it is already visible to exactly the two people in the conversation.
    Thresholds are task 7's.
    """
    for email in _moderator_emails_for_author(db, message.sender):
        send_direct_message_report_alert(email, report.id)


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
        raise HTTPException(status_code=409, detail=_DUPLICATE_MESSAGE)


def _notify_moderators(db: Session, post: ForumPost, report: Report) -> None:
    """
    Thin dispatcher to the escalation notification policy for this report,
    based on the post's already-committed report_count (spec section 7.1).
    Adding a future policy means adding one handler + one dispatch line here
    — not touching the existing handlers.

    Runs strictly after file_report()'s db.commit() — if the commit had
    failed, a moderator must never be alerted about a report that was never
    actually saved. (Any DB state that must change together with the commit
    — e.g. post.status on the 2nd report — lives in file_report() itself,
    before the commit, not here.)
    """
    if post.report_count == 1:
        _handle_first_report_notification(db, post, report)
    elif post.report_count >= 2:
        _handle_second_plus_report_notification(db, post, report)


def _handle_first_report_notification(
    db: Session, post: ForumPost, report: Report
) -> None:
    """1st report → regular email to moderators."""
    for email in _moderator_emails_for_author(db, post.author):
        send_moderator_alert(email, report.id, post.content[:100])


def _handle_second_plus_report_notification(
    db: Session, post: ForumPost, report: Report
) -> None:
    """2nd+ report → urgent email, repeated on every report from here on."""
    for email in _moderator_emails_for_author(db, post.author):
        send_urgent_moderator_alert(email, report.id)


def _cell_match_filter(cells: list[dict[str, str]]) -> ColumnElement[bool]:
    """
    Build an OR-of-ANDs SQLAlchemy filter matching User.user_type/sector
    against a moderator's list of {"group", "sector"} cells (spec §4.3).
    Shared by get_pending_reports() and get_report_for_moderator() — both
    start from "these are my cells" and query outward for matching users.
    (_moderator_emails_for_author() runs the opposite direction — one known author,
    searching moderators' JSON cell lists — so it can't reuse this filter.)
    """
    return or_(
        *(
            and_(User.user_type == cell["group"], User.sector == cell["sector"])
            for cell in cells
        )
    )


def _moderator_emails_for_author(db: Session, author: User) -> list[str]:
    """
    Return contact addresses for the moderators responsible for this author's
    cell (group + sector), per moderator.moderator_cells.

    Takes the author rather than the content since ABF-112: §7.1 step 5 routes
    by the cell the reported content came from, and that cell is a property of
    whoever wrote it, not of what they wrote. A forum post passes its author;
    a private message passes its sender — whose cell is also the recipient's,
    because §5.3 does not let a conversation cross one.

    Removed moderators keep their row with role=MODERATOR — the appointment is
    revoked by cancelling the account (see user_service.remove_moderator) — so
    the status filter is what keeps alerts from following someone off the
    roster.
    """
    if author.user_type is None or author.sector is None:
        return []

    moderators = (
        db.query(User)
        .filter(User.role == UserRole.MODERATOR)
        .filter(User.account_status == AccountStatus.ACTIVE)
        .filter(User.moderator_cells.isnot(None))
        .all()
    )
    matching = [
        m
        for m in moderators
        if m.moderator_cells
        and any(
            cell["group"] == author.user_type and cell["sector"] == author.sector
            for cell in m.moderator_cells
        )
    ]
    return [m.alert_email or m.email for m in matching]


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


def get_pending_reports(db: Session, moderator: User) -> list[tuple[Report, ForumPost]]:
    """
    Return (report, reported post) pairs for the moderator's assigned cells.
    ADMIN sees every pending report, unscoped (spec §3.2 — admin has "הכל"
    for report handling; MODERATOR is scoped to "אחריותו" only).

    Only FORUM_POST reports exist today (file_report() rejects other target
    types), so this joins Report -> reported User -> ForumPost and matches
    the reported user's (user_type, sector) against moderator.moderator_cells.
    The ForumPost is returned alongside each Report (rather than just the
    Report) so callers — namely the moderator endpoints — never need their
    own follow-up query to render the reported content.
    """
    query = (
        db.query(Report, ForumPost)
        .join(User, Report.reported_user_id == User.id)
        .join(ForumPost, Report.target_id == ForumPost.id)
        .filter(Report.target_type == ReportTargetType.FORUM_POST)
        .filter(Report.decision == ReportDecision.PENDING)
    )

    if moderator.role != UserRole.ADMIN:
        cells = moderator.moderator_cells or []
        if not cells:
            return []
        query = query.filter(_cell_match_filter(cells))

    rows = query.order_by(ForumPost.report_count.desc()).all()
    return [(report, post) for report, post in rows]


def get_report_for_moderator(
    db: Session, report_id: str, moderator: User
) -> tuple[Report, ForumPost]:
    """
    Load a single report and its reported post, enforcing that the moderator
    is responsible for its cell (ADMIN bypasses this check — see require_role
    on the router).

    Raises 404 if the report or its post doesn't exist, 403 if the
    moderator's cells don't cover it.
    """
    report = db.query(Report).filter(Report.id == report_id).first()
    if report is None:
        raise HTTPException(status_code=404, detail=_REPORT_NOT_FOUND_MESSAGE)

    post = db.query(ForumPost).filter(ForumPost.id == report.target_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail=_REPORTED_CONTENT_NOT_FOUND_MESSAGE)

    if moderator.role == UserRole.MODERATOR:
        cells = moderator.moderator_cells or []
        # An empty cells list must mean "authorized for nothing" — an empty
        # or_() clause is a SQL no-op (matches every row), not "match none",
        # so it has to be special-cased here rather than left to the filter.
        covered = bool(cells) and (
            db.query(User)
            .filter(User.id == report.reported_user_id)
            .filter(_cell_match_filter(cells))
            .first()
            is not None
        )
        if not covered:
            raise HTTPException(status_code=403, detail=_REPORT_FORBIDDEN_MESSAGE)

    return report, post


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

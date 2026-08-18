"""
Report and moderation service.

Implements the automated protection rules from spec section 7.

Rules:
  1st report on a post  → email to responsible moderator
  2nd report (different user) → auto-hide post + urgent notification
  3+ valid reports on a USER in 7 days → auto-suspend 48h + notify admin
  5+ false reports from same USER in 30 days → restrict that user's reporting

TODO list for junior developer:
  [ ] implement _check_auto_suspension()          – Sprint 5
  [ ] implement _check_frequent_false_reporter()  – Sprint 5
"""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, case, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.core.constants import (
    AuditAction,
    PostStatus,
    ReportDecision,
    ReportTargetType,
    UserRole,
)
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDecideRequest
from app.schemas.user import SuspendUserRequest, UserModerationCard
from app.services import user_service
from app.services.audit_service import log_action
from app.services.email_service import (
    send_content_removed_notification,
    send_moderator_alert,
    send_urgent_moderator_alert,
)

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
    for email in _moderator_emails_for(db, post):
        send_moderator_alert(email, report.id, post.content[:100])


def _handle_second_plus_report_notification(
    db: Session, post: ForumPost, report: Report
) -> None:
    """2nd+ report → urgent email, repeated on every report from here on."""
    for email in _moderator_emails_for(db, post):
        send_urgent_moderator_alert(email, report.id)


def _cell_match_filter(cells: list[dict[str, str]]) -> ColumnElement[bool]:
    """
    Build an OR-of-ANDs SQLAlchemy filter matching User.user_type/sector
    against a moderator's list of {"group", "sector"} cells (spec §4.3).
    Shared by get_pending_reports() and get_report_for_moderator() — both
    start from "these are my cells" and query outward for matching users.
    (_moderator_emails_for() runs the opposite direction — one known author,
    searching moderators' JSON cell lists — so it can't reuse this filter.)
    """
    return or_(
        *(
            and_(User.user_type == cell["group"], User.sector == cell["sector"])
            for cell in cells
        )
    )


def _moderator_covers(moderator: User, user: User) -> bool:
    """
    True if `user` sits in one of the cells this moderator oversees.

    The in-Python counterpart to _cell_match_filter(): that one starts from
    the cells and queries for matching users, this one has both objects in
    hand already and only has to compare them.

    A user with no group or sector – every non-USER role, plus a registration
    the admin has not yet placed – belongs to no cell, so no moderator covers
    them. An empty cell list likewise covers nobody.
    """
    if user.user_type is None or user.sector is None:
        return False

    return any(
        cell["group"] == user.user_type and cell["sector"] == user.sector
        for cell in moderator.moderator_cells or []
    )


def _moderator_emails_for(db: Session, post: ForumPost) -> list[str]:
    """
    Return contact addresses for moderators responsible for this post's
    author's cell (group + sector), per moderator.moderator_cells.
    """
    author = post.author
    if author.user_type is None or author.sector is None:
        return []

    moderators = (
        db.query(User)
        .filter(User.role == UserRole.MODERATOR)
        .filter(User.moderator_cells.isnot(None))
        .all()
    )
    matching = [m for m in moderators if _moderator_covers(m, author)]
    return [m.alert_email or m.email for m in matching]


def decide_report(
    db: Session,
    report_id: str,
    data: ReportDecideRequest,
    moderator: User,
) -> Report:
    """
    Record a moderator's decision on a pending report and act on the content
    (SPEC §7.1, "החלטת מבקר").

    VALID   → the report stands: the post is deleted (status = DELETED) and
              its author gets a system notification.
    INVALID → the report does not stand: a post the 2-report rule auto-hid
              goes back to VISIBLE. A post that is already DELETED stays
              deleted — its author or another moderator removed it on other
              grounds, and dismissing this report is not a reason to
              republish it.

    Either way the report leaves the pending queue with the decision, the
    deciding moderator, the timestamp and the note recorded on it, and the
    whole thing is written to the audit log (SPEC §9.3).

    Raises 404 if the report or its content is gone, 403 if the report falls
    outside the moderator's cells, 409 if it was already decided.
    """
    # for_update: two moderators sharing a cell can have the same report open.
    # The lock makes the "still PENDING?" check below settle which of them
    # wins, instead of both writing a decision over each other.
    report = get_report_for_moderator(db, report_id, moderator, for_update=True)

    if report.decision != ReportDecision.PENDING:
        raise HTTPException(status_code=409, detail="הדיווח כבר טופל.")

    # Only FORUM_POST reports can exist – file_report() rejects the other
    # target types – so the reported content is always a post.
    # joinedload(author) avoids a lazy-load for the notification below, after
    # log_action()'s commit has expired the instance.
    post = (
        db.query(ForumPost)
        .options(joinedload(ForumPost.author))
        .filter(ForumPost.id == report.target_id)
        .with_for_update(of=ForumPost)
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="התוכן המדווח לא נמצא.")

    report.decision = data.decision
    report.moderator_id = moderator.id
    report.moderator_note = data.note
    # Naive UTC on purpose: decided_at is a plain DateTime column, and the
    # created_at beside it is filled by the DB's own naive now() – an aware
    # value here would make the two incomparable. Same convention as
    # user_service.escalate_overdue_registrations().
    report.decided_at = datetime.now(UTC).replace(tzinfo=None)

    content_action = _apply_content_decision(post, data.decision)
    # Read before the commit below expires `post`; the notification needs it.
    author_email = post.author.email

    # log_action() commits internally, which persists the report fields and
    # the post's new status along with the audit entry – one transaction, so
    # a decision can never land without its content change, or the reverse.
    log_action(
        db,
        actor=moderator,
        action=AuditAction.REPORT_DECIDED,
        entity_type="Report",
        entity_id=report.id,
        # moderator_note stays out of here: it is free text written about a
        # bereaved user, and the audit log records the action, not its
        # contents. The note itself lives on the report row.
        details={
            "decision": data.decision.value,
            "content_action": content_action,
            "target_type": report.target_type.value,
            "target_id": report.target_id,
            "reported_user_id": report.reported_user_id,
        },
    )
    db.refresh(report)

    # Sprint 5 hooks in right here: _check_auto_suspension() for the reported
    # user after VALID, _check_frequent_false_reporter() for the reporter
    # after INVALID (SPEC §7.2). Both are out of scope for this ticket.

    # Strictly after the commit, and never fatal: the decision is already
    # recorded, and a notification that fails must not turn it into a failed
    # request – same policy as file_report()'s moderator alerts.
    if data.decision == ReportDecision.VALID:
        try:
            send_content_removed_notification(author_email, report.id)
        except Exception:
            logger.exception("Failed to notify the author about report %s", report.id)

    return report


def _apply_content_decision(post: ForumPost, decision: ReportDecision) -> str:
    """
    Apply a decision to the reported post, and name what it did so the audit
    entry can say so. Mutates in memory only — decide_report() owns the commit.

    `decision` is VALID or INVALID: ReportDecideRequest rejects PENDING, which
    is the state a report starts in rather than a decision anyone submits.
    """
    if decision == ReportDecision.VALID:
        if post.status == PostStatus.DELETED:
            return "already_deleted"
        post.status = PostStatus.DELETED
        return "deleted"

    if post.status == PostStatus.HIDDEN:
        post.status = PostStatus.VISIBLE
        return "restored"
    return "unchanged"


def _scoped_report_query(db: Session, moderator: User) -> Query[Report] | None:
    """
    Base query for the reports a moderator is responsible for: FORUM_POST
    reports joined to the reported user and to the reported post, matched on
    the reported user's (user_type, sector) against moderator.moderator_cells.

    ADMIN is unscoped (spec §3.2 — admin has "הכל" for report handling;
    MODERATOR is scoped to "אחריותו" only).

    Returns None for a MODERATOR with no cells assigned, meaning "responsible
    for nothing". That cannot be expressed as a filter: an empty or_() is a
    SQL no-op that matches every row, i.e. the exact opposite.
    """
    query = (
        db.query(Report)
        .join(User, Report.reported_user_id == User.id)
        .join(ForumPost, Report.target_id == ForumPost.id)
        .filter(Report.target_type == ReportTargetType.FORUM_POST)
    )

    if moderator.role == UserRole.ADMIN:
        return query

    cells = moderator.moderator_cells or []
    if not cells:
        return None
    return query.filter(_cell_match_filter(cells))


def get_pending_reports(db: Session, moderator: User) -> list[Report]:
    """
    Return the reports still awaiting a decision in the moderator's cells,
    most-reported content first (SPEC §7.3).

    This is a work queue meant to be emptied, so it is not paginated —
    get_decided_reports() is, because history only grows.
    """
    query = _scoped_report_query(db, moderator)
    if query is None:
        return []

    return (
        query.filter(Report.decision == ReportDecision.PENDING)
        .order_by(ForumPost.report_count.desc())
        .all()
    )


def get_decided_reports(
    db: Session,
    moderator: User,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Report], int]:
    """
    Return one page of the decisions already made in the moderator's cells,
    newest first, together with the total across all pages (SPEC §7.3,
    "היסטוריית דיווחים").

    Scoped to the cells, not to who decided: a moderator sharing a cell with
    another needs to see what was already handled there, otherwise the same
    content gets re-litigated.
    """
    query = _scoped_report_query(db, moderator)
    if query is None:
        return [], 0

    query = query.filter(Report.decision != ReportDecision.PENDING)
    total = query.count()

    reports = (
        # Report.id as a tiebreaker: two decisions can share a timestamp, and
        # without a total order a row can repeat across pages or be skipped.
        query.order_by(Report.decided_at.desc(), Report.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return reports, total


def get_report_for_moderator(
    db: Session,
    report_id: str,
    moderator: User,
    *,
    for_update: bool = False,
) -> Report:
    """
    Load a single report, enforcing that the moderator is responsible for
    its cell (ADMIN bypasses this check — see require_role on the router).

    for_update takes a row-level lock, for callers that go on to write to the
    report. No-op on SQLite (dev), enforced on PostgreSQL (production) — same
    pattern as forum_service.delete_post().

    Raises 404 if the report doesn't exist, 403 if the moderator's cells
    don't cover it.
    """
    query = db.query(Report).filter(Report.id == report_id)
    if for_update:
        query = query.with_for_update()

    report = query.first()
    if report is None:
        raise HTTPException(status_code=404, detail="הדיווח לא נמצא.")

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
            raise HTTPException(status_code=403, detail="אין הרשאה לצפות בדיווח זה.")

    return report


# ---------------------------------------------------------------------------
# The user card – one user's moderation history (SPEC §7.3)
# ---------------------------------------------------------------------------


def _user_in_moderators_cells(db: Session, user_id: str, moderator: User) -> User:
    """
    Load a user, enforcing that the moderator oversees the cell they belong
    to. ADMIN is unscoped, the same way it is for reports (spec §3.2).

    Raises 404 if there is no such user, 403 if they fall outside the
    moderator's cells.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")

    if moderator.role == UserRole.MODERATOR and not _moderator_covers(moderator, user):
        raise HTTPException(status_code=403, detail="המשתמש אינו בתא שבאחריותך.")

    return user


def _card_for(db: Session, user: User) -> UserModerationCard:
    """
    Build the card for an already-authorized user: their identity, their
    suspension state, and the five report counts behind the moderator's
    judgement, counted in one query rather than five.

    The counts span the whole reports table, not just this moderator's
    cells: they describe the user's own conduct, and a partial count would
    understate exactly the case the card exists to reveal — someone who was
    reported repeatedly, in more than one cell.
    """
    reported = Report.reported_user_id == user.id
    filed = Report.reporter_id == user.id
    valid = Report.decision == ReportDecision.VALID
    invalid = Report.decision == ReportDecision.INVALID

    # count() ignores NULLs, and a case() without else_ yields NULL when the
    # condition does not hold – so each count() sees only its own rows.
    row = (
        db.query(
            func.count(case((reported, 1))),
            func.count(case((and_(reported, valid), 1))),
            func.count(case((and_(reported, invalid), 1))),
            func.count(case((filed, 1))),
            func.count(case((and_(filed, invalid), 1))),
        )
        .filter(or_(reported, filed))
        .one()
    )

    return UserModerationCard(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        user_type=user.user_type,
        sector=user.sector,
        account_status=user.account_status,
        reports_against_total=row[0],
        reports_against_valid=row[1],
        reports_against_invalid=row[2],
        reports_filed_total=row[3],
        false_reports_filed=row[4],
        is_suspended=user.is_suspended,
        suspended_until=user.suspended_until,
    )


def get_user_card(db: Session, user_id: str, moderator: User) -> UserModerationCard:
    """
    Return one user's moderation history for the moderator responsible for
    their cell (SPEC §7.3, "כרטיס משתמש").
    """
    return _card_for(db, _user_in_moderators_cells(db, user_id, moderator))


def suspend_user_for_moderator(
    db: Session,
    user_id: str,
    moderator: User,
    data: SuspendUserRequest,
) -> UserModerationCard:
    """
    Suspend a user by hand from their card (SPEC §7.3, "אפשרות השעיה ידנית").

    The cell check runs first, so a moderator reaching outside their cells is
    told 403 and learns nothing further about the account. Everything past
    that point – the "only an active regular user may be suspended" rules,
    the suspension itself, the audit entry and the email to the user – is
    user_service.suspend_user()'s, unchanged and shared with the admin route.

    Returns the card as it now stands, so the caller that opened it does not
    have to fetch it again to see the suspension it just applied.
    """
    user = _user_in_moderators_cells(db, user_id, moderator)
    suspended = user_service.suspend_user(
        db, user.id, moderator, data.hours, data.reason
    )
    return _card_for(db, suspended)


def _check_auto_suspension(db: Session, reported_user: User) -> None:
    """
    Check if the reported user should be automatically suspended.

    Rule: 3+ valid reports in 7 days → suspend 48 hours + notify admin

    Sprint 5 — decide_report() marks where this is called from once it exists.

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

    Sprint 5 — decide_report() marks where this is called from once it exists.

    TODO:
      1. Count reports filed BY reporter with decision=INVALID in last 30 days
      2. If >= 5: add a report limit flag on the user
    """
    # TODO: implement this function
    pass

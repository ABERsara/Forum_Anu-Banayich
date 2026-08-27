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
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, and_, or_
from sqlalchemy.orm import Query, Session

from app.core.constants import (
    AccountStatus,
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


def _moderator_emails_for(db: Session, post: ForumPost) -> list[str]:
    """
    Return contact addresses for moderators responsible for this post's
    author's cell (group + sector), per moderator.moderator_cells.

    Removed moderators keep their row with role=MODERATOR — the appointment is
    revoked by cancelling the account (see user_service.remove_moderator) — so
    the status filter is what keeps alerts from following someone off the
    roster.
    """
    author = post.author
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
    # wins, instead of both writing a decision over each other. It covers the
    # reported post too — the decision rewrites its status.
    report, post = get_report_for_moderator(db, report_id, moderator, for_update=True)

    if report.decision != ReportDecision.PENDING:
        raise HTTPException(status_code=409, detail="הדיווח כבר טופל.")

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


def _scoped_report_query(db: Session, moderator: User) -> Query[Any] | None:
    """
    Base query for the reports a moderator is responsible for: FORUM_POST
    reports joined to the reported user and to the reported post, matched on
    the reported user's (user_type, sector) against moderator.moderator_cells.

    The ForumPost is selected alongside each Report (rather than just the
    Report) so callers — namely the moderator endpoints — never need their
    own follow-up query to render the reported content.

    ADMIN is unscoped (spec §3.2 — admin has "הכל" for report handling;
    MODERATOR is scoped to "אחריותו" only).

    Returns None for a MODERATOR with no cells assigned, meaning "responsible
    for nothing". That cannot be expressed as a filter: an empty or_() is a
    SQL no-op that matches every row, i.e. the exact opposite.

    Query[Any] rather than the row type: SQLAlchemy gives a two-entity query
    its own class, and how that class is parameterised changed between 2.0
    and 2.1 — pyproject asks only for ">=2.0", so naming it here would make
    mypy pass on one and fail on the other. The two callers annotate the rows
    they get back instead, which is where the pairs are actually read.
    """
    query = (
        db.query(Report, ForumPost)
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


def get_pending_reports(db: Session, moderator: User) -> list[tuple[Report, ForumPost]]:
    """
    Return the reports still awaiting a decision in the moderator's cells,
    most-reported content first (SPEC §7.3), each paired with the post it is
    about so the endpoint needs no follow-up query.

    This is a work queue meant to be emptied, so it is not paginated —
    get_decided_reports() is, because history only grows.
    """
    query = _scoped_report_query(db, moderator)
    if query is None:
        return []

    rows: list[tuple[Report, ForumPost]] = (
        query.filter(Report.decision == ReportDecision.PENDING)
        .order_by(ForumPost.report_count.desc())
        .all()
    )
    return [(report, post) for report, post in rows]


def get_decided_reports(
    db: Session,
    moderator: User,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[tuple[Report, ForumPost]], int]:
    """
    Return one page of the decisions already made in the moderator's cells,
    newest first, each paired with the post it is about, together with the
    total across all pages (SPEC §7.3, "היסטוריית דיווחים").

    Scoped to the cells, not to who decided: a moderator sharing a cell with
    another needs to see what was already handled there, otherwise the same
    content gets re-litigated.
    """
    query = _scoped_report_query(db, moderator)
    if query is None:
        return [], 0

    query = query.filter(Report.decision != ReportDecision.PENDING)
    total = query.count()

    rows: list[tuple[Report, ForumPost]] = (
        # Report.id as a tiebreaker: two decisions can share a timestamp, and
        # without a total order a row can repeat across pages or be skipped.
        query.order_by(Report.decided_at.desc(), Report.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return [(report, post) for report, post in rows], total


def get_report_for_moderator(
    db: Session,
    report_id: str,
    moderator: User,
    *,
    for_update: bool = False,
) -> tuple[Report, ForumPost]:
    """
    Load a single report and its reported post, enforcing that the moderator
    is responsible for its cell (ADMIN bypasses this check — see require_role
    on the router).

    for_update takes a row-level lock on both rows, for callers that go on to
    write to them — decide_report() rewrites the report and the post's status
    together. No-op on SQLite (dev), enforced on PostgreSQL (production) —
    same pattern as forum_service.delete_post().

    Raises 404 if the report or its post doesn't exist, 403 if the
    moderator's cells don't cover it.
    """
    query = db.query(Report).filter(Report.id == report_id)
    if for_update:
        query = query.with_for_update()

    report = query.first()
    if report is None:
        raise HTTPException(status_code=404, detail="הדיווח לא נמצא.")

    post_query = db.query(ForumPost).filter(ForumPost.id == report.target_id)
    if for_update:
        post_query = post_query.with_for_update()

    post = post_query.first()
    if post is None:
        raise HTTPException(status_code=404, detail="התוכן המדווח לא נמצא.")

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

    return report, post


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

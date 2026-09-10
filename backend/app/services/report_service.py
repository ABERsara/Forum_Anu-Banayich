"""
Report and moderation service.

Implements the automated protection rules from spec section 7.

Rules:
  1st report on a post  → email to responsible moderator
  2nd report (different user) → auto-hide post + urgent notification
  3+ upheld reports on a USER in 30 days → she cannot send private messages
      for 48h + notify her cell's moderator and the admin (§7.2, ABF-116)
  5+ dismissed reports from the same USER in 30 days → her reporting drops
      to 3 a day + notify her cell's moderator (§7.2, ABF-116)
  2+ upheld incidents in 7 days → auto-suspend 48h + notify admin

The threshold rules themselves live in `restriction_service`; this module is
where a decision is recorded and where the people who need to hear about one
are worked out.

TODO list for junior developer:
  [ ] implement _check_auto_suspension()          – §7.2's third row, still open
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Query, Session

from app.core.constants import (
    AccountStatus,
    AuditAction,
    PostStatus,
    ReportDecision,
    ReportTargetType,
    RestrictionType,
    UserRole,
)
from app.core.i18n import translate
from app.models.forum import DirectMessage, ForumPost
from app.models.report import Report
from app.models.restriction import UserRestriction
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDecideRequest
from app.services import forum_service, restriction_service
from app.services.audit_service import build_entry, log_action
from app.services.email_service import (
    send_content_removed_notification,
    send_direct_message_report_alert,
    send_moderator_alert,
    send_reporting_restriction_alert,
    send_sending_restriction_alert,
    send_urgent_moderator_alert,
)
from app.services.user_service import cell_match_filter

logger = logging.getLogger(__name__)


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

    The daily allowance is checked first, before either path and before
    anything is looked up. §7.2's limit applies to reporting itself, not to
    reporting a particular thing, and checking it here means a member who is
    over it gets the same answer whatever id she names — a check made after
    the lookup would answer 404 for an id that does not exist and 429 for one
    that does, which is a probe for other people's content.
    """
    restriction_service.assert_may_file_report(db, reporter)

    if data.target_type == ReportTargetType.DIRECT_MESSAGE:
        return _file_direct_message_report(db, data, reporter)
    if data.target_type != ReportTargetType.FORUM_POST:
        raise HTTPException(
            status_code=400, detail=translate("reports.target_type_unsupported")
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
        raise HTTPException(status_code=404, detail=translate("forum.post_not_found"))

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
        raise HTTPException(
            status_code=409, detail=translate("reports.already_reported")
        )


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
        raise HTTPException(
            status_code=409, detail=translate("reports.already_handled")
        )

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

    # §7.2's thresholds, evaluated on the decision that was just committed
    # (ABF-116). Deliberately *not* wrapped in a try/except, unlike every
    # notification in this module: a restriction is state, not mail. If it
    # cannot be written the caller has to hear about it — a protection
    # measure that silently fails to apply is the failure this whole
    # mechanism exists to prevent, and the alternative is a 500 on a
    # decision that is already recorded, which a retry answers honestly
    # with 409 "already handled".
    restriction = restriction_service.evaluate_after_decision(db, report, moderator)
    db.refresh(report)

    # Strictly after the commit, and never fatal: the decision is already
    # recorded, and a notification that fails must not turn it into a failed
    # request – same policy as file_report()'s moderator alerts.
    if data.decision == ReportDecision.VALID:
        try:
            send_content_removed_notification(author_email, report.id)
        except Exception:
            logger.exception("Failed to notify the author about report %s", report.id)

    if restriction is not None:
        try:
            _notify_restriction(db, restriction)
        except Exception:
            logger.exception(
                "Failed to send the restriction alerts for report %s", report.id
            )

    return report


def _notify_restriction(db: Session, restriction: UserRestriction) -> None:
    """
    §7.2's "התראה" column — tell the people who can act on a restriction that
    one was applied automatically.

    Who hears depends on the direction, because §7.2 says so and because the
    two mean different things. A member restricted from sending has been
    found against repeatedly: the moderator responsible for her cell needs to
    know, and so does the admin, who is the only one who can suspend
    ("עיון בהשעיה" — the admin considers it; nothing here decides it). A
    member whose reports keep being dismissed is a moderator's problem alone
    — it is the moderator's queue she is filling — and escalating that to an
    admin would turn an over-eager reporter into an administrative case.

    The alerts carry the restricted member's id and when the measure ends.
    Never the reports themselves, never their content: one of them can be a
    private message, and mail is not a channel anyone consented to it
    reaching (same rule as send_direct_message_report_alert).

    Lives here rather than in restriction_service because "which moderators
    cover this cell" is this module's knowledge — and keeping it here is what
    lets restriction_service stay importable from both services without a
    cycle.
    """
    member = restriction.user
    moderator_emails = _moderator_emails_for_author(db, member)

    if restriction.restriction_type == RestrictionType.MESSAGING:
        for email in moderator_emails + _admin_alert_emails(db):
            send_sending_restriction_alert(email, member.id, restriction.expires_at)
        return

    for email in moderator_emails:
        send_reporting_restriction_alert(email, member.id, restriction.expires_at)


def _admin_alert_emails(db: Session) -> list[str]:
    """
    Contact addresses for the admins who take §7.2's escalations.

    `alert_email` rather than the login address, and only where one is set —
    the same roster user_service.escalate_overdue_registrations() escalates
    to, so a deployment configures who is on call once.
    """
    admins = (
        db.query(User)
        .filter(User.role == UserRole.ADMIN)
        .filter(User.account_status == AccountStatus.ACTIVE)
        .filter(User.alert_email.isnot(None))
        .all()
    )
    return [admin.alert_email for admin in admins if admin.alert_email]


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
    return query.filter(cell_match_filter(cells))


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
        raise HTTPException(status_code=404, detail=translate("reports.not_found"))

    post_query = db.query(ForumPost).filter(ForumPost.id == report.target_id)
    if for_update:
        post_query = post_query.with_for_update()

    post = post_query.first()
    if post is None:
        raise HTTPException(
            status_code=404, detail=translate("reports.target_not_found")
        )

    if moderator.role == UserRole.MODERATOR:
        cells = moderator.moderator_cells or []
        # An empty cells list must mean "authorized for nothing" — an empty
        # or_() clause is a SQL no-op (matches every row), not "match none",
        # so it has to be special-cased here rather than left to the filter.
        covered = bool(cells) and (
            db.query(User)
            .filter(User.id == report.reported_user_id)
            .filter(cell_match_filter(cells))
            .first()
            is not None
        )
        if not covered:
            raise HTTPException(
                status_code=403, detail=translate("reports.view_forbidden")
            )

    return report, post


def _check_auto_suspension(db: Session, reported_user: User) -> None:
    """
    Check if the reported user should be automatically suspended.

    Rule: §7.2's third row — 2+ upheld incidents in 7 days → temporary
    automatic suspension (48h) + notify admin.

    Still open, and deliberately not what ABF-116 built. That ticket
    implements §7.2's *first two* rows, both of which restrict one action and
    leave the account alone; this one takes the account away, which is a
    heavier measure on a different window and count. decide_report() calls
    restriction_service.evaluate_after_decision() where this would also hook
    in.

    TODO:
      1. Count reports with decision=VALID against reported_user in last 7 days
      2. If >= 2 and not already suspended: call user_service.suspend_user()
    """
    # TODO: implement this function
    pass

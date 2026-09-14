"""
Automatic restrictions — spec §5.3's מה"ק and §7.2's two thresholds (ABF-116).

Two directions, one shape. A moderator's decision on a report is the only
thing that moves either of them:

    VALID   → one more upheld report against the person who was reported.
              DM_BLOCK_AFTER_REPORTS of them inside DM_BLOCK_DAYS_WINDOW and
              she cannot send private messages for DM_BLOCK_HOURS. She can
              still read every conversation she is in.
    INVALID → one more dismissed report from the person who filed it.
              FALSE_REPORT_LIMIT of them inside FALSE_REPORT_DAYS_WINDOW and
              her reporting drops to RESTRICTED_REPORTS_PER_DAY a day for
              FALSE_REPORT_RESTRICTION_DAYS. Reporting is not taken away.

Neither is a suspension. §7.2 asks for "עיון בהשעיה" — a human *considering*
one — and this module never makes that call: it restricts one action, for a
stated time, and tells the moderator and the admin so they can.

What is deliberately not here
-----------------------------
* No notification. Deciding who hears about a restriction is the report
  flow's job — it already knows which moderators cover the cell a report
  came from — and keeping the mail out of here is what lets report_service
  import this module without a cycle (this one imports no service that
  imports it back).
* No lifting. A restriction ends by expiring; nothing writes to a row after
  it is created. An early release is a moderator action, and there is no
  ticket for one yet.
* No counters on `users`. The counts come from `reports` on every
  evaluation, so there is no second copy of the truth to drift from the
  first — see `_decided_report_count`.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import InstrumentedAttribute, Query, Session

from app.core.config import settings
from app.core.constants import (
    AuditAction,
    ReportDecision,
    RestrictionType,
    UserRole,
)
from app.core.i18n import translate
from app.models.report import Report
from app.models.restriction import UserRestriction
from app.models.user import User
from app.services.audit_service import build_entry
from app.services.user_service import cell_match_filter

#: The refusal a restricted sender gets, as a translation key rather than a
#: sentence — the shape forum_service.py raises its other DM errors in, which
#: the Angular client resolves itself (core/utils/error-key.util.ts). Kept in
#: that shape on purpose: the chat screen recognises these three by name, and
#: a fourth that arrived as finished prose would drop to the generic fallback.
DM_RESTRICTED_MESSAGE = "errors.dm_restricted"


def _now() -> datetime:
    """
    Naive UTC, the convention every timestamp in this schema follows.

    `created_at` is filled by the database's own naive `now()`, so an aware
    value would be incomparable with the row beside it — the same reasoning
    report_service.decide_report() spells out for `decided_at`.
    """
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Reading the current state
# ---------------------------------------------------------------------------


def active_restriction(
    db: Session, user_id: str, restriction_type: RestrictionType
) -> UserRestriction | None:
    """
    The restriction of this kind that is in force right now, or None.

    Expiry is a comparison, not a job: a lapsed row simply stops matching, so
    a member gets her messaging back at `expires_at` whether or not any
    scheduled task ran. Newest first, so overlapping rows — possible if the
    thresholds are re-tuned downwards between two decisions — resolve to the
    one that ends last being found first.
    """
    return (
        db.query(UserRestriction)
        .filter(
            UserRestriction.user_id == user_id,
            UserRestriction.restriction_type == restriction_type,
            UserRestriction.expires_at > _now(),
        )
        .order_by(UserRestriction.expires_at.desc())
        .first()
    )


def _decided_report_count(
    db: Session,
    *,
    subject: InstrumentedAttribute[str] | InstrumentedAttribute[str | None],
    user_id: str,
    decision: ReportDecision,
    window_days: int,
) -> int:
    """
    How many reports about (or from) `user_id` were decided `decision` inside
    the last `window_days`.

    `subject` is the column that names the person — `Report.reported_user_id`
    for direction A, `Report.reporter_id` for direction B. Passed in rather
    than branched on inside, so the two thresholds cannot drift into counting
    differently; typed as either nullability because the reporter column is
    nullable since ABF-112 and the reported-user one is not.

    Counted from `reports` on every evaluation rather than kept as a column
    on `users`. A stored counter would have to be corrected every time a
    report is deleted, anonymized (§9.4) or re-decided, and a counter that is
    wrong in the direction of "more" restricts somebody who did not earn it.

    `decided_at` rather than `created_at`: the threshold is about findings,
    not accusations, and a report sits pending for however long the moderator
    takes. Filtering on it also drops PENDING rows for free — theirs is NULL,
    and NULL is not >= anything.
    """
    threshold = _now() - timedelta(days=window_days)
    return (
        db.query(Report)
        .filter(
            subject == user_id,
            Report.decision == decision,
            Report.decided_at >= threshold,
        )
        .count()
    )


# ---------------------------------------------------------------------------
# Applying a restriction
# ---------------------------------------------------------------------------


def apply_restriction(
    db: Session,
    *,
    user: User,
    actor: User,
    restriction_type: RestrictionType,
    duration: timedelta,
    report_count: int,
    window_days: int,
    triggered_by_report_id: str | None,
) -> UserRestriction:
    """
    Write the restriction and its audit entry as one transaction.

    Together, not one after the other: §9.3 wants a record of every automatic
    measure taken against a member, and a restriction that is in force with
    nothing in the log saying why is the state that record exists to prevent.
    Built with build_entry() rather than log_action() for exactly that reason
    — log_action() commits on its own.

    `actor` is the moderator whose decision crossed the threshold. The rule
    fired by itself, but it fired *on her decision*, and an audit trail whose
    actor is "the system" is one nobody can be asked about; `automatic` in
    the details is what says she did not choose the measure.

    The details carry ids, counts and a timestamp. They never carry the
    reported content — a report can be about a private message, and §5.3 lets
    exactly one moderator read one of those, through the moderator view.
    """
    now = _now()
    restriction = UserRestriction(
        user_id=user.id,
        restriction_type=restriction_type,
        expires_at=now + duration,
        report_count=report_count,
        window_days=window_days,
        triggered_by_report_id=triggered_by_report_id,
    )
    db.add(restriction)
    # restriction.id is a client-side uuid4 default — only populated once
    # flushed, and the audit entry below has to name it.
    db.flush()

    db.add(
        build_entry(
            actor=actor,
            action=AuditAction.USER_RESTRICTED,
            entity_type="User",
            entity_id=user.id,
            details={
                "restriction_id": restriction.id,
                "restriction_type": restriction_type.value,
                "expires_at": restriction.expires_at.isoformat(),
                "report_count": report_count,
                "window_days": window_days,
                "triggered_by_report_id": triggered_by_report_id,
                "automatic": True,
            },
        )
    )
    db.commit()
    db.refresh(restriction)
    return restriction


def evaluate_after_decision(
    db: Session, report: Report, moderator: User
) -> UserRestriction | None:
    """
    Apply §7.2's thresholds to the decision that was just recorded, and
    return the restriction it created — or None, which is the ordinary case.

    Called after decide_report() has committed, so what is counted here
    includes the decision that prompted it. A single report can therefore
    never restrict anyone on its own: the count it contributes to has to
    reach a threshold that is greater than one, and both configured
    thresholds are (3 and 5).

    PENDING never reaches here — ReportDecideRequest rejects it — and
    CLOSED_ACCOUNT_DELETED is the system closing a report because the account
    it was about is gone (§9.4, ABF-117), not a finding against anybody, so
    it deliberately falls through both branches.
    """
    if report.decision == ReportDecision.VALID:
        return _restrict_repeatedly_upheld_sender(db, report, moderator)
    if report.decision == ReportDecision.INVALID:
        return _restrict_frequent_false_reporter(db, report, moderator)
    return None


def _restrict_repeatedly_upheld_sender(
    db: Session, report: Report, moderator: User
) -> UserRestriction | None:
    """
    Direction A (§7.2 "מדווח-עליו תכוף ומוצדק", §5.3 מה"ק): a member whose
    content keeps being reported and keeps being found against loses the
    ability to *send* private messages for a while.

    The count is of upheld reports against her across the whole platform, not
    per conversation and not per content type. Per conversation is the point
    of the ticket — someone who sends one abusive message each to ten
    different people has done more harm than someone who sent ten to one, and
    a per-conversation count would see the first as ten separate innocents.
    Beyond that, §7.2 states the rule without qualifying it by where the
    content was, and a member found against three times in a month is the
    same member whichever surface she used.

    Nothing happens while a restriction of this kind is already running: a
    fourth decision inside a live 48 hours neither extends it nor writes a
    second row. The restriction answers a pattern, and the pattern is already
    being answered.
    """
    if active_restriction(db, report.reported_user_id, RestrictionType.MESSAGING):
        return None

    window_days = settings.DM_BLOCK_DAYS_WINDOW
    count = _decided_report_count(
        db,
        subject=Report.reported_user_id,
        user_id=report.reported_user_id,
        decision=ReportDecision.VALID,
        window_days=window_days,
    )
    if count < settings.DM_BLOCK_AFTER_REPORTS:
        return None

    reported_user = db.query(User).filter(User.id == report.reported_user_id).first()
    if reported_user is None:
        # The account closed between the decision and this evaluation (§9.4
        # deletes the member and keeps the report). Nothing to restrict.
        return None

    return apply_restriction(
        db,
        user=reported_user,
        actor=moderator,
        restriction_type=RestrictionType.MESSAGING,
        duration=timedelta(hours=settings.DM_BLOCK_HOURS),
        report_count=count,
        window_days=window_days,
        triggered_by_report_id=report.id,
    )


def _restrict_frequent_false_reporter(
    db: Session, report: Report, moderator: User
) -> UserRestriction | None:
    """
    Direction B (§7.2 "מדווח-שגוי תכוף"): a member whose reports keep being
    dismissed drops to a daily allowance.

    An allowance rather than a ban, because the two failure modes are not
    symmetrical. Someone who over-reports is a nuisance; someone who cannot
    report at all is a member of a bereavement platform with no way to say
    that something happened to her. Three a day leaves that possible.

    `reporter_id` is nullable since ABF-112 — a closed account's reports are
    kept and anonymized — so a report with no reporter restricts nobody.
    """
    if report.reporter_id is None:
        return None
    if active_restriction(db, report.reporter_id, RestrictionType.REPORTING):
        return None

    window_days = settings.FALSE_REPORT_DAYS_WINDOW
    count = _decided_report_count(
        db,
        subject=Report.reporter_id,
        user_id=report.reporter_id,
        decision=ReportDecision.INVALID,
        window_days=window_days,
    )
    if count < settings.FALSE_REPORT_LIMIT:
        return None

    reporter = db.query(User).filter(User.id == report.reporter_id).first()
    if reporter is None:
        return None

    return apply_restriction(
        db,
        user=reporter,
        actor=moderator,
        restriction_type=RestrictionType.REPORTING,
        duration=timedelta(days=settings.FALSE_REPORT_RESTRICTION_DAYS),
        report_count=count,
        window_days=window_days,
        triggered_by_report_id=report.id,
    )


# ---------------------------------------------------------------------------
# Enforcing a restriction
# ---------------------------------------------------------------------------


def assert_may_send_direct_message(db: Session, sender: User) -> None:
    """
    Refuse the send if this sender is under a messaging restriction.

    Called at the very top of send_direct_message(), *before* the recipient
    is looked up, and that order is load-bearing. A restricted member who
    could tell "restricted" from "no such recipient" apart would have a probe
    for who exists in her cell; checking her own state first means every send
    she attempts answers the same way, whoever she aimed it at.

    Only sending. get_conversation_messages(), get_inbox() and
    mark_conversation_read() are untouched — the acceptance criterion is that
    reading stays open, and it stays open because nothing on the read path
    calls this.

    No audit entry, unlike the DIRECT_MESSAGE_ACCESS_DENIED that
    send_direct_message() writes when the *recipient* check fails. That one
    records an attempt to reach content the sender has no right to; this one
    records nothing new — the measure itself is already on the record
    (AuditAction.USER_RESTRICTED, written once when it was applied), and a
    row per retry would fill §9.3's seven-year log with one member pressing
    send.
    """
    restriction = active_restriction(db, sender.id, RestrictionType.MESSAGING)
    if restriction is None:
        return

    # 403 rather than 429: this is not a rate limit that a slower sender
    # would pass, it is a withdrawn permission with an end date.
    raise HTTPException(status_code=403, detail=DM_RESTRICTED_MESSAGE)


def assert_may_file_report(db: Session, reporter: User) -> None:
    """
    Refuse a report that would exceed the daily allowance.

    Called at the top of file_report(), before the reported content is looked
    up — same reasoning as the send path: a member over her allowance must
    not be able to tell an id that exists from one that does not by which
    refusal comes back.

    The day is a rolling 24 hours rather than a calendar one. "3 דיווחים
    ליום" reads either way, and a calendar day needs a timezone the platform
    does not store per member — with the server on UTC, an Israeli member's
    allowance would reset at 2 or 3 in the morning, and a rolling window
    cannot be doubled by filing either side of midnight.

    Counted on `created_at`, not `decided_at`: this one is about how many
    reports she filed, and a report filed today is filed whether or not
    anybody has looked at it yet.
    """
    restriction = active_restriction(db, reporter.id, RestrictionType.REPORTING)
    if restriction is None:
        return

    since = _now() - timedelta(days=1)
    filed_today = (
        db.query(Report)
        .filter(Report.reporter_id == reporter.id, Report.created_at >= since)
        .count()
    )
    if filed_today < settings.RESTRICTED_REPORTS_PER_DAY:
        return

    raise HTTPException(
        status_code=429, detail=translate("reports.daily_limit_reached")
    )


# ---------------------------------------------------------------------------
# The moderator's view
# ---------------------------------------------------------------------------


def list_active_restrictions(
    db: Session, moderator: User
) -> list[tuple[UserRestriction, User]]:
    """
    The restrictions in force right now in this moderator's cells, newest
    first, each paired with the member it applies to (§7.3 — the dashboard
    shows who is under one without a second request per row).

    Active only. A dashboard is a picture of the situation now, and a list
    that also carried every lapsed restriction would bury the ones that are
    still doing something. The rows are kept, so a history view is a query
    away when a ticket asks for one.

    ADMIN is unscoped, MODERATOR is scoped to her cells — the same split
    §3.2 draws for handling reports ("הכל" against "אחריותו"), and the same
    special case for a moderator with no cells: an empty or_() matches every
    row, which is the opposite of "responsible for nothing".
    """
    query: Query[Any] = (
        db.query(UserRestriction, User)
        .join(User, UserRestriction.user_id == User.id)
        .filter(UserRestriction.expires_at > _now())
    )

    if moderator.role != UserRole.ADMIN:
        cells = moderator.moderator_cells or []
        if not cells:
            return []
        query = query.filter(cell_match_filter(cells))

    rows: list[tuple[UserRestriction, User]] = query.order_by(
        # id as a tiebreaker: two restrictions can share a created_at, and
        # without a total order the list is not stable between requests.
        UserRestriction.created_at.desc(),
        UserRestriction.id,
    ).all()
    return rows

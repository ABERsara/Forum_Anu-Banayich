"""
ABF-154's two automatic violation rules (spec §7.2, third row and second row).

What this file pins, in the order the ticket's acceptance criteria list them:

  * two upheld reports inside the window do nothing, three suspend — and the
    suspension lands on the third *decision*, not on the third report
    (TestAutoSuspensionThreshold);
  * a member who is already suspended is not suspended again, and deciding a
    further report against her is not an error (TestSuspensionIsNotDoubled);
  * four dismissed reports do nothing, five withdraw the reporting
    (TestFalseReporterFlag);
  * a member carrying the flag is refused with 403 and the right message
    (TestRestrictedReporterIsRefused);
  * after an admin lifts the flag, only dismissals decided after the lift
    count toward it again (ABF-XXX: TestALiftStartsTheCountAgain), and a
    member never lifted is counted as before
    (TestAMemberNeverLiftedIsCountedAsBefore);
  * every window is exercised with the clock under the test's control
    (TestWindowsAreMeasuredFromTheClock, and the `decided_at` offsets
    throughout).

Plus what the two rules must *not* do: cross into each other's direction
(TestTheDirectionsDoNotCross), reach an account that is not a member's
(TestOnlyMembersAreSuspended), write the decision's content into the audit log
or the notification (TestAutoSuspensionAuditTrail, TestFalseReporterAuditTrail),
or read a threshold from anywhere but `settings`
(TestThresholdsAreConfiguration).

And ABF-164's emails, one per rule, sent once the measure is committed: the
suspension goes to the admin team (TestAutoSuspensionEmailsTheAdminTeam), the
withdrawn reporting to the moderators of the member's cell
(TestRevokedReportingEmailsTheCellModerators), and an email that cannot be
sent never undoes either measure (TestAFailedEmailDoesNotUndoTheMeasure).

Time is controlled the way tests/test_restrictions.py controls it — history is
written straight to `reports` with an explicit `decided_at`, and the decision
that crosses a threshold always goes through the real `decide_report()` flow.
`shifted_clock` adds the other direction: it moves what the service believes
"now" is, so a window can be walked off the end of rather than only written
behind.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header

import pytest

from app.core.config import settings
from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    PostStatus,
    ProfessionalDomain,
    ReportDecision,
    ReportReason,
    ReportTargetType,
    RestrictionType,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.core.messages import ENGLISH, HEBREW, MESSAGES
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.restriction import UserRestriction
from app.models.user import User
from app.schemas.report import ReportDecideRequest
from app.services import (
    email_service,
    report_service,
    restriction_service,
    user_service,
)

FORUM_BASE = "/api/v1/forum"

CELL = {"group": UserType.WIDOW.value, "sector": Sector.HASIDIC.value}

NOTE = "החלטה מנומקת לצורך הבדיקה"


def _now() -> datetime:
    """Naive UTC — the convention every timestamp in this schema follows."""
    return datetime.now(UTC).replace(tzinfo=None)


def _days_ago(days: int) -> datetime:
    return _now() - timedelta(days=days)


def _make_user(
    db_session,
    email: str,
    *,
    role: UserRole = UserRole.USER,
    account_status: AccountStatus = AccountStatus.ACTIVE,
    moderator_cells: list[dict[str, str]] | None = None,
    is_report_restricted: bool = False,
    alert_email: str | None = None,
) -> User:
    is_member = role == UserRole.USER
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=UserType.WIDOW if is_member else None,
        sector=Sector.HASIDIC if is_member else None,
        account_status=account_status,
        moderator_cells=moderator_cells,
        is_report_restricted=is_report_restricted,
        alert_email=alert_email,
        professional_domain=(
            ProfessionalDomain.LAWYER if role == UserRole.PROFESSIONAL else None
        ),
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_post(db_session, author: User) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="כותרת",
        content="תוכן ההודעה שדווחה",
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
        status=PostStatus.VISIBLE,
    )
    db_session.add(post)
    db_session.commit()
    return post


def _decided_report(
    db_session,
    *,
    reporter: User | None,
    reported_user: User,
    decision: ReportDecision,
    decided_at: datetime | None = None,
    target_id: str = "target",
) -> Report:
    """
    A report that already carries a decision.

    Written straight to the table rather than driven through decide_report():
    these are the *history* a threshold is measured against, and history has to
    be placeable at an arbitrary point in the past. The decision that crosses a
    threshold always goes through the real flow.
    """
    report = Report(
        reporter_id=None if reporter is None else reporter.id,
        target_type=ReportTargetType.FORUM_POST,
        target_id=target_id,
        reported_user_id=reported_user.id,
        reason=ReportReason.HARASSMENT,
        decision=decision,
        decided_at=_now() if decided_at is None else decided_at,
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


def _pending_report(db_session, *, reporter: User, post: ForumPost) -> Report:
    """A report the moderator has not decided yet, filed on a real post."""
    report = Report(
        reporter_id=reporter.id,
        target_type=ReportTargetType.FORUM_POST,
        target_id=post.id,
        reported_user_id=post.author_id,
        reason=ReportReason.HARASSMENT,
    )
    db_session.add(report)
    post.report_count += 1
    db_session.commit()
    db_session.refresh(report)
    return report


def _decide(db_session, report: Report, moderator: User, decision: ReportDecision):
    return report_service.decide_report(
        db_session,
        report.id,
        ReportDecideRequest(decision=decision, note=NOTE),
        moderator,
    )


def _decide_a_fresh_report(
    db_session,
    *,
    reporter: User,
    reported_user: User,
    moderator: User,
    decision: ReportDecision,
) -> Report:
    """File one more report, on a post of its own, and decide it for real."""
    report = _pending_report(
        db_session, reporter=reporter, post=_make_post(db_session, reported_user)
    )
    return _decide(db_session, report, moderator, decision)


def _fill_history(
    db_session,
    *,
    reporter: User | None,
    reported_user: User,
    decision: ReportDecision,
    count: int,
    decided_at: datetime | None = None,
    prefix: str = "old",
) -> None:
    for index in range(count):
        _decided_report(
            db_session,
            reporter=reporter,
            reported_user=reported_user,
            decision=decision,
            decided_at=decided_at,
            target_id=f"{prefix}-{index}",
        )


def _audit_entries(
    db_session, action: AuditAction, *, measure: str | None = None
) -> list[AuditLog]:
    entries = db_session.query(AuditLog).filter(AuditLog.action == action).all()
    if measure is None:
        return entries
    return [e for e in entries if (e.details or {}).get("measure") == measure]


def _flag_audit_entries(db_session) -> list[AuditLog]:
    """
    Only ABF-154's flag, not the `user_restrictions` row ABF-116 writes.

    Both use AuditAction.USER_RESTRICTED — constants.py asks for one member and
    a `details` payload naming the measure, rather than an enum value per
    direction — so a decision that crosses §7.2's second row leaves two
    entries, and these tests are about one of them.
    """
    return _audit_entries(
        db_session, AuditAction.USER_RESTRICTED, measure="report_restricted"
    )


@pytest.fixture
def as_user():
    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def shifted_clock(monkeypatch):
    """
    Move what the rules believe "now" is, by a timedelta the test names.

    Both windows are measured as `_now() - timedelta(days=window)` inside
    restriction_service.decided_report_count(), so patching that one function
    moves every threshold's window together and leaves the stored rows exactly
    where the test put them. That is the direction `decided_at` cannot cover:
    writing history into the past shows what a window ignores today, and this
    shows a window moving off rows that were once inside it.
    """

    def _shift(delta: timedelta) -> None:
        monkeypatch.setattr(restriction_service, "_now", lambda: _now() + delta)

    return _shift


@pytest.fixture
def moderator(db_session) -> User:
    return _make_user(
        db_session,
        "moderator@example.com",
        role=UserRole.MODERATOR,
        moderator_cells=[CELL],
    )


@pytest.fixture
def offender(db_session) -> User:
    """The member the reports are about."""
    return _make_user(db_session, "offender@example.com")


@pytest.fixture
def reporter(db_session) -> User:
    """The member filing them."""
    return _make_user(db_session, "reporter@example.com")


@pytest.fixture
def admin(db_session) -> User:
    """
    An unscoped decider.

    get_report_for_moderator() scopes a MODERATOR to her cells and matches a
    reported account by group+sector — which a moderator, an admin or a
    professional does not have — so a report naming one of those can only be
    decided by an ADMIN (§3.2's "הכל" against "אחריותו").
    """
    return _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)


# ---------------------------------------------------------------------------
# כלל 1 — "3 דיווחים תקפים ב-7 ימים → השעיה 48 שעות"
# ---------------------------------------------------------------------------


class TestAutoSuspensionThreshold:
    def test_one_short_of_the_threshold_suspends_nobody(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 2,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False
        assert offender.suspended_until is None
        assert offender.account_status == AccountStatus.ACTIVE

    def test_crossing_the_threshold_suspends_the_account(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is True
        assert offender.account_status == AccountStatus.SUSPENDED

    def test_the_suspension_runs_for_the_configured_hours(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )

        before = datetime.now(UTC)
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )
        after = datetime.now(UTC)

        db_session.refresh(offender)
        assert offender.suspended_until is not None
        # suspend_user() writes an aware value into a naive column; read back it
        # is naive, and UTC is what the whole schema stores.
        suspended_until = offender.suspended_until.replace(tzinfo=UTC)
        window = timedelta(hours=settings.AUTO_SUSPEND_HOURS)
        assert before + window <= suspended_until <= after + window

    def test_the_suspension_lands_on_the_decision_not_on_the_report(
        self, db_session, moderator, offender, reporter
    ):
        """
        The criterion reads "המשתמשת מושעית בהחלטה השלישית" — on the third
        *decision*.

        Every report here goes through the real flow and the account's state is
        read after each one, so what this pins is the moment the measure lands
        rather than only that it eventually does.
        """
        states = []
        for _ in range(settings.AUTO_SUSPEND_VALID_REPORTS):
            _decide_a_fresh_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                moderator=moderator,
                decision=ReportDecision.VALID,
            )
            db_session.refresh(offender)
            states.append(offender.is_suspended)

        assert states == [False] * (settings.AUTO_SUSPEND_VALID_REPORTS - 1) + [True]

    def test_pending_reports_do_not_count(
        self, db_session, moderator, offender, reporter
    ):
        """A threshold is about findings, not accusations."""
        for _ in range(settings.AUTO_SUSPEND_VALID_REPORTS + 2):
            _pending_report(
                db_session, reporter=reporter, post=_make_post(db_session, offender)
            )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_findings_older_than_the_window_do_not_count(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
            decided_at=_days_ago(settings.AUTO_SUSPEND_DAYS_WINDOW + 1),
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_findings_just_inside_the_window_do_count(
        self, db_session, moderator, offender, reporter
    ):
        """
        The other side of the same boundary, so the test above cannot pass
        because the window is broken rather than because it is respected.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
            decided_at=_days_ago(settings.AUTO_SUSPEND_DAYS_WINDOW - 1),
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is True

    def test_dismissed_reports_do_not_count(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS + 2,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_system_closed_reports_do_not_count(
        self, db_session, moderator, offender, reporter
    ):
        """
        CLOSED_ACCOUNT_DELETED (§9.4, ABF-117) is the system closing a report
        whose subject deleted her account — not a finding against anybody.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.CLOSED_ACCOUNT_DELETED,
            count=settings.AUTO_SUSPEND_VALID_REPORTS + 1,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_the_count_is_per_reported_member_not_per_reporter(
        self, db_session, moderator, offender
    ):
        """
        Three different members each reporting her once is the pattern this
        rule is looking for. A count kept per reporter would see three separate
        first offences and never reach the threshold.
        """
        for index in range(settings.AUTO_SUSPEND_VALID_REPORTS - 1):
            complainant = _make_user(db_session, f"complainant{index}@example.com")
            _decided_report(
                db_session,
                reporter=complainant,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"other-{index}",
            )
        last = _make_user(db_session, "complainant-last@example.com")

        _decide_a_fresh_report(
            db_session,
            reporter=last,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is True


# ---------------------------------------------------------------------------
# "כפל-השעיה: אין שגיאה"
# ---------------------------------------------------------------------------


class TestSuspensionIsNotDoubled:
    def _suspend_by_crossing(self, db_session, moderator, offender, reporter) -> None:
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

    def test_a_further_decision_against_a_suspended_member_is_not_an_error(
        self, db_session, moderator, offender, reporter
    ):
        """
        user_service.suspend_user() answers 400 for an account that is not
        ACTIVE. Reaching it a second time would turn a decision that is already
        recorded into a failed request, so the rule checks before it counts.
        """
        self._suspend_by_crossing(db_session, moderator, offender, reporter)

        decided = _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        assert decided.decision == ReportDecision.VALID

    def test_the_second_decision_does_not_extend_the_suspension(
        self, db_session, moderator, offender, reporter
    ):
        self._suspend_by_crossing(db_session, moderator, offender, reporter)
        db_session.refresh(offender)
        original_expiry = offender.suspended_until

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.suspended_until == original_expiry

    def test_the_second_decision_writes_no_second_audit_entry(
        self, db_session, moderator, offender, reporter
    ):
        self._suspend_by_crossing(db_session, moderator, offender, reporter)

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        assert len(_audit_entries(db_session, AuditAction.USER_SUSPENDED)) == 1

    def test_a_member_suspended_by_hand_is_not_suspended_again(
        self, db_session, moderator, reporter
    ):
        """
        The guard is on the account's state, not on how it got there — a
        moderator's manual suspension (§7.3) blocks the automatic one just the
        same, and is not disturbed by it.
        """
        offender = _make_user(
            db_session,
            "manually-suspended@example.com",
            account_status=AccountStatus.SUSPENDED,
        )
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        assert _audit_entries(db_session, AuditAction.USER_SUSPENDED) == []


# ---------------------------------------------------------------------------
# "רק חשבון של משתמשת מושעה"
# ---------------------------------------------------------------------------


class TestOnlyMembersAreSuspended:
    @pytest.mark.parametrize(
        "role", [UserRole.MODERATOR, UserRole.PROFESSIONAL, UserRole.ADMIN]
    )
    def test_a_reported_non_member_is_not_suspended(
        self, db_session, admin, reporter, role
    ):
        """
        A forum post can be authored by any of the four roles, so a report can
        name one. suspend_user() answers 400 for all three of these — the rule
        has to stop before it, or an upheld report against a professional would
        500 a decision that is already recorded.

        Decided by the admin rather than a moderator: a reported account with
        no cell of its own falls outside every moderator's scope, so a
        moderator would be refused 403 before the rule was ever reached.
        """
        author = _make_user(db_session, f"reported-{role.value}@example.com", role=role)
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=author,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS,
        )

        decided = _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=author,
            moderator=admin,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(author)
        assert decided.decision == ReportDecision.VALID
        assert author.is_suspended is False
        assert _audit_entries(db_session, AuditAction.USER_SUSPENDED) == []


# ---------------------------------------------------------------------------
# §9.3 — כלל 1 על הרישום
# ---------------------------------------------------------------------------


class TestAutoSuspensionAuditTrail:
    def _cross(self, db_session, moderator, offender, reporter) -> ForumPost:
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )
        post = _make_post(db_session, offender)
        report = _pending_report(db_session, reporter=reporter, post=post)
        _decide(db_session, report, moderator, ReportDecision.VALID)
        return post

    def test_the_suspension_is_recorded_against_the_deciding_moderator(
        self, db_session, moderator, offender, reporter
    ):
        """
        The rule fired by itself, but it fired on her decision. An audit trail
        whose actor is "the system" is one nobody can be asked about — the same
        reasoning restriction_service.apply_restriction() spells out.
        """
        self._cross(db_session, moderator, offender, reporter)

        entry = _audit_entries(db_session, AuditAction.USER_SUSPENDED)[0]
        assert entry.actor_id == moderator.id
        assert entry.entity_type == "User"
        assert entry.entity_id == offender.id
        assert entry.details["hours"] == settings.AUTO_SUSPEND_HOURS

    def test_the_entry_carries_neither_the_content_nor_the_note(
        self, db_session, moderator, offender, reporter
    ):
        post = self._cross(db_session, moderator, offender, reporter)

        entry = _audit_entries(db_session, AuditAction.USER_SUSPENDED)[0]
        assert post.content not in str(entry.details)
        assert NOTE not in str(entry.details)
        assert entry.details["reason"] == report_service.AUTO_SUSPENSION_REASON

    def test_the_notification_does_not_log_the_content_or_the_note(
        self, db_session, moderator, offender, reporter, caplog
    ):
        """
        The member's suspension email carries the reason, and the reason is a
        fixed sentence for exactly this: a report can be about a private
        message, and the note is free text written about a bereaved user.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )
        post = _make_post(db_session, offender)
        report = _pending_report(db_session, reporter=reporter, post=post)

        with caplog.at_level(logging.DEBUG):
            _decide(db_session, report, moderator, ReportDecision.VALID)

        assert post.content not in caplog.text
        assert NOTE not in caplog.text

    def test_no_entry_when_the_threshold_is_not_crossed(
        self, db_session, moderator, offender, reporter
    ):
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        assert _audit_entries(db_session, AuditAction.USER_SUSPENDED) == []


# ---------------------------------------------------------------------------
# כלל 2 — "5 דיווחים שגויים ב-30 ימים → is_report_restricted"
# ---------------------------------------------------------------------------


class TestFalseReporterFlag:
    def test_one_short_of_the_limit_restricts_nobody(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 2,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_reaching_the_limit_withdraws_the_reporting(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True

    def test_dismissals_older_than_the_window_do_not_count(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
            decided_at=_days_ago(settings.FALSE_REPORT_DAYS_WINDOW + 1),
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_dismissals_just_inside_the_window_do_count(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
            decided_at=_days_ago(settings.FALSE_REPORT_DAYS_WINDOW - 1),
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True

    def test_an_anonymized_report_restricts_nobody(
        self, db_session, moderator, offender
    ):
        """
        §9.4 keeps a report for five years without the person who filed it, so
        `reporter_id` can be NULL (ABF-112). Those must not aggregate into a
        single phantom over-reporter.
        """
        _fill_history(
            db_session,
            reporter=None,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
            prefix="anon",
        )

        # No exception, and no flag written anywhere — there is nobody to
        # write one on.
        report_service._check_frequent_false_reporter(db_session, None, moderator)

        assert (
            db_session.query(User).filter(User.is_report_restricted.is_(True)).count()
            == 0
        )
        assert _flag_audit_entries(db_session) == []

    def test_a_sixth_dismissal_writes_no_second_audit_entry(
        self, db_session, moderator, offender, reporter
    ):
        """
        §9.3 wants a record of the measure, and the measure is one event — not
        a row for every decision taken after it.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )
        for _ in range(2):
            _decide_a_fresh_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                moderator=moderator,
                decision=ReportDecision.INVALID,
            )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True
        assert len(_flag_audit_entries(db_session)) == 1


# ---------------------------------------------------------------------------
# §9.3 — כלל 2 על הרישום
# ---------------------------------------------------------------------------


class TestFalseReporterAuditTrail:
    def _cross(self, db_session, moderator, offender, reporter) -> ForumPost:
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )
        post = _make_post(db_session, offender)
        report = _pending_report(db_session, reporter=reporter, post=post)
        _decide(db_session, report, moderator, ReportDecision.INVALID)
        return post

    def test_the_measure_is_recorded_with_its_count_and_window(
        self, db_session, moderator, offender, reporter
    ):
        self._cross(db_session, moderator, offender, reporter)

        entry = _flag_audit_entries(db_session)[0]
        assert entry.actor_id == moderator.id
        assert entry.entity_type == "User"
        assert entry.entity_id == reporter.id
        assert entry.details["report_count"] == settings.FALSE_REPORT_LIMIT
        assert entry.details["window_days"] == settings.FALSE_REPORT_DAYS_WINDOW
        assert entry.details["automatic"] is True

    def test_it_is_told_apart_from_the_bounded_restriction_on_the_same_decision(
        self, db_session, moderator, offender, reporter
    ):
        """
        ABF-116's `user_restrictions` row and this flag cross on the same
        decision and share AuditAction.USER_RESTRICTED. `measure` is what says
        which of the two an entry is about — constants.py asks for one member
        and a details payload rather than an enum value per direction, because
        Postgres cannot remove one once it exists.
        """
        self._cross(db_session, moderator, offender, reporter)

        entries = _audit_entries(db_session, AuditAction.USER_RESTRICTED)
        measures = sorted(
            entry.details.get("measure") or entry.details["restriction_type"]
            for entry in entries
        )
        assert measures == ["report_restricted", RestrictionType.REPORTING.value]

    def test_the_entry_carries_neither_the_content_nor_the_note(
        self, db_session, moderator, offender, reporter
    ):
        post = self._cross(db_session, moderator, offender, reporter)

        entry = _flag_audit_entries(db_session)[0]
        assert post.content not in str(entry.details)
        assert NOTE not in str(entry.details)

    def test_the_bounded_restriction_is_still_applied_alongside_it(
        self, db_session, moderator, offender, reporter
    ):
        """
        ABF-154 hardens §7.2's second row; it does not replace what ABF-116
        built. The row is what the moderator dashboard lists and what carries
        the end date, and the §7.2 alert is sent about it.
        """
        self._cross(db_session, moderator, offender, reporter)

        restriction = (
            db_session.query(UserRestriction)
            .filter(
                UserRestriction.user_id == reporter.id,
                UserRestriction.restriction_type == RestrictionType.REPORTING,
            )
            .one()
        )
        assert restriction.expires_at > _now()

    def test_no_entry_when_the_limit_is_not_reached(
        self, db_session, moderator, offender, reporter
    ):
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        assert _flag_audit_entries(db_session) == []


# ---------------------------------------------------------------------------
# "משתמשת מוגבלת: 403 עם המפתח הנכון"
# ---------------------------------------------------------------------------


class TestRestrictedReporterIsRefused:
    async def _report(self, client, post_id: str, **kwargs):
        return await client.post(
            f"{FORUM_BASE}/posts/{post_id}/report",
            json={
                "target_type": ReportTargetType.FORUM_POST.value,
                "target_id": post_id,
                "reason": ReportReason.SPAM.value,
            },
            **kwargs,
        )

    def _restricted(self, db_session) -> User:
        return _make_user(
            db_session, "restricted@example.com", is_report_restricted=True
        )

    async def test_a_restricted_member_is_refused(
        self, client, db_session, as_user, offender
    ):
        as_user(self._restricted(db_session))
        post = _make_post(db_session, offender)

        response = await self._report(client, post.id)

        assert response.status_code == 403
        assert (
            response.json()["detail"] == MESSAGES["reports.reporter_restricted"][HEBREW]
        )

    async def test_the_refusal_is_translated_like_every_other_one(
        self, client, db_session, as_user, offender
    ):
        """
        ABF-137: the message is a catalogue key resolved against the request's
        Accept-Language, not a sentence written where it is raised. What
        reaches the client is finished text — which is why no `reports.*` name
        appears in the frontend's KNOWN_ERROR_KEYS.
        """
        as_user(self._restricted(db_session))
        post = _make_post(db_session, offender)

        response = await self._report(
            client, post.id, headers={"Accept-Language": "en"}
        )

        assert response.status_code == 403
        assert (
            response.json()["detail"]
            == MESSAGES["reports.reporter_restricted"][ENGLISH]
        )

    async def test_the_refusal_comes_before_the_content_is_looked_up(
        self, client, db_session, as_user
    ):
        """
        An id that does not exist answers 403 too, not 404. A restricted member
        who could tell the two apart would have a probe for other people's
        content — the same ordering assert_may_file_report() and
        assert_may_send_direct_message() are placed for.
        """
        as_user(self._restricted(db_session))

        response = await self._report(client, "no-such-post-id")

        assert response.status_code == 403

    async def test_no_report_row_is_written(
        self, client, db_session, as_user, offender
    ):
        as_user(self._restricted(db_session))
        post = _make_post(db_session, offender)

        await self._report(client, post.id)

        assert db_session.query(Report).count() == 0

    async def test_an_unrestricted_member_still_files(
        self, client, db_session, as_user, offender, reporter
    ):
        as_user(reporter)
        post = _make_post(db_session, offender)

        response = await self._report(client, post.id)

        assert response.status_code == 201

    async def test_a_lift_restores_the_ability_to_file(
        self, client, db_session, as_user, offender, admin
    ):
        """
        ABF-162: the ticket's own proof of work, end to end — an admin's lift
        is what ends the refusal, not the passage of time (this module's
        flag has no expiry of its own; see its docstring on `User`).
        """
        restricted = self._restricted(db_session)
        user_service.lift_report_restriction(db_session, restricted.id, admin)
        db_session.refresh(restricted)
        as_user(restricted)

        response = await self._report(client, _make_post(db_session, offender).id)

        assert response.status_code == 201

    async def test_the_flag_takes_effect_on_the_decision_that_set_it(
        self, client, db_session, as_user, moderator, offender, reporter
    ):
        """
        End to end, the way the ticket's proof of work reads: five dismissed
        reports, and the next attempt comes back 403.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        as_user(reporter)
        response = await self._report(client, _make_post(db_session, offender).id)

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# ABF-XXX — "לאחר lift, דחיות שהתקבלו לפני ה-lift לא מפעילות מחדש את ההגבלה"
# ---------------------------------------------------------------------------


def _restrict_then_lift(db_session, *, moderator, offender, reporter, admin):
    """
    The flag set by the real rule on the real flow, then lifted by the real
    ABF-162 service call. The dismissals that set it are a day old, well
    inside the 30-day window, which is the whole problem: by the window alone
    they would still count after the lift.
    """
    _fill_history(
        db_session,
        reporter=reporter,
        reported_user=offender,
        decision=ReportDecision.INVALID,
        count=settings.FALSE_REPORT_LIMIT - 1,
        decided_at=_days_ago(1),
        prefix="before-lift",
    )
    _decide_a_fresh_report(
        db_session,
        reporter=reporter,
        reported_user=offender,
        moderator=moderator,
        decision=ReportDecision.INVALID,
    )
    db_session.refresh(reporter)
    assert reporter.is_report_restricted is True

    user_service.lift_report_restriction(db_session, reporter.id, admin)
    db_session.refresh(reporter)
    assert reporter.is_report_restricted is False


def _dismiss_after_the_lift(db_session, *, moderator, offender, reporter, count):
    """
    `count` dismissals decided after the lift: all but the last written as
    history stamped now, the last decided for real so the rule runs on it.
    """
    _fill_history(
        db_session,
        reporter=reporter,
        reported_user=offender,
        decision=ReportDecision.INVALID,
        count=count - 1,
        prefix="after-lift",
    )
    _decide_a_fresh_report(
        db_session,
        reporter=reporter,
        reported_user=offender,
        moderator=moderator,
        decision=ReportDecision.INVALID,
    )
    db_session.refresh(reporter)


class TestALiftStartsTheCountAgain:
    """
    The ticket's three criteria, each on the real decide_report() flow after
    a real lift, plus the two edges a boundary has (the instant of the lift,
    and a lift older than the window) and "the latest lift", which the
    ticket names.
    """

    def test_a_queued_report_dismissed_after_the_lift_does_not_restrict_again(
        self, db_session, moderator, offender, reporter, admin, revoked_alerts
    ):
        """
        The ticket's own scenario: a report filed before the lift, still in
        the queue, dismissed after it. Before this ticket, that one dismissal
        plus the five the lift answered made six inside the window, and the
        flag came straight back with nobody told.
        """
        queued = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _restrict_then_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            admin=admin,
        )

        _decide(db_session, queued, moderator, ReportDecision.INVALID)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False
        assert len(_flag_audit_entries(db_session)) == 1
        assert [user_id for _, user_id in revoked_alerts] == [reporter.id]

    def test_dismissals_from_before_the_lift_do_not_top_up_the_new_count(
        self, db_session, moderator, offender, reporter, admin
    ):
        """
        One short after the lift stays one short, though the window holds
        twice the limit. The pre-lift dismissals are left out, not
        discounted.
        """
        _restrict_then_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            admin=admin,
        )

        _dismiss_after_the_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )

        assert reporter.is_report_restricted is False

    def test_the_full_limit_after_the_lift_restricts_again(
        self, db_session, moderator, offender, reporter, admin, revoked_alerts
    ):
        """
        The lift is a clean slate, not an exemption: five new dismissals
        withdraw the reporting again, record it again and alert the
        moderators again, exactly as the first time.
        """
        _restrict_then_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            admin=admin,
        )

        _dismiss_after_the_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            count=settings.FALSE_REPORT_LIMIT,
        )

        assert reporter.is_report_restricted is True
        assert len(_flag_audit_entries(db_session)) == 2
        assert [user_id for _, user_id in revoked_alerts] == [reporter.id] * 2

    def test_the_new_entry_counts_from_the_lift_and_says_so(
        self, db_session, moderator, offender, reporter, admin
    ):
        """
        `report_count` is the post-lift count, not the ten in the window. The
        entry names the lift it counted from, so an admin reading "5 in 30
        days" right after her own lift can see why.
        """
        _restrict_then_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            admin=admin,
        )
        lifted_at = reporter.report_restriction_lifted_at

        _dismiss_after_the_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            count=settings.FALSE_REPORT_LIMIT,
        )

        # Told apart by content, not `timestamp`: SQLite stamps both entries
        # with the same whole second.
        first, again = sorted(
            _flag_audit_entries(db_session),
            key=lambda e: "counted_since_lift" in e.details,
        )
        assert "counted_since_lift" not in first.details
        assert again.details["report_count"] == settings.FALSE_REPORT_LIMIT
        assert again.details["counted_since_lift"] == lifted_at.isoformat()

    def test_only_the_latest_lift_starts_the_count(
        self, db_session, moderator, offender, reporter, admin
    ):
        """
        Restricted, lifted, restricted again on five new dismissals, lifted
        again. The five between the two lifts are what the second lift
        answered, so they no longer count either.
        """
        _restrict_then_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            admin=admin,
        )
        _dismiss_after_the_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            count=settings.FALSE_REPORT_LIMIT,
        )
        assert reporter.is_report_restricted is True
        user_service.lift_report_restriction(db_session, reporter.id, admin)

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_a_dismissal_decided_at_the_instant_of_the_lift_does_not_count(
        self, db_session, moderator, offender, reporter
    ):
        """
        "After the lift" is strict. A decision stamped with the lift's own
        instant was already on record when the admin looked.
        """
        lifted_at = _days_ago(1)
        reporter.report_restriction_lifted_at = lifted_at
        db_session.commit()
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
            decided_at=lifted_at,
        )

        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_a_dismissal_decided_just_after_the_lift_does_count(
        self, db_session, moderator, offender, reporter
    ):
        lifted_at = _days_ago(1)
        reporter.report_restriction_lifted_at = lifted_at
        db_session.commit()
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
            decided_at=lifted_at + timedelta(microseconds=1),
        )

        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True

    def test_a_lift_older_than_the_window_leaves_the_window_in_charge(
        self, db_session, moderator, offender, reporter
    ):
        """
        The lift only ever narrows the window. Dismissals after an old lift
        that have since left the 30 days do not count.
        """
        reporter.report_restriction_lifted_at = _days_ago(
            settings.FALSE_REPORT_DAYS_WINDOW + 10
        )
        db_session.commit()
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
            decided_at=_days_ago(settings.FALSE_REPORT_DAYS_WINDOW + 1),
        )

        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_after_an_old_lift_the_window_counts_as_it_always_did(
        self, db_session, moderator, offender, reporter
    ):
        reporter.report_restriction_lifted_at = _days_ago(
            settings.FALSE_REPORT_DAYS_WINDOW + 10
        )
        db_session.commit()
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
            decided_at=_days_ago(settings.FALSE_REPORT_DAYS_WINDOW - 1),
        )

        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True


class TestAMemberNeverLiftedIsCountedAsBefore:
    """
    "משתמש ללא lift בכלל — ההתנהגות הקיימת לא משתנה". TestFalseReporterFlag
    and TestFalseReporterAuditTrail already pin the count and the window, and
    pass unchanged. These pin what the ticket adds, and only for a member
    who has been lifted: the column and the audit key.
    """

    def test_a_member_never_lifted_has_no_lift_time(self, db_session, reporter):
        assert reporter.report_restriction_lifted_at is None

    def test_the_limit_still_restricts_on_the_whole_window(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
            decided_at=_days_ago(settings.FALSE_REPORT_DAYS_WINDOW - 1),
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True

    def test_the_audit_entry_is_the_one_it_always_was(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        assert _flag_audit_entries(db_session)[0].details == {
            "measure": "report_restricted",
            "report_count": settings.FALSE_REPORT_LIMIT,
            "window_days": settings.FALSE_REPORT_DAYS_WINDOW,
            "automatic": True,
        }


class TestALiftDoesNotReachTheOtherDirection:
    def test_findings_against_a_lifted_member_still_count_from_before_the_lift(
        self, db_session, moderator, offender, reporter, admin
    ):
        """
        The lift answers her *reporting*. Reports upheld against her own
        content are §7.2's other direction, and the lift does not wipe them:
        the suspension rule counts its full 7 days as before.
        """
        _restrict_then_lift(
            db_session,
            moderator=moderator,
            offender=offender,
            reporter=reporter,
            admin=admin,
        )
        _fill_history(
            db_session,
            reporter=offender,
            reported_user=reporter,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
            decided_at=_days_ago(2),
            prefix="against-her",
        )

        _decide_a_fresh_report(
            db_session,
            reporter=offender,
            reported_user=reporter,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_suspended is True


# ---------------------------------------------------------------------------
# "שני הכיוונים אינם מצטלבים"
# ---------------------------------------------------------------------------


class TestTheDirectionsDoNotCross:
    def test_upheld_reports_do_not_withdraw_the_reporters_reporting(
        self, db_session, moderator, offender, reporter
    ):
        """Being right is not an offence."""
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.FALSE_REPORT_LIMIT,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_dismissed_reports_do_not_suspend_the_member_they_named(
        self, db_session, moderator, offender, reporter
    ):
        """A report a moderator dismissed is not evidence of anything."""
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_crossing_rule_one_does_not_restrict_the_member_who_reported_her(
        self, db_session, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_crossing_rule_two_does_not_suspend_the_over_reporter(
        self, db_session, moderator, offender, reporter
    ):
        """
        §7.2 answers an over-reporter with an allowance and, since ABF-154, by
        withdrawing the reporting. Never with a suspension — she has not been
        found against, she has filled a queue.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_suspended is False
        assert reporter.account_status == AccountStatus.ACTIVE


# ---------------------------------------------------------------------------
# "טסטים עם fixtures מבוקרי-זמן"
# ---------------------------------------------------------------------------


class TestWindowsAreMeasuredFromTheClock:
    def test_a_finding_leaves_the_suspension_window_as_time_passes(
        self, db_session, moderator, offender, reporter, shifted_clock
    ):
        """
        The same rows, the same query, a later "now" — and the threshold no
        longer reaches.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS,
        )
        shifted_clock(timedelta(days=settings.AUTO_SUSPEND_DAYS_WINDOW + 1))

        report_service._check_auto_suspension(db_session, offender, moderator)

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_the_same_findings_suspend_while_the_window_still_covers_them(
        self, db_session, moderator, offender, reporter, shifted_clock
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS,
        )
        shifted_clock(timedelta(days=settings.AUTO_SUSPEND_DAYS_WINDOW - 1))

        report_service._check_auto_suspension(db_session, offender, moderator)

        db_session.refresh(offender)
        assert offender.is_suspended is True

    def test_a_dismissal_leaves_the_reporting_window_as_time_passes(
        self, db_session, moderator, offender, reporter, shifted_clock
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
        )
        shifted_clock(timedelta(days=settings.FALSE_REPORT_DAYS_WINDOW + 1))

        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False

    def test_the_same_dismissals_restrict_while_the_window_still_covers_them(
        self, db_session, moderator, offender, reporter, shifted_clock
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
        )
        shifted_clock(timedelta(days=settings.FALSE_REPORT_DAYS_WINDOW - 1))

        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True

    def test_the_flag_does_not_lapse_on_its_own(
        self, db_session, moderator, offender, reporter, shifted_clock
    ):
        """
        Out of scope by the ticket's own list: nothing expires this measure.
        Pinned rather than left implied — every restriction ABF-116 writes ends
        by expiring, and "it works like the other one" is the assumption a
        reader would otherwise make.
        """
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT,
        )
        report_service._check_frequent_false_reporter(db_session, reporter, moderator)

        shifted_clock(timedelta(days=settings.FALSE_REPORT_DAYS_WINDOW * 10))

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True


# ---------------------------------------------------------------------------
# "הספים נכתבים כקונפיגורציה ולא כמספרים קשיחים"
# ---------------------------------------------------------------------------


class TestThresholdsAreConfiguration:
    def test_retuning_the_suspension_threshold_changes_when_it_fires(
        self, db_session, monkeypatch, moderator, offender, reporter
    ):
        """
        §7.2 reads "2+" and the setting has held 3 since it was written.
        ABF-154 settles on 3 — the number the ticket asks for — and reading it
        from `settings` is what lets the first real run move it without a
        deploy.
        """
        monkeypatch.setattr(settings, "AUTO_SUSPEND_VALID_REPORTS", 2)
        _decided_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            target_id="old-0",
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is True

    def test_retuning_the_suspension_window_changes_what_counts(
        self, db_session, monkeypatch, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
            decided_at=_days_ago(3),
        )
        monkeypatch.setattr(settings, "AUTO_SUSPEND_DAYS_WINDOW", 1)

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        db_session.refresh(offender)
        assert offender.is_suspended is False

    def test_retuning_the_duration_changes_the_end_date(
        self, db_session, monkeypatch, moderator, offender, reporter
    ):
        monkeypatch.setattr(settings, "AUTO_SUSPEND_VALID_REPORTS", 1)
        monkeypatch.setattr(settings, "AUTO_SUSPEND_HOURS", 2)

        before = datetime.now(UTC)
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )
        after = datetime.now(UTC)

        db_session.refresh(offender)
        suspended_until = offender.suspended_until.replace(tzinfo=UTC)
        window = timedelta(hours=2)
        assert before + window <= suspended_until <= after + window

    def test_retuning_the_false_report_limit_changes_when_it_fires(
        self, db_session, monkeypatch, moderator, offender, reporter
    ):
        monkeypatch.setattr(settings, "FALSE_REPORT_LIMIT", 2)
        _decided_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            target_id="old-0",
        )

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True

    def test_retuning_the_false_report_window_changes_what_counts(
        self, db_session, monkeypatch, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
            decided_at=_days_ago(3),
        )
        monkeypatch.setattr(settings, "FALSE_REPORT_DAYS_WINDOW", 1)

        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        db_session.refresh(reporter)
        assert reporter.is_report_restricted is False


# ---------------------------------------------------------------------------
# ABF-164 — "כאשר כלל אוטומטי מופעל, נשלח מייל"
# ---------------------------------------------------------------------------

OTHER_CELL = {"group": UserType.WIDOW.value, "sector": Sector.LITVISH.value}


def _cross_rule_one(db_session, moderator, offender, reporter) -> ForumPost:
    """Two upheld findings on record, then the third decided for real."""
    _fill_history(
        db_session,
        reporter=reporter,
        reported_user=offender,
        decision=ReportDecision.VALID,
        count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
    )
    post = _make_post(db_session, offender)
    report = _pending_report(db_session, reporter=reporter, post=post)
    _decide(db_session, report, moderator, ReportDecision.VALID)
    return post


def _cross_rule_two(db_session, moderator, offender, reporter) -> ForumPost:
    """Four dismissals on record, then the fifth decided for real."""
    _fill_history(
        db_session,
        reporter=reporter,
        reported_user=offender,
        decision=ReportDecision.INVALID,
        count=settings.FALSE_REPORT_LIMIT - 1,
    )
    post = _make_post(db_session, offender)
    report = _pending_report(db_session, reporter=reporter, post=post)
    _decide(db_session, report, moderator, ReportDecision.INVALID)
    return post


@pytest.fixture
def suspension_alerts(monkeypatch) -> list[tuple[list[str], str, int]]:
    """Every send_auto_suspension_alert() call, as (sorted recipients, id, hours)."""
    sent: list[tuple[list[str], str, int]] = []
    monkeypatch.setattr(
        report_service,
        "send_auto_suspension_alert",
        lambda emails, user_id, hours: sent.append((sorted(emails), user_id, hours)),
    )
    return sent


@pytest.fixture
def revoked_alerts(monkeypatch) -> list[tuple[list[str], str]]:
    """Every send_reporting_revoked_alert() call, as (sorted recipients, id)."""
    sent: list[tuple[list[str], str]] = []
    monkeypatch.setattr(
        report_service,
        "send_reporting_revoked_alert",
        lambda emails, user_id: sent.append((sorted(emails), user_id)),
    )
    return sent


class _RecordingSMTP:
    """A mail server that keeps what it is handed, for the end-to-end tests."""

    delivered: list = []

    def __init__(self, host, port):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        _RecordingSMTP.delivered.append(msg)


@pytest.fixture
def mail_server(monkeypatch) -> Callable[[str], list]:
    """
    Turn real sending on against _RecordingSMTP, and hand back a lookup of what
    was delivered under a given subject.

    By subject, because one decision can set off several notifications and a
    test is about one of them. The others are still log-only stubs today, and
    filtering keeps these tests true on the day one of them starts sending.
    """
    _RecordingSMTP.delivered = []
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_service.smtplib, "SMTP", _RecordingSMTP)

    def _delivered(subject_fragment: str) -> list:
        return [
            msg
            for msg in _RecordingSMTP.delivered
            if subject_fragment in str(make_header(decode_header(msg["Subject"])))
        ]

    return _delivered


def _html(msg) -> str:
    return msg.get_payload(decode=True).decode("utf-8")


class TestAutoSuspensionEmailsTheAdminTeam:
    def test_crossing_rule_one_emails_every_active_admin(
        self, db_session, suspension_alerts, moderator, offender, reporter
    ):
        """
        "צוות הניהול" means every active admin, at the address they chose for
        alerts or, failing that, the one they log in with. It does not include
        a moderator, a cancelled admin, or the member herself: her own email is
        user_service.suspend_user()'s, and it is out of this ticket's scope.
        """
        _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        _make_user(
            db_session,
            "admin2@example.com",
            role=UserRole.ADMIN,
            alert_email="admin2-alerts@example.com",
        )
        _make_user(
            db_session,
            "former-admin@example.com",
            role=UserRole.ADMIN,
            account_status=AccountStatus.CANCELLED,
        )

        _cross_rule_one(db_session, moderator, offender, reporter)

        assert suspension_alerts == [
            (
                ["admin2-alerts@example.com", "admin@example.com"],
                offender.id,
                settings.AUTO_SUSPEND_HOURS,
            )
        ]

    def test_the_email_is_sent_after_the_suspension_is_saved(
        self, db_session, monkeypatch, admin, moderator, offender, reporter
    ):
        """The ticket's "לאחר שהפעולה נשמרה ב-DB", checked at the moment of sending."""
        seen: dict[str, object] = {}

        def _record(emails, user_id, hours):
            row = db_session.query(User).filter(User.id == user_id).one()
            seen["status"] = row.account_status
            seen["audited"] = bool(
                _audit_entries(db_session, AuditAction.USER_SUSPENDED)
            )

        monkeypatch.setattr(report_service, "send_auto_suspension_alert", _record)

        _cross_rule_one(db_session, moderator, offender, reporter)

        assert seen == {"status": AccountStatus.SUSPENDED, "audited": True}

    def test_one_short_of_the_threshold_emails_nobody(
        self, db_session, suspension_alerts, admin, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 2,
        )
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        assert suspension_alerts == []

    def test_a_further_decision_against_a_suspended_member_emails_nobody(
        self, db_session, suspension_alerts, admin, moderator, offender, reporter
    ):
        """No double suspension (ABF-154), so no second email about one."""
        _cross_rule_one(db_session, moderator, offender, reporter)
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.VALID,
        )

        assert len(suspension_alerts) == 1

    def test_crossing_rule_two_sends_no_suspension_email(
        self, db_session, suspension_alerts, admin, moderator, offender, reporter
    ):
        _cross_rule_two(db_session, moderator, offender, reporter)

        assert suspension_alerts == []

    def test_no_admin_to_alert_is_a_warning_not_silence(
        self, db_session, monkeypatch, moderator, offender, reporter, caplog
    ):
        monkeypatch.setattr(settings, "SMTP_HOST", "")

        with caplog.at_level(logging.WARNING):
            _cross_rule_one(db_session, moderator, offender, reporter)

        assert (
            f"[EMAIL] Automatic suspension of user {offender.id}: no admin to alert"
            in caplog.text
        )

    def test_the_mail_reaches_the_admin_and_names_only_the_account(
        self, db_session, mail_server, admin, moderator, offender, reporter
    ):
        """The ticket's proof, end to end: a real message to the admin, over SMTP."""
        post = _cross_rule_one(db_session, moderator, offender, reporter)

        delivered = mail_server("השעיה אוטומטית")
        assert [msg["To"] for msg in delivered] == [admin.email]
        html = _html(delivered[0])
        assert offender.id in html
        assert f"{settings.AUTO_SUSPEND_HOURS} שעות" in html
        assert post.content not in html
        assert NOTE not in html
        assert offender.email not in html


class TestRevokedReportingEmailsTheCellModerators:
    def test_crossing_rule_two_emails_the_moderators_of_her_cell(
        self, db_session, revoked_alerts, admin, offender, reporter
    ):
        """
        The email goes to the moderators covering the reporter's cell, at their
        alert address where one is set. That is the routing every other
        moderator alert in this module uses. It does not go to a moderator of
        another cell or to the admins: §7.2 makes an over-eager reporter a
        moderator's matter, and ABF-116 drew the same line.
        """
        deciding = _make_user(
            db_session,
            "moderator@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[CELL],
            alert_email="moderator-alerts@example.com",
        )
        _make_user(
            db_session,
            "colleague@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[CELL, OTHER_CELL],
        )
        _make_user(
            db_session,
            "elsewhere@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[OTHER_CELL],
        )

        _cross_rule_two(db_session, deciding, offender, reporter)

        assert revoked_alerts == [
            (
                ["colleague@example.com", "moderator-alerts@example.com"],
                reporter.id,
            )
        ]

    def test_the_email_is_sent_after_the_flag_is_saved(
        self, db_session, monkeypatch, moderator, offender, reporter
    ):
        seen: dict[str, object] = {}

        def _record(emails, user_id):
            row = db_session.query(User).filter(User.id == user_id).one()
            seen["flag"] = row.is_report_restricted
            seen["audited"] = bool(_flag_audit_entries(db_session))

        monkeypatch.setattr(report_service, "send_reporting_revoked_alert", _record)

        _cross_rule_two(db_session, moderator, offender, reporter)

        assert seen == {"flag": True, "audited": True}

    def test_one_short_of_the_limit_emails_nobody(
        self, db_session, revoked_alerts, moderator, offender, reporter
    ):
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 2,
        )
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        assert revoked_alerts == []

    def test_a_sixth_dismissal_emails_nobody_again(
        self, db_session, revoked_alerts, moderator, offender, reporter
    ):
        """The flag is set once, so it is reported once."""
        _cross_rule_two(db_session, moderator, offender, reporter)
        _decide_a_fresh_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            moderator=moderator,
            decision=ReportDecision.INVALID,
        )

        assert len(revoked_alerts) == 1

    def test_crossing_rule_one_sends_no_revoked_reporting_email(
        self, db_session, revoked_alerts, moderator, offender, reporter
    ):
        _cross_rule_one(db_session, moderator, offender, reporter)

        assert revoked_alerts == []

    def test_the_mail_reaches_the_moderator_and_names_only_the_account(
        self, db_session, mail_server, moderator, offender, reporter
    ):
        """The ticket's proof, end to end: a real message to the moderator, over SMTP."""
        post = _cross_rule_two(db_session, moderator, offender, reporter)

        delivered = mail_server("שלילת אפשרות הדיווח")
        assert [msg["To"] for msg in delivered] == [moderator.email]
        html = _html(delivered[0])
        assert reporter.id in html
        assert post.content not in html
        assert NOTE not in html
        assert reporter.email not in html


class TestAFailedEmailDoesNotUndoTheMeasure:
    """
    The third acceptance criterion: "כשל בשליחת המייל אינו גורר כשל בפעולה
    הראשית". The tests cover both the send and the roster lookup in front of
    it, because either one can be what fails.
    """

    @staticmethod
    def _explode(*args, **kwargs):
        raise RuntimeError("mail is down")

    @pytest.mark.parametrize(
        "target", ["send_auto_suspension_alert", "_admin_team_emails"]
    )
    def test_the_suspension_stands(
        self,
        db_session,
        monkeypatch,
        caplog,
        admin,
        moderator,
        offender,
        reporter,
        target,
    ):
        monkeypatch.setattr(report_service, target, self._explode)
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            count=settings.AUTO_SUSPEND_VALID_REPORTS - 1,
        )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        with caplog.at_level(logging.ERROR):
            decided = _decide(db_session, report, moderator, ReportDecision.VALID)

        assert decided.decision == ReportDecision.VALID
        db_session.refresh(offender)
        assert offender.account_status == AccountStatus.SUSPENDED
        assert len(_audit_entries(db_session, AuditAction.USER_SUSPENDED)) == 1
        assert (
            "Failed to alert the admins about the automatic suspension of user "
            f"{offender.id}" in caplog.text
        )

    @pytest.mark.parametrize(
        "target", ["send_reporting_revoked_alert", "_moderator_emails_for_author"]
    )
    def test_the_withdrawn_reporting_stands(
        self, db_session, monkeypatch, caplog, moderator, offender, reporter, target
    ):
        monkeypatch.setattr(report_service, target, self._explode)
        _fill_history(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            count=settings.FALSE_REPORT_LIMIT - 1,
        )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        with caplog.at_level(logging.ERROR):
            decided = _decide(db_session, report, moderator, ReportDecision.INVALID)

        assert decided.decision == ReportDecision.INVALID
        db_session.refresh(reporter)
        assert reporter.is_report_restricted is True
        assert len(_flag_audit_entries(db_session)) == 1
        assert (
            "Failed to alert the moderators about the revoked reporting of user "
            f"{reporter.id}" in caplog.text
        )

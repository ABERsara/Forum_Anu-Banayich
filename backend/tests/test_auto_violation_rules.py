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
  * every window is exercised with the clock under the test's control
    (TestWindowsAreMeasuredFromTheClock, and the `decided_at` offsets
    throughout).

Plus what the two rules must *not* do: cross into each other's direction
(TestTheDirectionsDoNotCross), reach an account that is not a member's
(TestOnlyMembersAreSuspended), write the decision's content into the audit log
or the notification (TestAutoSuspensionAuditTrail, TestFalseReporterAuditTrail),
or read a threshold from anywhere but `settings`
(TestThresholdsAreConfiguration).

Time is controlled the way tests/test_restrictions.py controls it — history is
written straight to `reports` with an explicit `decided_at`, and the decision
that crosses a threshold always goes through the real `decide_report()` flow.
`shifted_clock` adds the other direction: it moves what the service believes
"now" is, so a window can be walked off the end of rather than only written
behind.
"""

import logging
from datetime import UTC, datetime, timedelta

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
from app.services import report_service, restriction_service

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

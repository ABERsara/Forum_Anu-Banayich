"""
Automatic restrictions on repeat offenders (ABF-116, spec §5.3 מה"ק + §7.2).

The acceptance criteria this file pins, in the order the ticket lists them:

  * a single report restricts nobody (TestSingleReportDoesNotRestrict);
  * crossing a threshold applies a restriction that carries an end date
    (TestCrossingTheThresholdRestricts, TestFalseReporterThreshold);
  * the restriction blocks sending and leaves reading open
    (TestRestrictionBlocksSendingNotReading);
  * both directions are covered — the repeatedly-reported sender and the
    frequent false reporter (the two threshold classes above, plus
    TestDailyReportingAllowance for what direction B actually costs).

Plus the DoD's own: thresholds read from configuration rather than inlined
(TestThresholdsAreConfiguration), permission checks made straight against the
API rather than through any UI (§4.2, TestModeratorRestrictionsEndpoint,
TestMyRestrictionEndpoint), refusals that reveal nothing about who or what
exists (TestRefusalsRevealNothing), an audit entry for every automatic
measure (§9.3, TestAuditTrail), the §7.2 notifications
(TestRestrictionNotifications), and no message content in any log line or
response body (TestNoContentLeak).
"""

import logging
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    PostStatus,
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
from app.core.messages import HEBREW, MESSAGES
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.restriction import UserRestriction
from app.models.user import User
from app.schemas.forum import DirectMessageCreate
from app.schemas.report import ReportDecideRequest
from app.services import forum_service, report_service, restriction_service

MESSAGES_BASE = "/api/v1/messages"
MODERATOR_BASE = "/api/v1/moderator"
CONVERSATIONS_BASE = "/api/v1/conversations"

CELL = {"group": UserType.WIDOW.value, "sector": Sector.HASIDIC.value}
OTHER_CELL = {"group": UserType.WIDOWER.value, "sector": Sector.SEPHARDIC.value}

NOTE = "החלטה מנומקת לצורך הבדיקה"


def _now() -> datetime:
    """Naive UTC — the convention every timestamp in this schema follows."""
    return datetime.now(UTC).replace(tzinfo=None)


def _make_user(
    db_session,
    email: str,
    user_type: UserType | None = UserType.WIDOW,
    sector: Sector | None = Sector.HASIDIC,
    role: UserRole = UserRole.USER,
    alert_email: str | None = None,
    moderator_cells: list[dict[str, str]] | None = None,
    account_status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
        account_status=account_status,
        alert_email=alert_email,
        moderator_cells=moderator_cells,
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
    target_type: ReportTargetType = ReportTargetType.FORUM_POST,
    target_id: str = "target",
) -> Report:
    """
    A report that already carries a decision.

    Written straight to the table rather than driven through decide_report():
    these set up the *history* a threshold is measured against, and history
    has to be placeable at an arbitrary point in the past. The decision that
    crosses the threshold always goes through the real flow.
    """
    report = Report(
        reporter_id=None if reporter is None else reporter.id,
        target_type=target_type,
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


def _restriction_for(db_session, user: User, restriction_type: RestrictionType):
    return (
        db_session.query(UserRestriction)
        .filter(
            UserRestriction.user_id == user.id,
            UserRestriction.restriction_type == restriction_type,
        )
        .one_or_none()
    )


def _restrict(
    db_session,
    user: User,
    restriction_type: RestrictionType = RestrictionType.MESSAGING,
    *,
    expires_in: timedelta = timedelta(hours=48),
    report_count: int = 3,
    window_days: int = 30,
) -> UserRestriction:
    """Put a restriction on the books directly, for the enforcement tests."""
    restriction = UserRestriction(
        user_id=user.id,
        restriction_type=restriction_type,
        expires_at=_now() + expires_in,
        report_count=report_count,
        window_days=window_days,
    )
    db_session.add(restriction)
    db_session.commit()
    db_session.refresh(restriction)
    return restriction


@pytest.fixture
def as_user():
    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


@pytest.fixture
def moderator(db_session) -> User:
    return _make_user(
        db_session,
        "moderator@example.com",
        role=UserRole.MODERATOR,
        alert_email="mod-alerts@example.com",
        moderator_cells=[CELL],
        user_type=None,
        sector=None,
    )


@pytest.fixture
def offender(db_session) -> User:
    """The member other people keep reporting, and the platform restricts."""
    return _make_user(db_session, "offender@example.com")


@pytest.fixture
def pair(db_session):
    """A sender and the cell-mate she writes to."""
    sender = _make_user(db_session, "sender@example.com")
    recipient = _make_user(db_session, "recipient@example.com")
    return sender, recipient


# ---------------------------------------------------------------------------
# "דיווח בודד לא מפעיל הגבלה"
# ---------------------------------------------------------------------------


class TestSingleReportDoesNotRestrict:
    def test_one_upheld_report_restricts_nobody(self, db_session, moderator, offender):
        reporter = _make_user(db_session, "reporter@example.com")
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING) is None

    def test_one_short_of_the_threshold_still_restricts_nobody(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 2):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING) is None

    def test_one_dismissed_report_does_not_restrict_the_reporter(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.INVALID)

        assert _restriction_for(db_session, reporter, RestrictionType.REPORTING) is None

    def test_an_upheld_report_does_not_restrict_the_reporter(
        self, db_session, moderator, offender
    ):
        """The two directions do not cross: being right is not an offence."""
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.FALSE_REPORT_LIMIT):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"upheld-{index}",
            )

        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, reporter, RestrictionType.REPORTING) is None


# ---------------------------------------------------------------------------
# "חציית סף מפעילה הגבלה עם תאריך סיום"
# ---------------------------------------------------------------------------


class TestCrossingTheThresholdRestricts:
    def _cross(self, db_session, moderator, offender, reporter) -> None:
        """Fill the window to one short of the threshold, then decide one more."""
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _decide(db_session, report, moderator, ReportDecision.VALID)

    def test_threshold_applies_a_messaging_restriction(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        self._cross(db_session, moderator, offender, reporter)

        restriction = _restriction_for(db_session, offender, RestrictionType.MESSAGING)
        assert restriction is not None
        assert restriction.report_count == settings.DM_BLOCK_AFTER_REPORTS
        assert restriction.window_days == settings.DM_BLOCK_DAYS_WINDOW

    def test_the_restriction_carries_an_end_date(self, db_session, moderator, offender):
        reporter = _make_user(db_session, "reporter@example.com")
        self._cross(db_session, moderator, offender, reporter)

        restriction = _restriction_for(db_session, offender, RestrictionType.MESSAGING)
        expected = _now() + timedelta(hours=settings.DM_BLOCK_HOURS)
        assert restriction.expires_at > _now()
        assert abs((restriction.expires_at - expected).total_seconds()) < 60

    def test_the_restriction_names_the_report_that_crossed_the_threshold(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        last = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _decide(db_session, last, moderator, ReportDecision.VALID)

        restriction = _restriction_for(db_session, offender, RestrictionType.MESSAGING)
        assert restriction.triggered_by_report_id == last.id

    def test_the_account_itself_is_untouched(self, db_session, moderator, offender):
        """
        §7.2's second row asks for an alert and for a *human* to consider a
        suspension. A restriction is not one, and must not quietly become one.
        """
        reporter = _make_user(db_session, "reporter@example.com")
        self._cross(db_session, moderator, offender, reporter)

        db_session.refresh(offender)
        assert offender.is_suspended is False
        assert offender.suspended_until is None
        assert offender.account_status == AccountStatus.ACTIVE

    def test_decisions_older_than_the_window_do_not_count(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        stale = _now() - timedelta(days=settings.DM_BLOCK_DAYS_WINDOW + 1)
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                decided_at=stale,
                target_id=f"stale-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING) is None

    def test_pending_reports_do_not_count(self, db_session, moderator, offender):
        """A threshold is about findings, not accusations."""
        reporter = _make_user(db_session, "reporter@example.com")
        for _ in range(settings.DM_BLOCK_AFTER_REPORTS + 2):
            _pending_report(
                db_session, reporter=reporter, post=_make_post(db_session, offender)
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING) is None

    def test_system_closed_reports_do_not_count(self, db_session, moderator, offender):
        """
        CLOSED_ACCOUNT_DELETED (ABF-117) is the system closing a report whose
        subject deleted her account — not a finding against anybody.
        """
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS + 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.CLOSED_ACCOUNT_DELETED,
                target_id=f"closed-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING) is None

    def test_a_live_restriction_is_not_extended_or_duplicated(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        existing = _restrict(db_session, offender, expires_in=timedelta(hours=1))
        original_expiry = existing.expires_at

        for index in range(settings.DM_BLOCK_AFTER_REPORTS):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"more-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _decide(db_session, report, moderator, ReportDecision.VALID)

        rows = (
            db_session.query(UserRestriction)
            .filter(UserRestriction.user_id == offender.id)
            .all()
        )
        assert len(rows) == 1
        assert rows[0].expires_at == original_expiry

    def test_a_lapsed_restriction_does_not_block_a_new_one(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        _restrict(db_session, offender, expires_in=timedelta(hours=-1))

        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"new-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _decide(db_session, report, moderator, ReportDecision.VALID)

        rows = (
            db_session.query(UserRestriction)
            .filter(UserRestriction.user_id == offender.id)
            .all()
        )
        assert len(rows) == 2

    def test_the_count_is_per_sender_across_conversations(
        self, db_session, moderator, offender
    ):
        """
        The ticket's DB line: "צבירה לפי שולח על פני שיחות".

        One abusive message each to three different cell-mates is the count
        this rule is looking for — a per-conversation count would see three
        separate first offences and never reach a threshold.
        """
        reports = []
        for index in range(settings.DM_BLOCK_AFTER_REPORTS):
            victim = _make_user(db_session, f"victim{index}@example.com")
            reports.append(
                _decided_report(
                    db_session,
                    reporter=victim,
                    reported_user=offender,
                    decision=ReportDecision.VALID,
                    target_type=ReportTargetType.DIRECT_MESSAGE,
                    target_id=f"message-{index}",
                )
            )

        restriction = restriction_service.evaluate_after_decision(
            db_session, reports[-1], moderator
        )

        assert restriction is not None
        assert restriction.restriction_type == RestrictionType.MESSAGING
        assert restriction.report_count == settings.DM_BLOCK_AFTER_REPORTS


class TestFalseReporterThreshold:
    def _cross(self, db_session, moderator, reporter, offender) -> Report:
        for index in range(settings.FALSE_REPORT_LIMIT - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                target_id=f"dismissed-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )
        _decide(db_session, report, moderator, ReportDecision.INVALID)
        return report

    def test_threshold_applies_a_reporting_restriction_with_an_end_date(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "over-reporter@example.com")
        self._cross(db_session, moderator, reporter, offender)

        restriction = _restriction_for(db_session, reporter, RestrictionType.REPORTING)
        assert restriction is not None
        assert restriction.report_count == settings.FALSE_REPORT_LIMIT
        assert restriction.window_days == settings.FALSE_REPORT_DAYS_WINDOW
        expected = _now() + timedelta(days=settings.FALSE_REPORT_RESTRICTION_DAYS)
        assert abs((restriction.expires_at - expected).total_seconds()) < 60

    def test_it_does_not_also_restrict_her_messaging(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "over-reporter@example.com")
        self._cross(db_session, moderator, reporter, offender)

        assert _restriction_for(db_session, reporter, RestrictionType.MESSAGING) is None

    def test_dismissals_older_than_the_window_do_not_count(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "over-reporter@example.com")
        stale = _now() - timedelta(days=settings.FALSE_REPORT_DAYS_WINDOW + 1)
        for index in range(settings.FALSE_REPORT_LIMIT - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                decided_at=stale,
                target_id=f"stale-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.INVALID)

        assert _restriction_for(db_session, reporter, RestrictionType.REPORTING) is None

    def test_an_anonymized_report_restricts_nobody(
        self, db_session, moderator, offender
    ):
        """
        §9.4 keeps a report for five years without the person who filed it, so
        `reporter_id` can be NULL (ABF-112). Those must not aggregate into a
        single phantom over-reporter.
        """
        for index in range(settings.FALSE_REPORT_LIMIT):
            _decided_report(
                db_session,
                reporter=None,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                target_id=f"anon-{index}",
            )
        anonymized = _decided_report(
            db_session,
            reporter=None,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            target_id="anon-last",
        )

        assert (
            restriction_service.evaluate_after_decision(
                db_session, anonymized, moderator
            )
            is None
        )
        assert db_session.query(UserRestriction).count() == 0


# ---------------------------------------------------------------------------
# "ההגבלה חוסמת שליחה ולא קריאה"
# ---------------------------------------------------------------------------


class TestRestrictionBlocksSendingNotReading:
    async def test_restricted_sender_cannot_send(
        self, client, db_session, as_user, pair
    ):
        sender, recipient = pair
        _restrict(db_session, sender)
        as_user(sender)

        response = await client.post(
            MESSAGES_BASE,
            json={"recipient_id": recipient.id, "content": "שלום"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "errors.dm_restricted"

    async def test_nothing_is_stored_when_a_send_is_refused(
        self, client, db_session, as_user, pair
    ):
        sender, recipient = pair
        _restrict(db_session, sender)
        as_user(sender)

        await client.post(
            MESSAGES_BASE,
            json={"recipient_id": recipient.id, "content": "שלום"},
        )

        assert forum_service.DirectMessage is not None  # import guard
        assert db_session.query(forum_service.DirectMessage).count() == 0

    async def test_restricted_sender_can_still_read_the_inbox(
        self, client, db_session, as_user, pair
    ):
        sender, recipient = pair
        forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=recipient.id, content="הודעה מוקדמת"),
            sender,
        )
        _restrict(db_session, sender)
        as_user(sender)

        response = await client.get(MESSAGES_BASE)

        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_restricted_sender_can_still_read_a_conversation(
        self, client, db_session, as_user, pair
    ):
        sender, recipient = pair
        forum_service.send_direct_message(
            db_session,
            DirectMessageCreate(recipient_id=recipient.id, content="הודעה מוקדמת"),
            sender,
        )
        _restrict(db_session, sender)
        as_user(sender)
        key = forum_service.build_conversation_key(sender.id, recipient.id)

        response = await client.get(f"{CONVERSATIONS_BASE}/{key}/messages")

        assert response.status_code == 200
        assert len(response.json()["items"]) == 1

    async def test_the_other_side_can_still_write_to_a_restricted_member(
        self, client, db_session, as_user, pair
    ):
        """The measure is on the sender, not on the conversation."""
        restricted, cellmate = pair
        _restrict(db_session, restricted)
        as_user(cellmate)

        response = await client.post(
            MESSAGES_BASE,
            json={"recipient_id": restricted.id, "content": "אפשר לכתוב אליה"},
        )

        assert response.status_code == 201

    async def test_a_lapsed_restriction_stops_blocking_by_itself(
        self, client, db_session, as_user, pair
    ):
        sender, recipient = pair
        _restrict(db_session, sender, expires_in=timedelta(seconds=-1))
        as_user(sender)

        response = await client.post(
            MESSAGES_BASE,
            json={"recipient_id": recipient.id, "content": "שלום"},
        )

        assert response.status_code == 201

    async def test_a_reporting_restriction_does_not_block_sending(
        self, client, db_session, as_user, pair
    ):
        """The two kinds are separate measures and do not bleed into each other."""
        sender, recipient = pair
        _restrict(db_session, sender, RestrictionType.REPORTING)
        as_user(sender)

        response = await client.post(
            MESSAGES_BASE,
            json={"recipient_id": recipient.id, "content": "שלום"},
        )

        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Direction B, enforced: the daily allowance
# ---------------------------------------------------------------------------


class TestDailyReportingAllowance:
    async def test_the_allowance_is_spent_and_then_refused(
        self, client, db_session, as_user, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        _restrict(db_session, reporter, RestrictionType.REPORTING)
        as_user(reporter)

        posts = [
            _make_post(db_session, offender)
            for _ in range(settings.RESTRICTED_REPORTS_PER_DAY + 1)
        ]
        statuses = []
        for post in posts:
            response = await client.post(
                f"/api/v1/forum/posts/{post.id}/report",
                json={
                    "target_type": ReportTargetType.FORUM_POST.value,
                    "target_id": post.id,
                    "reason": ReportReason.SPAM.value,
                },
            )
            statuses.append(response.status_code)

        assert statuses[:-1] == [201] * settings.RESTRICTED_REPORTS_PER_DAY
        assert statuses[-1] == 429

    async def test_an_unrestricted_member_has_no_allowance_to_spend(
        self, client, db_session, as_user, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        as_user(reporter)

        statuses = []
        for _ in range(settings.RESTRICTED_REPORTS_PER_DAY + 2):
            post = _make_post(db_session, offender)
            response = await client.post(
                f"/api/v1/forum/posts/{post.id}/report",
                json={
                    "target_type": ReportTargetType.FORUM_POST.value,
                    "target_id": post.id,
                    "reason": ReportReason.SPAM.value,
                },
            )
            statuses.append(response.status_code)

        assert statuses == [201] * (settings.RESTRICTED_REPORTS_PER_DAY + 2)

    def test_reports_filed_more_than_a_day_ago_do_not_count(self, db_session, offender):
        reporter = _make_user(db_session, "reporter@example.com")
        _restrict(db_session, reporter, RestrictionType.REPORTING)
        for index in range(settings.RESTRICTED_REPORTS_PER_DAY + 3):
            report = _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                target_id=f"yesterday-{index}",
            )
            report.created_at = _now() - timedelta(days=2)
        db_session.commit()

        # Does not raise: nothing was filed inside the rolling 24 hours.
        restriction_service.assert_may_file_report(db_session, reporter)

    def test_the_refusal_names_the_daily_limit(self, db_session, offender):
        reporter = _make_user(db_session, "reporter@example.com")
        _restrict(db_session, reporter, RestrictionType.REPORTING)
        for index in range(settings.RESTRICTED_REPORTS_PER_DAY):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                target_id=f"today-{index}",
            )

        with pytest.raises(HTTPException) as exc:
            restriction_service.assert_may_file_report(db_session, reporter)

        assert exc.value.status_code == 429
        assert exc.value.detail == MESSAGES["reports.daily_limit_reached"][HEBREW]


# ---------------------------------------------------------------------------
# "דחייה שאינה מדליפה קיום של משתמשת או שיחה"
# ---------------------------------------------------------------------------


class TestRefusalsRevealNothing:
    async def test_a_restricted_send_answers_the_same_for_any_recipient(
        self, client, db_session, as_user, pair
    ):
        """
        The restriction is checked before the recipient is resolved, so a
        real cell-mate, a member of another cell and an id that belongs to
        nobody are indistinguishable in the reply.
        """
        sender, cellmate = pair
        outsider = _make_user(
            db_session,
            "outsider@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.SEPHARDIC,
        )
        _restrict(db_session, sender)
        as_user(sender)

        replies = []
        for recipient_id in (cellmate.id, outsider.id, "no-such-user"):
            response = await client.post(
                MESSAGES_BASE, json={"recipient_id": recipient_id, "content": "שלום"}
            )
            replies.append((response.status_code, response.json()["detail"]))

        assert len(set(replies)) == 1
        assert replies[0] == (403, "errors.dm_restricted")

    async def test_an_over_allowance_report_answers_the_same_for_any_target(
        self, client, db_session, as_user, offender
    ):
        """
        The allowance is checked before the reported content is looked up, so
        a real post and an id that belongs to nothing answer identically —
        otherwise the pair (404, 429) is a probe for other people's content.
        """
        reporter = _make_user(db_session, "reporter@example.com")
        _restrict(db_session, reporter, RestrictionType.REPORTING)
        for index in range(settings.RESTRICTED_REPORTS_PER_DAY):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                target_id=f"today-{index}",
            )
        as_user(reporter)
        real_post = _make_post(db_session, offender)

        statuses = []
        for target_id in (real_post.id, "no-such-post"):
            response = await client.post(
                f"/api/v1/forum/posts/{target_id}/report",
                json={
                    "target_type": ReportTargetType.FORUM_POST.value,
                    "target_id": target_id,
                    "reason": ReportReason.SPAM.value,
                },
            )
            statuses.append(response.status_code)

        assert statuses == [429, 429]


# ---------------------------------------------------------------------------
# The member's own view — GET /messages/restriction
# ---------------------------------------------------------------------------


class TestMyRestrictionEndpoint:
    async def test_unauthenticated_is_refused(self, client):
        response = await client.get(f"{MESSAGES_BASE}/restriction")
        assert response.status_code == 401

    async def test_an_unrestricted_member_gets_a_null_restriction(
        self, client, db_session, as_user
    ):
        as_user(_make_user(db_session, "fine@example.com"))

        response = await client.get(f"{MESSAGES_BASE}/restriction")

        assert response.status_code == 200
        assert response.json() == {"restriction": None}

    async def test_a_restricted_member_is_told_what_and_until_when(
        self, client, db_session, as_user
    ):
        member = _make_user(db_session, "restricted@example.com")
        restriction = _restrict(db_session, member)
        as_user(member)

        response = await client.get(f"{MESSAGES_BASE}/restriction")

        body = response.json()["restriction"]
        assert body["restriction_type"] == RestrictionType.MESSAGING.value
        assert datetime.fromisoformat(body["expires_at"]) == restriction.expires_at

    async def test_it_does_not_hand_back_the_evidence(
        self, client, db_session, as_user
    ):
        """
        A count of upheld reports returned to the person they were filed
        against is a hint about who has been reporting her.
        """
        member = _make_user(db_session, "restricted@example.com")
        _restrict(db_session, member)
        as_user(member)

        body = (await client.get(f"{MESSAGES_BASE}/restriction")).json()["restriction"]

        assert set(body) == {"restriction_type", "expires_at"}

    async def test_a_reporting_restriction_is_not_reported_as_a_messaging_one(
        self, client, db_session, as_user
    ):
        member = _make_user(db_session, "restricted@example.com")
        _restrict(db_session, member, RestrictionType.REPORTING)
        as_user(member)

        response = await client.get(f"{MESSAGES_BASE}/restriction")

        assert response.json() == {"restriction": None}


# ---------------------------------------------------------------------------
# The moderator's view — GET /moderator/restrictions (§3.2, §4.2)
# ---------------------------------------------------------------------------


class TestModeratorRestrictionsEndpoint:
    async def test_unauthenticated_is_refused(self, client):
        response = await client.get(f"{MODERATOR_BASE}/restrictions")
        assert response.status_code == 401

    async def test_a_member_may_not_read_it(self, client, db_session, as_user):
        as_user(_make_user(db_session, "member@example.com"))

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.status_code == 403

    async def test_a_professional_may_not_read_it(self, client, db_session, as_user):
        as_user(
            _make_user(
                db_session,
                "pro@example.com",
                role=UserRole.PROFESSIONAL,
                user_type=None,
                sector=None,
            )
        )

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.status_code == 403

    async def test_a_moderator_sees_a_restriction_in_her_cell(
        self, client, db_session, as_user, moderator, offender
    ):
        _restrict(db_session, offender)
        as_user(moderator)

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["member"]["id"] == offender.id
        assert body["items"][0]["report_count"] == 3
        assert body["items"][0]["window_days"] == 30

    async def test_a_moderator_does_not_see_another_cell(
        self, client, db_session, as_user, moderator
    ):
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.SEPHARDIC,
        )
        _restrict(db_session, elsewhere)
        as_user(moderator)

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.json() == {"items": [], "total": 0}

    async def test_a_moderator_with_no_cells_sees_nothing(
        self, client, db_session, as_user, offender
    ):
        """
        An empty cell list means "responsible for nothing". An empty or_()
        matches every row, so this is the case that has to be special-cased.
        """
        unassigned = _make_user(
            db_session,
            "unassigned@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[],
            user_type=None,
            sector=None,
        )
        _restrict(db_session, offender)
        as_user(unassigned)

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.json() == {"items": [], "total": 0}

    async def test_an_admin_sees_every_cell(
        self, client, db_session, as_user, offender
    ):
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.SEPHARDIC,
        )
        _restrict(db_session, offender)
        _restrict(db_session, elsewhere)
        as_user(
            _make_user(
                db_session,
                "admin@example.com",
                role=UserRole.ADMIN,
                user_type=None,
                sector=None,
            )
        )

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.json()["total"] == 2

    async def test_lapsed_restrictions_are_not_listed(
        self, client, db_session, as_user, moderator, offender
    ):
        _restrict(db_session, offender, expires_in=timedelta(seconds=-1))
        as_user(moderator)

        response = await client.get(f"{MODERATOR_BASE}/restrictions")

        assert response.json() == {"items": [], "total": 0}

    async def test_the_list_carries_no_report_content_and_no_reporter(
        self, client, db_session, as_user, moderator, offender
    ):
        _restrict(db_session, offender)
        as_user(moderator)

        item = (await client.get(f"{MODERATOR_BASE}/restrictions")).json()["items"][0]

        assert set(item) == {
            "id",
            "restriction_type",
            "expires_at",
            "report_count",
            "window_days",
            "created_at",
            "member",
        }
        assert set(item["member"]) == {"id", "first_name", "last_name"}


# ---------------------------------------------------------------------------
# §7.2's notifications
# ---------------------------------------------------------------------------


class TestRestrictionNotifications:
    def _admin(self, db_session) -> User:
        return _make_user(
            db_session,
            "admin@example.com",
            role=UserRole.ADMIN,
            alert_email="admin-alerts@example.com",
            user_type=None,
            sector=None,
        )

    def test_a_messaging_restriction_alerts_the_moderator_and_the_admin(
        self, db_session, monkeypatch, moderator, offender
    ):
        admin = self._admin(db_session)
        sent: list[tuple[str, str]] = []
        monkeypatch.setattr(
            report_service,
            "send_sending_restriction_alert",
            lambda email, user_id, expires_at: sent.append((email, user_id)),
        )
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert sorted(email for email, _ in sent) == sorted(
            [moderator.alert_email, admin.alert_email]
        )
        assert {user_id for _, user_id in sent} == {offender.id}

    def test_a_reporting_restriction_alerts_the_moderator_only(
        self, db_session, monkeypatch, moderator, offender
    ):
        self._admin(db_session)
        sent: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_reporting_restriction_alert",
            lambda email, user_id, expires_at: sent.append(email),
        )
        reporter = _make_user(db_session, "over-reporter@example.com")
        for index in range(settings.FALSE_REPORT_LIMIT - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.INVALID,
                target_id=f"dismissed-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.INVALID)

        assert sent == [moderator.alert_email]

    def test_an_ordinary_decision_alerts_nobody_about_a_restriction(
        self, db_session, monkeypatch, moderator, offender
    ):
        sent: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_sending_restriction_alert",
            lambda email, user_id, expires_at: sent.append(email),
        )
        reporter = _make_user(db_session, "reporter@example.com")
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert sent == []

    def test_a_failing_alert_does_not_undo_the_restriction(
        self, db_session, monkeypatch, moderator, offender
    ):
        """Same policy as every other notification here: mail never rolls back state."""

        def _explode(email, user_id, expires_at):
            raise RuntimeError("SMTP is down")

        monkeypatch.setattr(report_service, "send_sending_restriction_alert", _explode)
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        decided = _decide(db_session, report, moderator, ReportDecision.VALID)

        assert decided.decision == ReportDecision.VALID
        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING)


# ---------------------------------------------------------------------------
# §9.3 — every automatic measure is on the record
# ---------------------------------------------------------------------------


class TestAuditTrail:
    def test_applying_a_restriction_writes_an_audit_entry(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.USER_RESTRICTED)
            .one()
        )
        assert entry.actor_id == moderator.id
        assert entry.entity_type == "User"
        assert entry.entity_id == offender.id
        assert entry.details["restriction_type"] == RestrictionType.MESSAGING.value
        assert entry.details["automatic"] is True
        assert entry.details["report_count"] == settings.DM_BLOCK_AFTER_REPORTS

    def test_the_entry_carries_no_reported_content(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        post = _make_post(db_session, offender)
        report = _pending_report(db_session, reporter=reporter, post=post)

        _decide(db_session, report, moderator, ReportDecision.VALID)

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.USER_RESTRICTED)
            .one()
        )
        assert post.content not in str(entry.details)
        assert NOTE not in str(entry.details)

    def test_no_entry_when_no_threshold_is_crossed(
        self, db_session, moderator, offender
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.USER_RESTRICTED)
            .count()
            == 0
        )


# ---------------------------------------------------------------------------
# "אין דליפת תוכן הודעה ללוגים, stack traces או הודעות שגיאה"
# ---------------------------------------------------------------------------


class TestNoContentLeak:
    async def test_a_refused_send_does_not_log_the_message(
        self, client, db_session, as_user, pair, caplog
    ):
        sender, recipient = pair
        _restrict(db_session, sender)
        as_user(sender)
        secret = "טקסט פרטי שאסור שיופיע בלוג"

        with caplog.at_level(logging.DEBUG):
            response = await client.post(
                MESSAGES_BASE,
                json={"recipient_id": recipient.id, "content": secret},
            )

        assert secret not in caplog.text
        assert secret not in response.text

    def test_applying_a_restriction_does_not_log_the_reported_content(
        self, db_session, moderator, offender, caplog
    ):
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                target_id=f"old-{index}",
            )
        post = _make_post(db_session, offender)
        report = _pending_report(db_session, reporter=reporter, post=post)

        with caplog.at_level(logging.DEBUG):
            _decide(db_session, report, moderator, ReportDecision.VALID)

        assert post.content not in caplog.text
        assert NOTE not in caplog.text


# ---------------------------------------------------------------------------
# "הספים נכתבים כקונפיגורציה ולא כמספרים קשיחים"
# ---------------------------------------------------------------------------


class TestThresholdsAreConfiguration:
    def test_retuning_the_upheld_threshold_changes_when_it_fires(
        self, db_session, monkeypatch, moderator, offender
    ):
        monkeypatch.setattr(settings, "DM_BLOCK_AFTER_REPORTS", 2)
        reporter = _make_user(db_session, "reporter@example.com")
        _decided_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.VALID,
            target_id="old-0",
        )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        restriction = _restriction_for(db_session, offender, RestrictionType.MESSAGING)
        assert restriction is not None
        assert restriction.report_count == 2

    def test_retuning_the_duration_changes_the_end_date(
        self, db_session, monkeypatch, moderator, offender
    ):
        monkeypatch.setattr(settings, "DM_BLOCK_AFTER_REPORTS", 1)
        monkeypatch.setattr(settings, "DM_BLOCK_HOURS", 2)
        reporter = _make_user(db_session, "reporter@example.com")
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        restriction = _restriction_for(db_session, offender, RestrictionType.MESSAGING)
        expected = _now() + timedelta(hours=2)
        assert abs((restriction.expires_at - expected).total_seconds()) < 60

    def test_retuning_the_window_changes_what_counts(
        self, db_session, monkeypatch, moderator, offender
    ):
        monkeypatch.setattr(settings, "DM_BLOCK_DAYS_WINDOW", 1)
        reporter = _make_user(db_session, "reporter@example.com")
        for index in range(settings.DM_BLOCK_AFTER_REPORTS - 1):
            _decided_report(
                db_session,
                reporter=reporter,
                reported_user=offender,
                decision=ReportDecision.VALID,
                decided_at=_now() - timedelta(days=3),
                target_id=f"old-{index}",
            )
        report = _pending_report(
            db_session, reporter=reporter, post=_make_post(db_session, offender)
        )

        _decide(db_session, report, moderator, ReportDecision.VALID)

        assert _restriction_for(db_session, offender, RestrictionType.MESSAGING) is None

    def test_retuning_the_daily_allowance_changes_what_is_refused(
        self, db_session, monkeypatch, offender
    ):
        monkeypatch.setattr(settings, "RESTRICTED_REPORTS_PER_DAY", 1)
        reporter = _make_user(db_session, "reporter@example.com")
        _restrict(db_session, reporter, RestrictionType.REPORTING)
        _decided_report(
            db_session,
            reporter=reporter,
            reported_user=offender,
            decision=ReportDecision.INVALID,
            target_id="today-0",
        )

        with pytest.raises(HTTPException) as exc:
            restriction_service.assert_may_file_report(db_session, reporter)

        assert exc.value.status_code == 429

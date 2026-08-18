"""
Integration tests for the moderator's report endpoints: the pending queue,
a single report, the decision, and the history of past decisions.
"""

import pytest

from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    PostStatus,
    ReportDecision,
    ReportReason,
    ReportTargetType,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.user import User

BASE = "/api/v1/moderator"

WIDOWER_HASIDIC_CELL = {"group": UserType.WIDOWER, "sector": Sector.HASIDIC}


@pytest.fixture
def as_user():
    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


def _make_post(
    db_session, author: User, status: PostStatus = PostStatus.VISIBLE
) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="כותרת",
        content="תוכן ההודעה שדווחה",
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
        status=status,
    )
    db_session.add(post)
    db_session.commit()
    return post


def _file_report(db_session, post: ForumPost, reporter: User) -> Report:
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


class TestListPendingReports:
    async def test_returns_only_reports_in_moderators_cell(
        self, client, make_user, as_user, db_session
    ):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        moderator.moderator_cells = [WIDOWER_HASIDIC_CELL]
        db_session.commit()
        as_user(moderator)

        in_cell_author = make_user(
            "in-cell@example.com", user_type=UserType.WIDOWER, sector=Sector.HASIDIC
        )
        other_cell_author = make_user(
            "other-cell@example.com", user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        reporter = make_user("reporter@example.com")

        in_cell_post = _make_post(db_session, in_cell_author)
        other_cell_post = _make_post(db_session, other_cell_author)
        in_cell_report = _file_report(db_session, in_cell_post, reporter)
        _file_report(db_session, other_cell_post, reporter)

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == in_cell_report.id
        assert body["items"][0]["content_text"] == in_cell_post.content
        assert body["items"][0]["report_count"] == 1

    async def test_empty_list_when_no_cells_assigned(
        self, client, make_user, as_user, db_session
    ):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        as_user(moderator)

        author = make_user(
            "author@example.com", user_type=UserType.WIDOWER, sector=Sector.HASIDIC
        )
        reporter = make_user("reporter@example.com")
        post = _make_post(db_session, author)
        _file_report(db_session, post, reporter)

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 200
        assert response.json() == {"items": [], "total": 0, "pending_count": 0}

    async def test_admin_sees_reports_across_all_cells(
        self, client, make_user, as_user, db_session
    ):
        admin = make_user("admin@example.com", role=UserRole.ADMIN)
        as_user(admin)

        author_a = make_user(
            "author-a@example.com", user_type=UserType.WIDOWER, sector=Sector.HASIDIC
        )
        author_b = make_user(
            "author-b@example.com", user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        reporter = make_user("reporter@example.com")
        report_a = _file_report(db_session, _make_post(db_session, author_a), reporter)
        report_b = _file_report(db_session, _make_post(db_session, author_b), reporter)

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 200
        ids = {item["id"] for item in response.json()["items"]}
        assert ids == {report_a.id, report_b.id}

    async def test_regular_user_forbidden(self, client, make_user, as_user):
        user = make_user("user@example.com", role=UserRole.USER)
        as_user(user)

        response = await client.get(f"{BASE}/reports")

        assert response.status_code == 403


class TestGetReport:
    async def test_moderator_can_view_report_in_their_cell(
        self, client, make_user, as_user, db_session
    ):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        moderator.moderator_cells = [WIDOWER_HASIDIC_CELL]
        db_session.commit()
        as_user(moderator)

        author = make_user(
            "author@example.com", user_type=UserType.WIDOWER, sector=Sector.HASIDIC
        )
        reporter = make_user("reporter@example.com")
        post = _make_post(db_session, author)
        report = _file_report(db_session, post, reporter)

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == report.id
        assert body["content_title"] == post.title

    async def test_moderator_forbidden_outside_their_cell(
        self, client, make_user, as_user, db_session
    ):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        moderator.moderator_cells = [WIDOWER_HASIDIC_CELL]
        db_session.commit()
        as_user(moderator)

        author = make_user(
            "author@example.com", user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        reporter = make_user("reporter@example.com")
        post = _make_post(db_session, author)
        report = _file_report(db_session, post, reporter)

        response = await client.get(f"{BASE}/reports/{report.id}")

        assert response.status_code == 403

    async def test_404_for_nonexistent_report(
        self, client, make_user, as_user, db_session
    ):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        moderator.moderator_cells = [WIDOWER_HASIDIC_CELL]
        db_session.commit()
        as_user(moderator)

        response = await client.get(f"{BASE}/reports/nonexistent-id")

        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /moderator/reports/{id}/decide  (ABF-105)
# ---------------------------------------------------------------------------


def _make_moderator(db_session, make_user) -> User:
    moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
    moderator.moderator_cells = [WIDOWER_HASIDIC_CELL]
    db_session.commit()
    return moderator


def _make_reported_post(
    db_session, make_user, status: PostStatus = PostStatus.VISIBLE
) -> tuple[ForumPost, Report]:
    """A post by an author inside WIDOWER_HASIDIC_CELL, with one report on it."""
    author = make_user(
        "author@example.com", user_type=UserType.WIDOWER, sector=Sector.HASIDIC
    )
    reporter = make_user("reporter@example.com")
    post = _make_post(db_session, author, status=status)
    return post, _file_report(db_session, post, reporter)


def _decide_body(decision: ReportDecision, note: str = "נבדק מול כללי הקהילה") -> dict:
    return {"decision": decision.value, "note": note}


class TestDecideReport:
    async def test_valid_decision_deletes_the_post_and_records_the_decision(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        post, report = _make_reported_post(db_session, make_user)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID, note="תוכן פוגעני"),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == ReportDecision.VALID.value
        assert body["moderator_id"] == moderator.id
        assert body["moderator_note"] == "תוכן פוגעני"
        assert body["decided_at"] is not None
        db_session.refresh(post)
        assert post.status == PostStatus.DELETED

    async def test_invalid_decision_restores_an_auto_hidden_post(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        post, report = _make_reported_post(
            db_session, make_user, status=PostStatus.HIDDEN
        )

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.INVALID),
        )

        assert response.status_code == 200
        db_session.refresh(post)
        assert post.status == PostStatus.VISIBLE

    async def test_decided_report_is_gone_from_the_pending_list(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        _, report = _make_reported_post(db_session, make_user)

        await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )
        response = await client.get(f"{BASE}/reports")

        assert response.json()["items"] == []

    async def test_note_is_required(self, client, make_user, as_user, db_session):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        _, report = _make_reported_post(db_session, make_user)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json={"decision": ReportDecision.VALID.value},
        )

        assert response.status_code == 422

    async def test_pending_is_not_an_acceptable_decision(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        _, report = _make_reported_post(db_session, make_user)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.PENDING),
        )

        assert response.status_code == 422

    async def test_deciding_twice_conflicts(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        _, report = _make_reported_post(db_session, make_user)
        await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.INVALID),
        )

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        assert response.status_code == 409

    async def test_moderator_forbidden_outside_their_cell(
        self, client, make_user, as_user, db_session
    ):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        moderator.moderator_cells = [
            {"group": UserType.WIDOW, "sector": Sector.SEPHARDIC}
        ]
        db_session.commit()
        as_user(moderator)
        post, report = _make_reported_post(db_session, make_user)

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        assert response.status_code == 403
        db_session.refresh(post)
        assert post.status == PostStatus.VISIBLE

    async def test_regular_user_forbidden(self, client, make_user, as_user, db_session):
        _make_moderator(db_session, make_user)
        _, report = _make_reported_post(db_session, make_user)
        as_user(make_user("intruder@example.com", role=UserRole.USER))

        response = await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET /moderator/reports/history  (ABF-105)
# ---------------------------------------------------------------------------


class TestReportHistory:
    async def test_lists_reports_this_moderators_cells_already_decided(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        post, report = _make_reported_post(db_session, make_user)
        await client.post(
            f"{BASE}/reports/{report.id}/decide",
            json=_decide_body(ReportDecision.VALID, note="תוכן פוגעני"),
        )

        response = await client.get(f"{BASE}/reports/history")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert body["page"] == 1
        item = body["items"][0]
        assert item["id"] == report.id
        assert item["decision"] == ReportDecision.VALID.value
        assert item["moderator_note"] == "תוכן פוגעני"
        # The content stays readable in history – it is the record of what
        # was decided, even once the post itself is deleted.
        assert item["content_title"] == post.title
        assert item["content_status"] == PostStatus.DELETED.value

    async def test_pending_reports_are_not_history(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        _make_reported_post(db_session, make_user)

        response = await client.get(f"{BASE}/reports/history")

        assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}

    async def test_history_is_scoped_to_the_moderators_cells(
        self, client, make_user, as_user, db_session
    ):
        admin = make_user("admin@example.com", role=UserRole.ADMIN)
        as_user(admin)
        other_author = make_user(
            "other@example.com", user_type=UserType.WIDOW, sector=Sector.SEPHARDIC
        )
        reporter = make_user("reporter@example.com")
        other_report = _file_report(
            db_session, _make_post(db_session, other_author), reporter
        )
        await client.post(
            f"{BASE}/reports/{other_report.id}/decide",
            json=_decide_body(ReportDecision.VALID),
        )

        as_user(_make_moderator(db_session, make_user))
        response = await client.get(f"{BASE}/reports/history")

        assert response.json()["total"] == 0

    async def test_paginates(self, client, make_user, as_user, db_session):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        author = make_user(
            "author@example.com", user_type=UserType.WIDOWER, sector=Sector.HASIDIC
        )
        for index in range(3):
            reporter = make_user(f"reporter-{index}@example.com")
            report = _file_report(db_session, _make_post(db_session, author), reporter)
            await client.post(
                f"{BASE}/reports/{report.id}/decide",
                json=_decide_body(ReportDecision.INVALID),
            )

        response = await client.get(f"{BASE}/reports/history?page=2&page_size=2")

        body = response.json()
        assert body["total"] == 3
        assert body["page"] == 2
        assert len(body["items"]) == 1

    async def test_history_is_not_mistaken_for_a_report_id(
        self, client, make_user, as_user, db_session
    ):
        """
        Regression test: /reports/history must be declared before
        /reports/{report_id}, or FastAPI matches "history" as an id and
        answers 404 from the wrong route.
        """
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)

        response = await client.get(f"{BASE}/reports/history")

        assert response.status_code == 200
        assert "items" in response.json()

    async def test_regular_user_forbidden(self, client, make_user, as_user):
        as_user(make_user("user@example.com", role=UserRole.USER))

        response = await client.get(f"{BASE}/reports/history")

        assert response.status_code == 403


# ---------------------------------------------------------------------------
# GET  /moderator/users/{id}/card     (ABF-100)
# POST /moderator/users/{id}/suspend  (ABF-100)
# ---------------------------------------------------------------------------


def _make_member(db_session, make_user, email: str = "member@example.com") -> User:
    """An active user inside WIDOWER_HASIDIC_CELL – the subject of a card."""
    user = make_user(
        email,
        user_type=UserType.WIDOWER,
        sector=Sector.HASIDIC,
        account_status=AccountStatus.ACTIVE,
    )
    db_session.commit()
    return user


def _suspend_body(hours: int = 48, reason: str = "התנהגות פוגענית חוזרת") -> dict:
    return {"hours": hours, "reason": reason}


class TestGetUserCard:
    async def test_returns_the_counts_behind_the_moderators_judgement(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        member = _make_member(db_session, make_user)
        reporter = make_user("reporter@example.com")
        post = _make_post(db_session, member)
        report = _file_report(db_session, post, reporter)
        report.decision = ReportDecision.VALID
        db_session.commit()

        response = await client.get(f"{BASE}/users/{member.id}/card")

        assert response.status_code == 200
        body = response.json()
        assert body["id"] == member.id
        assert body["reports_against_total"] == 1
        assert body["reports_against_valid"] == 1
        assert body["reports_against_invalid"] == 0
        assert body["reports_filed_total"] == 0
        assert body["false_reports_filed"] == 0
        assert body["is_suspended"] is False
        assert body["suspended_until"] is None

    async def test_the_card_carries_no_contact_details(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        member = _make_member(db_session, make_user)

        response = await client.get(f"{BASE}/users/{member.id}/card")

        body = response.json()
        assert not {"email", "phone", "id_number"} & set(body)

    async def test_moderator_forbidden_outside_their_cell(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        elsewhere = make_user(
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.ACTIVE,
        )

        response = await client.get(f"{BASE}/users/{elsewhere.id}/card")

        assert response.status_code == 403

    async def test_404_for_nonexistent_user(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))

        response = await client.get(f"{BASE}/users/no-such-user/card")

        assert response.status_code == 404

    async def test_regular_user_forbidden(self, client, make_user, as_user, db_session):
        member = _make_member(db_session, make_user)
        as_user(make_user("intruder@example.com", role=UserRole.USER))

        response = await client.get(f"{BASE}/users/{member.id}/card")

        assert response.status_code == 403


class TestSuspendUserFromTheCard:
    async def test_suspends_the_user_and_answers_with_the_updated_card(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        member = _make_member(db_session, make_user)

        response = await client.post(
            f"{BASE}/users/{member.id}/suspend", json=_suspend_body(hours=48)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["is_suspended"] is True
        assert body["suspended_until"] is not None
        assert body["account_status"] == AccountStatus.SUSPENDED.value
        db_session.refresh(member)
        assert member.account_status == AccountStatus.SUSPENDED

    async def test_writes_an_audit_entry(self, client, make_user, as_user, db_session):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        member = _make_member(db_session, make_user)

        await client.post(f"{BASE}/users/{member.id}/suspend", json=_suspend_body())

        entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.USER_SUSPENDED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].actor_id == moderator.id
        assert entries[0].entity_id == member.id

    async def test_moderator_forbidden_outside_their_cell(
        self, client, make_user, as_user, db_session
    ):
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        elsewhere = make_user(
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.ACTIVE,
        )

        response = await client.post(
            f"{BASE}/users/{elsewhere.id}/suspend", json=_suspend_body()
        )

        assert response.status_code == 403
        db_session.refresh(elsewhere)
        assert elsewhere.account_status == AccountStatus.ACTIVE

    async def test_reason_is_required(self, client, make_user, as_user, db_session):
        as_user(_make_moderator(db_session, make_user))
        member = _make_member(db_session, make_user)

        response = await client.post(
            f"{BASE}/users/{member.id}/suspend", json={"hours": 48}
        )

        assert response.status_code == 422

    async def test_hours_must_be_positive(self, client, make_user, as_user, db_session):
        as_user(_make_moderator(db_session, make_user))
        member = _make_member(db_session, make_user)

        response = await client.post(
            f"{BASE}/users/{member.id}/suspend", json=_suspend_body(hours=0)
        )

        assert response.status_code == 422

    async def test_404_for_nonexistent_user(
        self, client, make_user, as_user, db_session
    ):
        as_user(_make_moderator(db_session, make_user))

        response = await client.post(
            f"{BASE}/users/no-such-user/suspend", json=_suspend_body()
        )

        assert response.status_code == 404

    async def test_regular_user_forbidden(self, client, make_user, as_user, db_session):
        member = _make_member(db_session, make_user)
        as_user(make_user("intruder@example.com", role=UserRole.USER))

        response = await client.post(
            f"{BASE}/users/{member.id}/suspend", json=_suspend_body()
        )

        assert response.status_code == 403
        db_session.refresh(member)
        assert member.account_status == AccountStatus.ACTIVE


class TestTheCardEndToEnd:
    async def test_three_valid_reports_then_a_48_hour_suspension(
        self, client, make_user, as_user, db_session
    ):
        """
        The walkthrough this ticket is accepted on: a moderator opens the card
        of a user with three upheld reports against them, reads the counts,
        and suspends the account for 48 hours with a reason.
        """
        moderator = _make_moderator(db_session, make_user)
        as_user(moderator)
        member = _make_member(db_session, make_user)
        for index in range(3):
            reporter = make_user(f"reporter-{index}@example.com")
            report = _file_report(db_session, _make_post(db_session, member), reporter)
            report.decision = ReportDecision.VALID
        db_session.commit()

        card = (await client.get(f"{BASE}/users/{member.id}/card")).json()

        assert card["reports_against_total"] == 3
        assert card["reports_against_valid"] == 3
        assert card["is_suspended"] is False

        response = await client.post(
            f"{BASE}/users/{member.id}/suspend",
            json=_suspend_body(hours=48, reason="שלושה דיווחים מוצדקים"),
        )

        assert response.status_code == 200
        db_session.refresh(member)
        assert member.account_status == AccountStatus.SUSPENDED
        assert member.suspended_until is not None
        assert response.json()["reports_against_valid"] == 3

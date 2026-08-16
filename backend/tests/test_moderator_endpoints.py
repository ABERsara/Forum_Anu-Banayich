"""
Integration tests for GET /moderator/reports and GET /moderator/reports/{id}.
"""

import pytest

from app.core.constants import (
    GroupVisibility,
    ReportReason,
    ReportTargetType,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
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


def _make_post(db_session, author: User) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="כותרת",
        content="תוכן ההודעה שדווחה",
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
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

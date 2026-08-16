"""
Unit tests for report_service.file_report() and its escalation logic.
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import (
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
from app.models.forum import ForumPost
from app.models.user import User
from app.schemas.report import ReportCreate
from app.services import report_service


def _make_user(
    db_session: Session,
    email: str,
    role: UserRole = UserRole.USER,
    alert_email: str | None = None,
    user_type: UserType | None = None,
    sector: Sector | None = None,
    moderator_cells: list[dict[str, str]] | None = None,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        alert_email=alert_email,
        user_type=user_type,
        sector=sector,
        moderator_cells=moderator_cells,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_post(db_session: Session, author: User) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="Title",
        content="Content that was reported for being harassing in nature",
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
    )
    db_session.add(post)
    db_session.commit()
    return post


def _report_data(
    target_id: str, target_type: ReportTargetType = ReportTargetType.FORUM_POST
) -> ReportCreate:
    return ReportCreate(
        target_type=target_type,
        target_id=target_id,
        reason=ReportReason.HARASSMENT,
        description="test description",
    )


# Default cell used across tests that need a moderator's moderator_cells to
# match a post author's (user_type, sector) — spec §4.3.
WIDOWER_HASIDIC_CELL = {"group": UserType.WIDOWER, "sector": Sector.HASIDIC}


class TestFileReportCreatesReport:
    def test_creates_report_with_correct_fields(self, db_session: Session) -> None:
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        assert report.reporter_id == reporter.id
        assert report.target_type == ReportTargetType.FORUM_POST
        assert report.target_id == post.id
        assert report.reported_user_id == author.id
        assert report.reason == ReportReason.HARASSMENT
        assert report.description == "test description"
        assert report.decision == ReportDecision.PENDING

    def test_increments_report_count(self, db_session: Session) -> None:
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        db_session.refresh(post)
        assert post.report_count == 1


class TestFileReportUnsupportedTargetType:
    def test_direct_message_rejected(self, db_session: Session) -> None:
        reporter = _make_user(db_session, "reporter@example.com")

        with pytest.raises(HTTPException) as exc_info:
            report_service.file_report(
                db_session,
                _report_data("some-id", target_type=ReportTargetType.DIRECT_MESSAGE),
                reporter,
            )

        assert exc_info.value.status_code == 400

    def test_professional_query_rejected(self, db_session: Session) -> None:
        reporter = _make_user(db_session, "reporter@example.com")

        with pytest.raises(HTTPException) as exc_info:
            report_service.file_report(
                db_session,
                _report_data(
                    "some-id", target_type=ReportTargetType.PROFESSIONAL_QUERY
                ),
                reporter,
            )

        assert exc_info.value.status_code == 400


class TestFileReportTargetNotFound:
    def test_nonexistent_post_returns_404(self, db_session: Session) -> None:
        reporter = _make_user(db_session, "reporter@example.com")

        with pytest.raises(HTTPException) as exc_info:
            report_service.file_report(
                db_session, _report_data("nonexistent-id"), reporter
            )

        assert exc_info.value.status_code == 404


class TestFileReportDuplicateBlocked:
    def test_same_reporter_twice_raises_409(self, db_session: Session) -> None:
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        with pytest.raises(HTTPException) as exc_info:
            report_service.file_report(db_session, _report_data(post.id), reporter)

        assert exc_info.value.status_code == 409

    def test_different_reporters_both_succeed(self, db_session: Session) -> None:
        author = _make_user(db_session, "author@example.com")
        reporter1 = _make_user(db_session, "reporter1@example.com")
        reporter2 = _make_user(db_session, "reporter2@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter1)
        report_service.file_report(db_session, _report_data(post.id), reporter2)

        db_session.refresh(post)
        assert post.report_count == 2


class TestFileReportFirstReportEscalation:
    def test_sends_moderator_alert(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(
                (email, report_id, content_preview)
            ),
        )
        _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            alert_email="mod-alerts@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        assert calls == [("mod-alerts@example.com", report.id, post.content[:100])]

    def test_post_stays_visible(self, db_session: Session) -> None:
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        db_session.refresh(post)
        assert post.status == PostStatus.VISIBLE


class TestFileReportSecondReportEscalation:
    def test_hides_post(self, db_session: Session) -> None:
        author = _make_user(db_session, "author@example.com")
        reporter1 = _make_user(db_session, "reporter1@example.com")
        reporter2 = _make_user(db_session, "reporter2@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter1)
        report_service.file_report(db_session, _report_data(post.id), reporter2)

        db_session.refresh(post)
        assert post.status == PostStatus.HIDDEN

    def test_sends_urgent_alert(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        monkeypatch.setattr(
            report_service,
            "send_urgent_moderator_alert",
            lambda email, report_id: calls.append((email, report_id)),
        )
        _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            alert_email="mod-alerts@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter1 = _make_user(db_session, "reporter1@example.com")
        reporter2 = _make_user(db_session, "reporter2@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter1)
        report = report_service.file_report(
            db_session, _report_data(post.id), reporter2
        )

        assert calls == [("mod-alerts@example.com", report.id)]


class TestFileReportThirdPlusReportEscalation:
    def test_third_and_fourth_report_send_urgent_alert_again(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = []
        monkeypatch.setattr(
            report_service,
            "send_urgent_moderator_alert",
            lambda email, report_id: calls.append(report_id),
        )
        _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            alert_email="mod-alerts@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        post = _make_post(db_session, author)
        reporters = [
            _make_user(db_session, f"reporter{i}@example.com") for i in range(4)
        ]

        reports = [
            report_service.file_report(db_session, _report_data(post.id), reporter)
            for reporter in reporters
        ]

        # report_count reaches 2, 3, 4 on these calls -> urgent alert fires each time
        assert calls == [reports[1].id, reports[2].id, reports[3].id]


class TestFileReportModeratorBroadcast:
    def test_broadcasts_to_all_moderators_covering_the_authors_cell(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(email),
        )
        _make_user(
            db_session,
            "mod1@example.com",
            role=UserRole.MODERATOR,
            alert_email="alert1@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        _make_user(
            db_session,
            "mod2@example.com",
            role=UserRole.MODERATOR,
            alert_email="alert2@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        _make_user(db_session, "user@example.com")  # not a moderator
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert sorted(calls) == ["alert1@example.com", "alert2@example.com"]

    def test_skips_moderators_whose_cells_dont_cover_the_author(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(email),
        )
        _make_user(
            db_session,
            "mod-widower-hasidic@example.com",
            role=UserRole.MODERATOR,
            alert_email="alert1@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        _make_user(
            db_session,
            "mod-widow-litvish@example.com",
            role=UserRole.MODERATOR,
            alert_email="alert2@example.com",
            moderator_cells=[{"group": UserType.WIDOW, "sector": Sector.LITVISH}],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert calls == ["alert1@example.com"]

    def test_falls_back_to_email_when_alert_email_missing(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(email),
        )
        _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            alert_email=None,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert calls == ["mod@example.com"]

    def test_no_alert_when_author_has_no_cell(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An author with no user_type/sector (e.g. incomplete profile) matches no cell."""
        calls: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(email),
        )
        _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            alert_email="alert@example.com",
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert calls == []


class TestGetPendingReports:
    def test_empty_when_moderator_has_no_cells(self, db_session: Session) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)
        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert report_service.get_pending_reports(db_session, moderator) == []

    def test_returns_only_reports_in_the_moderators_cell(
        self, db_session: Session
    ) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        in_cell_author = _make_user(
            db_session,
            "in-cell-author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        other_cell_author = _make_user(
            db_session,
            "other-cell-author@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        reporter1 = _make_user(db_session, "reporter1@example.com")
        reporter2 = _make_user(db_session, "reporter2@example.com")
        in_cell_post = _make_post(db_session, in_cell_author)
        other_cell_post = _make_post(db_session, other_cell_author)

        in_cell_report = report_service.file_report(
            db_session, _report_data(in_cell_post.id), reporter1
        )
        report_service.file_report(
            db_session, _report_data(other_cell_post.id), reporter2
        )

        results = report_service.get_pending_reports(db_session, moderator)

        assert [r.id for r in results] == [in_cell_report.id]

    def test_admin_sees_all_pending_reports_unscoped(self, db_session: Session) -> None:
        """Admin has no moderator_cells but must still see every cell's reports."""
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        author_a = _make_user(
            db_session,
            "author-a@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        author_b = _make_user(
            db_session,
            "author-b@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        reporter1 = _make_user(db_session, "reporter1@example.com")
        reporter2 = _make_user(db_session, "reporter2@example.com")
        post_a = _make_post(db_session, author_a)
        post_b = _make_post(db_session, author_b)

        report_a = report_service.file_report(
            db_session, _report_data(post_a.id), reporter1
        )
        report_b = report_service.file_report(
            db_session, _report_data(post_b.id), reporter2
        )

        results = report_service.get_pending_reports(db_session, admin)

        assert {r.id for r in results} == {report_a.id, report_b.id}

    def test_sorted_by_report_count_descending(self, db_session: Session) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporters = [
            _make_user(db_session, f"reporter{i}@example.com") for i in range(3)
        ]
        less_reported_post = _make_post(db_session, author)
        more_reported_post = _make_post(db_session, author)

        less_report = report_service.file_report(
            db_session, _report_data(less_reported_post.id), reporters[0]
        )
        more_report_a = report_service.file_report(
            db_session, _report_data(more_reported_post.id), reporters[1]
        )
        more_report_b = report_service.file_report(
            db_session, _report_data(more_reported_post.id), reporters[2]
        )

        results = report_service.get_pending_reports(db_session, moderator)

        # Both reports on more_reported_post (report_count=2) sort before the
        # single report on less_reported_post (report_count=1); order between
        # the tied pair is unspecified.
        assert {r.id for r in results[:2]} == {more_report_a.id, more_report_b.id}
        assert results[2].id == less_report.id

    def test_excludes_already_decided_reports(self, db_session: Session) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)
        report = report_service.file_report(db_session, _report_data(post.id), reporter)
        report.decision = ReportDecision.VALID
        db_session.commit()

        assert report_service.get_pending_reports(db_session, moderator) == []


class TestGetReportForModerator:
    def test_moderator_can_view_report_in_their_cell(self, db_session: Session) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)
        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        result = report_service.get_report_for_moderator(
            db_session, report.id, moderator
        )

        assert result.id == report.id

    def test_moderator_cannot_view_report_outside_their_cell(
        self, db_session: Session
    ) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)
        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        with pytest.raises(HTTPException) as exc_info:
            report_service.get_report_for_moderator(db_session, report.id, moderator)

        assert exc_info.value.status_code == 403

    def test_moderator_with_no_cells_cannot_view_any_report(
        self, db_session: Session
    ) -> None:
        """
        Regression test: an empty moderator_cells list must deny access to
        every report, not grant it. or_() with no clauses is a SQL no-op
        (matches every row) rather than "match none", so this has to be
        special-cased rather than left to the filter — see _cell_match_filter.
        """
        moderator = _make_user(
            db_session, "mod@example.com", role=UserRole.MODERATOR, moderator_cells=[]
        )
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)
        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        with pytest.raises(HTTPException) as exc_info:
            report_service.get_report_for_moderator(db_session, report.id, moderator)

        assert exc_info.value.status_code == 403

    def test_admin_can_view_any_report(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)
        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        result = report_service.get_report_for_moderator(db_session, report.id, admin)

        assert result.id == report.id

    def test_404_for_nonexistent_report(self, db_session: Session) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[WIDOWER_HASIDIC_CELL],
        )

        with pytest.raises(HTTPException) as exc_info:
            report_service.get_report_for_moderator(
                db_session, "nonexistent-id", moderator
            )

        assert exc_info.value.status_code == 404

"""
Unit tests for report_service: filing a report and its escalation logic,
the moderator's queue, and deciding on a report.
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

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
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.report import ReportCreate, ReportDecideRequest
from app.schemas.user import SuspendUserRequest
from app.services import forum_service, report_service, user_service


def _make_user(
    db_session: Session,
    email: str,
    role: UserRole = UserRole.USER,
    alert_email: str | None = None,
    user_type: UserType | None = None,
    sector: Sector | None = None,
    moderator_cells: list[dict[str, str]] | None = None,
    account_status: AccountStatus = AccountStatus.ACTIVE,
) -> User:
    # ACTIVE by default: everyone in these scenarios is a live account, and
    # alerts only go to moderators still on the roster (see
    # report_service._moderator_emails_for). Overridable, because the user
    # card has to report a suspended account as suspended.
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
        account_status=account_status,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_post(
    db_session: Session,
    author: User,
    status: PostStatus = PostStatus.VISIBLE,
) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="Title",
        content="Content that was reported for being harassing in nature",
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
        status=status,
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

        assert [r.id for r, _ in results] == [in_cell_report.id]

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

        assert {r.id for r, _ in results} == {report_a.id, report_b.id}

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
        assert {r.id for r, _ in results[:2]} == {more_report_a.id, more_report_b.id}
        assert results[2][0].id == less_report.id

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

        result_report, result_post = report_service.get_report_for_moderator(
            db_session, report.id, moderator
        )

        assert result_report.id == report.id
        assert result_post.id == post.id

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

        result_report, result_post = report_service.get_report_for_moderator(
            db_session, report.id, admin
        )

        assert result_report.id == report.id
        assert result_post.id == post.id

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


# ---------------------------------------------------------------------------
# decide_report() – the moderator's decision (ABF-105)
# ---------------------------------------------------------------------------


def _decision(
    decision: ReportDecision, note: str = "נבדק מול כללי הקהילה"
) -> ReportDecideRequest:
    return ReportDecideRequest(decision=decision, note=note)


def _make_moderator(db_session: Session) -> User:
    return _make_user(
        db_session,
        "mod@example.com",
        role=UserRole.MODERATOR,
        moderator_cells=[WIDOWER_HASIDIC_CELL],
    )


def _make_reported_post(
    db_session: Session,
    status: PostStatus = PostStatus.VISIBLE,
) -> tuple[ForumPost, Report]:
    """A post by an author in the moderator's cell, with one report filed on it."""
    author = _make_user(
        db_session,
        "author@example.com",
        user_type=UserType.WIDOWER,
        sector=Sector.HASIDIC,
    )
    reporter = _make_user(db_session, "reporter@example.com")
    post = _make_post(db_session, author, status=status)
    report = report_service.file_report(db_session, _report_data(post.id), reporter)
    return post, report


class TestDecideReportRecordsTheDecision:
    def test_records_decision_moderator_note_and_timestamp(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        _, report = _make_reported_post(db_session)

        result = report_service.decide_report(
            db_session,
            report.id,
            _decision(ReportDecision.VALID, note="תוכן פוגעני, נמחק"),
            moderator,
        )

        assert result.decision == ReportDecision.VALID
        assert result.moderator_id == moderator.id
        assert result.moderator_note == "תוכן פוגעני, נמחק"
        assert result.decided_at is not None

    def test_decided_report_leaves_the_pending_queue(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        _, report = _make_reported_post(db_session)
        assert report_service.get_pending_reports(db_session, moderator) != []

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        assert report_service.get_pending_reports(db_session, moderator) == []

    def test_writes_an_audit_entry_without_the_note_text(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session)

        report_service.decide_report(
            db_session,
            report.id,
            _decision(ReportDecision.VALID, note="הערה פנימית רגישה"),
            moderator,
        )

        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.REPORT_DECIDED)
            .one()
        )
        assert entry.actor_id == moderator.id
        assert entry.entity_type == "Report"
        assert entry.entity_id == report.id
        assert entry.details == {
            "decision": "valid",
            "content_action": "deleted",
            "target_type": "forum_post",
            "target_id": post.id,
            "reported_user_id": post.author_id,
        }
        # The note is free text about a bereaved user – it belongs on the
        # report row, never in the audit log (CONTRIBUTING §4, "אין PII בלוגים").
        assert "הערה פנימית רגישה" not in str(entry.details)


class TestDecideReportValid:
    def test_deletes_the_reported_post(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), moderator
        )

        db_session.refresh(post)
        assert post.status == PostStatus.DELETED

    def test_deleted_post_disappears_from_the_forum_list(
        self, db_session: Session
    ) -> None:
        """The proof the ticket asks for: the content is gone from the forum."""
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session)
        reader = _make_user(
            db_session,
            "reader@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )
        assert forum_service.get_posts(db_session, reader).total == 1

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), moderator
        )

        listing = forum_service.get_posts(db_session, reader)
        assert listing.total == 0
        assert post.id not in [item.id for item in listing.items]

    def test_notifies_the_author_that_their_content_was_removed(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            report_service,
            "send_content_removed_notification",
            lambda email, report_id: calls.append((email, report_id)),
        )
        moderator = _make_moderator(db_session)
        _, report = _make_reported_post(db_session)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), moderator
        )

        assert calls == [("author@example.com", report.id)]

    def test_a_failed_notification_does_not_undo_the_decision(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _explode(email: str, report_id: str) -> None:
            raise RuntimeError("SMTP is down")

        monkeypatch.setattr(
            report_service, "send_content_removed_notification", _explode
        )
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session)

        result = report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), moderator
        )

        assert result.decision == ReportDecision.VALID
        db_session.refresh(post)
        assert post.status == PostStatus.DELETED

    def test_deciding_on_an_already_deleted_post_is_recorded_as_such(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session, status=PostStatus.DELETED)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), moderator
        )

        db_session.refresh(post)
        assert post.status == PostStatus.DELETED
        entry = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.REPORT_DECIDED)
            .one()
        )
        assert entry.details is not None
        assert entry.details["content_action"] == "already_deleted"


class TestDecideReportInvalid:
    def test_restores_an_auto_hidden_post(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session, status=PostStatus.HIDDEN)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        db_session.refresh(post)
        assert post.status == PostStatus.VISIBLE

    def test_restored_post_reappears_in_the_forum_list(
        self, db_session: Session
    ) -> None:
        """The second proof the ticket asks for: a hidden post comes back."""
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session, status=PostStatus.HIDDEN)
        reader = _make_user(
            db_session,
            "reader@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )
        assert forum_service.get_posts(db_session, reader).total == 0

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        listing = forum_service.get_posts(db_session, reader)
        assert [item.id for item in listing.items] == [post.id]

    def test_a_visible_post_is_left_alone(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        db_session.refresh(post)
        assert post.status == PostStatus.VISIBLE

    def test_a_deleted_post_is_not_republished(self, db_session: Session) -> None:
        """
        The author, or a moderator acting on other grounds, deleted the post.
        Dismissing this one report is not a mandate to bring it back.
        """
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session, status=PostStatus.DELETED)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        db_session.refresh(post)
        assert post.status == PostStatus.DELETED

    def test_does_not_notify_the_author(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str]] = []
        monkeypatch.setattr(
            report_service,
            "send_content_removed_notification",
            lambda email, report_id: calls.append((email, report_id)),
        )
        moderator = _make_moderator(db_session)
        _, report = _make_reported_post(db_session)

        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        assert calls == []


class TestDecideReportGuards:
    def test_second_decision_on_the_same_report_is_rejected(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        _, report = _make_reported_post(db_session)
        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.INVALID), moderator
        )

        with pytest.raises(HTTPException) as exc_info:
            report_service.decide_report(
                db_session, report.id, _decision(ReportDecision.VALID), moderator
            )

        assert exc_info.value.status_code == 409

    def test_moderator_cannot_decide_outside_their_cell(
        self, db_session: Session
    ) -> None:
        moderator = _make_user(
            db_session,
            "mod@example.com",
            role=UserRole.MODERATOR,
            moderator_cells=[{"group": UserType.WIDOW, "sector": Sector.SEPHARDIC}],
        )
        post, report = _make_reported_post(db_session)

        with pytest.raises(HTTPException) as exc_info:
            report_service.decide_report(
                db_session, report.id, _decision(ReportDecision.VALID), moderator
            )

        assert exc_info.value.status_code == 403
        db_session.refresh(post)
        assert post.status == PostStatus.VISIBLE

    def test_admin_can_decide_on_any_report(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        post, report = _make_reported_post(db_session)

        result = report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), admin
        )

        assert result.moderator_id == admin.id
        db_session.refresh(post)
        assert post.status == PostStatus.DELETED

    def test_nonexistent_report_is_404(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)

        with pytest.raises(HTTPException) as exc_info:
            report_service.decide_report(
                db_session, "nonexistent-id", _decision(ReportDecision.VALID), moderator
            )

        assert exc_info.value.status_code == 404


class TestReportDecideRequestValidation:
    def test_pending_is_not_a_decision(self) -> None:
        with pytest.raises(ValidationError):
            ReportDecideRequest(decision=ReportDecision.PENDING, note="הערה תקינה")

    def test_note_is_mandatory(self) -> None:
        with pytest.raises(ValidationError):
            ReportDecideRequest(decision=ReportDecision.VALID)  # type: ignore[call-arg]

    def test_blank_note_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReportDecideRequest(decision=ReportDecision.VALID, note="       ")

    def test_note_is_stored_trimmed(self) -> None:
        data = ReportDecideRequest(decision=ReportDecision.VALID, note="  הערה תקינה  ")

        assert data.note == "הערה תקינה"


# ---------------------------------------------------------------------------
# get_decided_reports() – the history tab (ABF-105)
# ---------------------------------------------------------------------------


class TestGetDecidedReports:
    def test_returns_reports_decided_in_the_moderators_cell(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        post, report = _make_reported_post(db_session)
        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), moderator
        )

        rows, total = report_service.get_decided_reports(db_session, moderator)

        assert total == 1
        assert [r.id for r, _ in rows] == [report.id]
        # The post comes back with its report, so the endpoint needs no
        # follow-up query to render the content that was decided on.
        assert [p.id for _, p in rows] == [post.id]

    def test_excludes_reports_still_awaiting_a_decision(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        _make_reported_post(db_session)

        reports, total = report_service.get_decided_reports(db_session, moderator)

        assert (reports, total) == ([], 0)

    def test_excludes_decisions_outside_the_moderators_cells(
        self, db_session: Session
    ) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        other_author = _make_user(
            db_session,
            "other@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        reporter = _make_user(db_session, "reporter@example.com")
        other_post = _make_post(db_session, other_author)
        other_report = report_service.file_report(
            db_session, _report_data(other_post.id), reporter
        )
        report_service.decide_report(
            db_session, other_report.id, _decision(ReportDecision.VALID), admin
        )
        moderator = _make_moderator(db_session)

        reports, total = report_service.get_decided_reports(db_session, moderator)

        assert (reports, total) == ([], 0)

    def test_moderator_with_no_cells_sees_nothing(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        _, report = _make_reported_post(db_session)
        report_service.decide_report(
            db_session, report.id, _decision(ReportDecision.VALID), admin
        )
        moderator = _make_user(
            db_session, "mod@example.com", role=UserRole.MODERATOR, moderator_cells=[]
        )

        reports, total = report_service.get_decided_reports(db_session, moderator)

        assert (reports, total) == ([], 0)

    def test_admin_sees_decisions_across_all_cells(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        _, in_cell = _make_reported_post(db_session)
        other_author = _make_user(
            db_session,
            "other@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        second_reporter = _make_user(db_session, "second-reporter@example.com")
        out_of_cell = report_service.file_report(
            db_session,
            _report_data(_make_post(db_session, other_author).id),
            second_reporter,
        )
        for report_id in (in_cell.id, out_of_cell.id):
            report_service.decide_report(
                db_session, report_id, _decision(ReportDecision.INVALID), admin
            )

        rows, total = report_service.get_decided_reports(db_session, admin)

        assert total == 2
        assert {r.id for r, _ in rows} == {in_cell.id, out_of_cell.id}

    def test_paginates_and_reports_the_full_total(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        author = _make_user(
            db_session,
            "author@example.com",
            user_type=UserType.WIDOWER,
            sector=Sector.HASIDIC,
        )
        for index in range(3):
            reporter = _make_user(db_session, f"reporter-{index}@example.com")
            report = report_service.file_report(
                db_session, _report_data(_make_post(db_session, author).id), reporter
            )
            report_service.decide_report(
                db_session, report.id, _decision(ReportDecision.INVALID), moderator
            )

        first_page, total = report_service.get_decided_reports(
            db_session, moderator, page=1, page_size=2
        )
        second_page, _ = report_service.get_decided_reports(
            db_session, moderator, page=2, page_size=2
        )

        assert total == 3
        assert len(first_page) == 2
        assert len(second_page) == 1
        # No row may show up on two pages – hence the id tiebreaker in the
        # ORDER BY, since these decisions can share a timestamp.
        assert {r.id for r, _ in first_page}.isdisjoint({r.id for r, _ in second_page})


# ---------------------------------------------------------------------------
# get_user_card() / suspend_user_for_moderator() – the user card (ABF-100)
# ---------------------------------------------------------------------------


def _card_user(db_session: Session, email: str = "member@example.com") -> User:
    """An active user inside the moderator's cell – the subject of a card."""
    return _make_user(
        db_session,
        email,
        user_type=UserType.WIDOWER,
        sector=Sector.HASIDIC,
        account_status=AccountStatus.ACTIVE,
    )


def _report_row(
    db_session: Session,
    reporter: User,
    reported_user: User,
    decision: ReportDecision = ReportDecision.PENDING,
    target_id: str = "some-post-id",
) -> Report:
    """
    A report row, written straight to the table.

    The card reads the reports table and nothing else, so these rows need no
    post behind them – and building them here rather than through
    file_report() + decide_report() keeps a counting test from depending on
    the deletion and the notifications those two perform.
    """
    report = Report(
        reporter_id=reporter.id,
        target_type=ReportTargetType.FORUM_POST,
        target_id=target_id,
        reported_user_id=reported_user.id,
        reason=ReportReason.HARASSMENT,
        decision=decision,
    )
    db_session.add(report)
    db_session.commit()
    return report


SUSPENSION_REASON = "התנהגות פוגענית חוזרת"


def _suspend_request(
    hours: int = 48, reason: str = SUSPENSION_REASON
) -> SuspendUserRequest:
    return SuspendUserRequest(hours=hours, reason=reason)


class TestGetUserCard:
    def test_counts_the_reports_against_the_user_by_decision(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)
        reporter = _make_user(db_session, "reporter@example.com")
        _report_row(db_session, reporter, member, ReportDecision.VALID)
        _report_row(db_session, reporter, member, ReportDecision.VALID)
        _report_row(db_session, reporter, member, ReportDecision.INVALID)
        _report_row(db_session, reporter, member, ReportDecision.PENDING)

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert card.reports_against_total == 4
        assert card.reports_against_valid == 2
        assert card.reports_against_invalid == 1

    def test_counts_the_false_reports_the_user_filed(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)
        other = _make_user(db_session, "other@example.com")
        _report_row(db_session, member, other, ReportDecision.INVALID)
        _report_row(db_session, member, other, ReportDecision.INVALID)
        _report_row(db_session, member, other, ReportDecision.VALID)

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert card.reports_filed_total == 3
        assert card.false_reports_filed == 2
        # Filing reports says nothing about having been reported.
        assert card.reports_against_total == 0

    def test_counts_reports_the_user_filed_outside_the_moderators_cells(
        self, db_session: Session
    ) -> None:
        """
        The counts describe the user, not the cell: a report this user filed
        about someone in another cell still belongs on their record.
        """
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
        )
        _report_row(db_session, member, elsewhere, ReportDecision.INVALID)

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert card.false_reports_filed == 1

    def test_a_user_with_no_history_counts_zero_across_the_board(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert card.reports_against_total == 0
        assert card.reports_against_valid == 0
        assert card.reports_against_invalid == 0
        assert card.reports_filed_total == 0
        assert card.false_reports_filed == 0

    def test_shows_who_the_user_is_and_where_they_belong(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert card.id == member.id
        assert card.first_name == member.first_name
        assert card.user_type == UserType.WIDOWER
        assert card.sector == Sector.HASIDIC
        assert card.account_status == AccountStatus.ACTIVE

    def test_carries_no_contact_details(self, db_session: Session) -> None:
        """
        A moderator moderates content. The card deliberately stops short of
        the email, phone and ID number UserAdminView carries for admins.
        """
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert not {"email", "phone", "id_number"} & set(card.model_dump())

    def test_shows_the_current_suspension(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)
        report_service.suspend_user_for_moderator(
            db_session, member.id, moderator, _suspend_request()
        )

        card = report_service.get_user_card(db_session, member.id, moderator)

        assert card.is_suspended is True
        assert card.suspended_until is not None
        assert card.account_status == AccountStatus.SUSPENDED

    def test_moderator_cannot_open_a_card_outside_their_cells(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.ACTIVE,
        )

        with pytest.raises(HTTPException) as exc:
            report_service.get_user_card(db_session, elsewhere.id, moderator)

        assert exc.value.status_code == 403

    def test_moderator_with_no_cells_can_open_no_card(
        self, db_session: Session
    ) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        member = _card_user(db_session)

        with pytest.raises(HTTPException) as exc:
            report_service.get_user_card(db_session, member.id, moderator)

        assert exc.value.status_code == 403

    def test_a_user_with_no_cell_belongs_to_no_moderator(
        self, db_session: Session
    ) -> None:
        """A staff account carries no group or sector, so no cell covers it."""
        moderator = _make_moderator(db_session)
        professional = _make_user(
            db_session, "pro@example.com", role=UserRole.PROFESSIONAL
        )

        with pytest.raises(HTTPException) as exc:
            report_service.get_user_card(db_session, professional.id, moderator)

        assert exc.value.status_code == 403

    def test_admin_can_open_any_card(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.ACTIVE,
        )

        card = report_service.get_user_card(db_session, elsewhere.id, admin)

        assert card.id == elsewhere.id

    def test_nonexistent_user_is_404(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)

        with pytest.raises(HTTPException) as exc:
            report_service.get_user_card(db_session, "no-such-user", moderator)

        assert exc.value.status_code == 404


class TestSuspendUserForModerator:
    def test_suspends_the_user(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)

        card = report_service.suspend_user_for_moderator(
            db_session, member.id, moderator, _suspend_request(hours=48)
        )

        db_session.refresh(member)
        assert member.account_status == AccountStatus.SUSPENDED
        assert member.is_suspended is True
        assert card.is_suspended is True
        assert card.suspended_until is not None

    def test_returns_the_card_as_it_now_stands(self, db_session: Session) -> None:
        """
        The reply is the refreshed card, so the page that asked for the
        suspension does not have to fetch it again to show the result.
        """
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)
        reporter = _make_user(db_session, "reporter@example.com")
        _report_row(db_session, reporter, member, ReportDecision.VALID)

        card = report_service.suspend_user_for_moderator(
            db_session, member.id, moderator, _suspend_request()
        )

        assert card.account_status == AccountStatus.SUSPENDED
        assert card.reports_against_valid == 1

    def test_writes_one_audit_entry_naming_the_moderator(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)

        report_service.suspend_user_for_moderator(
            db_session, member.id, moderator, _suspend_request(hours=48)
        )

        entries = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.USER_SUSPENDED)
            .all()
        )
        assert len(entries) == 1
        assert entries[0].actor_id == moderator.id
        assert entries[0].entity_type == "User"
        assert entries[0].entity_id == member.id
        assert entries[0].details == {"hours": 48, "reason": SUSPENSION_REASON}

    def test_notifies_the_user(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent: list[tuple[str, int, str]] = []
        monkeypatch.setattr(
            user_service,
            "send_suspension_notification",
            lambda *args: sent.append(args),
        )
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)

        report_service.suspend_user_for_moderator(
            db_session, member.id, moderator, _suspend_request(hours=24)
        )

        assert sent == [(member.email, 24, SUSPENSION_REASON)]

    def test_moderator_cannot_suspend_outside_their_cells(
        self, db_session: Session
    ) -> None:
        moderator = _make_moderator(db_session)
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.ACTIVE,
        )

        with pytest.raises(HTTPException) as exc:
            report_service.suspend_user_for_moderator(
                db_session, elsewhere.id, moderator, _suspend_request()
            )

        assert exc.value.status_code == 403
        db_session.refresh(elsewhere)
        assert elsewhere.account_status == AccountStatus.ACTIVE

    def test_the_cell_check_runs_before_anything_else(
        self, db_session: Session
    ) -> None:
        """
        A moderator reaching outside their cells is answered 403 and nothing
        more – not the 400 that would betray the state of that account.
        """
        moderator = _make_moderator(db_session)
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.SUSPENDED,
        )

        with pytest.raises(HTTPException) as exc:
            report_service.suspend_user_for_moderator(
                db_session, elsewhere.id, moderator, _suspend_request()
            )

        assert exc.value.status_code == 403

    def test_an_already_suspended_user_is_rejected(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)
        member = _card_user(db_session)
        report_service.suspend_user_for_moderator(
            db_session, member.id, moderator, _suspend_request()
        )

        with pytest.raises(HTTPException) as exc:
            report_service.suspend_user_for_moderator(
                db_session, member.id, moderator, _suspend_request()
            )

        assert exc.value.status_code == 400

    def test_only_regular_users_can_be_suspended(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        professional = _make_user(
            db_session,
            "pro@example.com",
            role=UserRole.PROFESSIONAL,
            account_status=AccountStatus.ACTIVE,
        )

        with pytest.raises(HTTPException) as exc:
            report_service.suspend_user_for_moderator(
                db_session, professional.id, admin, _suspend_request()
            )

        assert exc.value.status_code == 400

    def test_admin_can_suspend_any_user(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        elsewhere = _make_user(
            db_session,
            "elsewhere@example.com",
            user_type=UserType.WIDOW,
            sector=Sector.SEPHARDIC,
            account_status=AccountStatus.ACTIVE,
        )

        card = report_service.suspend_user_for_moderator(
            db_session, elsewhere.id, admin, _suspend_request()
        )

        assert card.is_suspended is True

    def test_nonexistent_user_is_404(self, db_session: Session) -> None:
        moderator = _make_moderator(db_session)

        with pytest.raises(HTTPException) as exc:
            report_service.suspend_user_for_moderator(
                db_session, "no-such-user", moderator, _suspend_request()
            )

        assert exc.value.status_code == 404


class TestSuspendUserRequestValidation:
    def test_reason_is_mandatory(self) -> None:
        with pytest.raises(ValidationError):
            SuspendUserRequest(hours=48)  # type: ignore[call-arg]

    def test_hours_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            SuspendUserRequest(hours=0, reason=SUSPENSION_REASON)

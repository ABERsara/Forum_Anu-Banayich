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
    SectorVisibility,
    UserRole,
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
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        alert_email=alert_email,
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
        )
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report = report_service.file_report(db_session, _report_data(post.id), reporter)

        assert calls == [
            ("mod-alerts@example.com", report.id, post.content[:100])
        ]

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
        )
        author = _make_user(db_session, "author@example.com")
        reporter1 = _make_user(db_session, "reporter1@example.com")
        reporter2 = _make_user(db_session, "reporter2@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter1)
        report = report_service.file_report(db_session, _report_data(post.id), reporter2)

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
        )
        author = _make_user(db_session, "author@example.com")
        post = _make_post(db_session, author)
        reporters = [_make_user(db_session, f"reporter{i}@example.com") for i in range(4)]

        reports = [
            report_service.file_report(db_session, _report_data(post.id), reporter)
            for reporter in reporters
        ]

        # report_count reaches 2, 3, 4 on these calls -> urgent alert fires each time
        assert calls == [reports[1].id, reports[2].id, reports[3].id]


class TestFileReportModeratorBroadcast:
    def test_broadcasts_to_all_moderators(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(email),
        )
        _make_user(
            db_session, "mod1@example.com", role=UserRole.MODERATOR, alert_email="alert1@example.com"
        )
        _make_user(
            db_session, "mod2@example.com", role=UserRole.MODERATOR, alert_email="alert2@example.com"
        )
        _make_user(db_session, "user@example.com")  # not a moderator
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert sorted(calls) == ["alert1@example.com", "alert2@example.com"]

    def test_falls_back_to_email_when_alert_email_missing(
        self, db_session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(
            report_service,
            "send_moderator_alert",
            lambda email, report_id, content_preview: calls.append(email),
        )
        _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR, alert_email=None)
        author = _make_user(db_session, "author@example.com")
        reporter = _make_user(db_session, "reporter@example.com")
        post = _make_post(db_session, author)

        report_service.file_report(db_session, _report_data(post.id), reporter)

        assert calls == ["mod@example.com"]

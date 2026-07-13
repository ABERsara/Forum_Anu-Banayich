"""
Unit tests for forum_service.create_broadcast_post().
"""

from sqlalchemy.orm import Session

from app.core.constants import (
    AuditAction,
    GroupVisibility,
    PostStatus,
    SectorVisibility,
    UserRole,
)
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.forum import BroadcastCreate
from app.services import forum_service


def _make_admin(db_session: Session, email: str = "admin@example.com") -> User:
    admin = User(
        email=email,
        password_hash="hashed",
        first_name="Admin",
        last_name="User",
        role=UserRole.ADMIN,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


class TestCreateBroadcastPost:
    def test_creates_post_visible_to_all_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        admin = _make_admin(db_session)
        data = BroadcastCreate(title="הודעה חשובה", content="תוכן ההודעה לכלל המשתמשים")

        post = forum_service.create_broadcast_post(db_session, data, admin)

        assert post.id is not None
        assert post.author_id == admin.id
        assert post.title == "הודעה חשובה"
        assert post.content == "תוכן ההודעה לכלל המשתמשים"
        assert post.group_visibility == GroupVisibility.ALL
        assert post.sector_visibility == SectorVisibility.ALL
        assert post.status == PostStatus.VISIBLE

    def test_creates_audit_log_entry(self, db_session: Session) -> None:
        admin = _make_admin(db_session)
        data = BroadcastCreate(title="הודעה חשובה", content="תוכן ההודעה")

        post = forum_service.create_broadcast_post(db_session, data, admin)

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == post.id).all()
        assert len(logs) == 1
        assert logs[0].action == AuditAction.BROADCAST_SENT
        assert logs[0].actor_id == admin.id
        assert logs[0].entity_type == "ForumPost"
        details = logs[0].details
        assert details is not None
        assert details["title"] == "הודעה חשובה"

    def test_two_broadcasts_create_two_independent_posts_and_logs(
        self, db_session: Session
    ) -> None:
        admin = _make_admin(db_session)

        first = forum_service.create_broadcast_post(
            db_session, BroadcastCreate(title="ראשון", content="תוכן ראשון"), admin
        )
        second = forum_service.create_broadcast_post(
            db_session, BroadcastCreate(title="שני", content="תוכן שני"), admin
        )

        assert first.id != second.id
        logs = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == AuditAction.BROADCAST_SENT)
            .all()
        )
        assert len(logs) == 2

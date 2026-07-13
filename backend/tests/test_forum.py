"""
Integration tests for POST /forum/broadcast.
"""

import pytest
from sqlalchemy.orm import Session

from app.core.constants import AuditAction, GroupVisibility, SectorVisibility, UserRole
from app.core.dependencies import get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User

BASE = "/api/v1/forum"


def _make_user(db_session: Session, role: UserRole, email: str) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def as_user():
    """Override get_current_user to return the given user, for the duration of the test."""

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)


class TestCreateBroadcast:
    async def test_admin_can_send_broadcast(self, client, db_session, as_user):
        admin = _make_user(db_session, UserRole.ADMIN, "admin@example.com")
        as_user(admin)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "הודעה חשובה"
        assert body["group_visibility"] == GroupVisibility.ALL
        assert body["sector_visibility"] == SectorVisibility.ALL

    async def test_admin_broadcast_writes_audit_log(self, client, db_session, as_user):
        admin = _make_user(db_session, UserRole.ADMIN, "admin@example.com")
        as_user(admin)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )
        post_id = response.json()["id"]

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == post_id).all()
        assert len(logs) == 1
        assert logs[0].action == AuditAction.BROADCAST_SENT
        assert logs[0].actor_id == admin.id

    async def test_regular_user_cannot_send_broadcast(
        self, client, db_session, as_user
    ):
        user = _make_user(db_session, UserRole.USER, "user@example.com")
        as_user(user)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )

        assert response.status_code == 403

    async def test_moderator_cannot_send_broadcast(self, client, db_session, as_user):
        moderator = _make_user(db_session, UserRole.MODERATOR, "mod@example.com")
        as_user(moderator)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )

        assert response.status_code == 403

    async def test_rejects_title_too_short(self, client, db_session, as_user):
        admin = _make_user(db_session, UserRole.ADMIN, "admin@example.com")
        as_user(admin)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "א", "content": "תוכן"}
        )

        assert response.status_code == 422

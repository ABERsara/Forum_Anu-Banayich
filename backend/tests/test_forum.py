"""
Integration tests for POST /forum/broadcast.
"""

import pytest

from app.core.constants import AuditAction, GroupVisibility, SectorVisibility, UserRole
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.audit import AuditLog
from app.models.user import User

BASE = "/api/v1/forum"


@pytest.fixture
def as_user():
    """
    Bypass real JWT auth for these tests – override get_current_user and
    get_current_active_user directly, the same way test_forum_endpoints.py does.
    """

    def _apply(user: User):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_active_user] = lambda: user

    yield _apply
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_active_user, None)


class TestCreateBroadcast:
    async def test_admin_can_send_broadcast(self, client, make_user, as_user):
        admin = make_user("admin@example.com", role=UserRole.ADMIN)
        as_user(admin)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )

        assert response.status_code == 201
        body = response.json()
        assert body["title"] == "הודעה חשובה"
        assert body["group_visibility"] == GroupVisibility.ALL
        assert body["sector_visibility"] == SectorVisibility.ALL

    async def test_admin_broadcast_writes_audit_log(
        self, client, db_session, make_user, as_user
    ):
        admin = make_user("admin@example.com", role=UserRole.ADMIN)
        as_user(admin)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )
        post_id = response.json()["id"]

        logs = db_session.query(AuditLog).filter(AuditLog.entity_id == post_id).all()
        assert len(logs) == 1
        assert logs[0].action == AuditAction.BROADCAST_SENT
        assert logs[0].actor_id == admin.id

    async def test_regular_user_cannot_send_broadcast(self, client, make_user, as_user):
        user = make_user("user@example.com", role=UserRole.USER)
        as_user(user)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )

        assert response.status_code == 403

    async def test_moderator_cannot_send_broadcast(self, client, make_user, as_user):
        moderator = make_user("mod@example.com", role=UserRole.MODERATOR)
        as_user(moderator)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )

        assert response.status_code == 403

    async def test_missing_token_returns_401(self, client):
        response = await client.post(
            f"{BASE}/broadcast", json={"title": "הודעה חשובה", "content": "תוכן ההודעה"}
        )
        assert response.status_code == 401

    async def test_invalid_token_returns_401(self, client):
        response = await client.post(
            f"{BASE}/broadcast",
            json={"title": "הודעה חשובה", "content": "תוכן ההודעה"},
            headers={"Authorization": "Bearer not.a.valid.jwt"},
        )
        assert response.status_code == 401

    async def test_rejects_title_too_short(self, client, make_user, as_user):
        admin = make_user("admin@example.com", role=UserRole.ADMIN)
        as_user(admin)

        response = await client.post(
            f"{BASE}/broadcast", json={"title": "א", "content": "תוכן"}
        )

        assert response.status_code == 422

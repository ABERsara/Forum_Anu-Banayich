"""
Integration tests for GET/DELETE /forum/posts/{id} and POST .../report.

test_forum_service.py / test_report_service.py already cover the underlying
business rules in full via unit tests on the service functions directly.
These tests instead go through the real HTTP route, to catch wiring mistakes
that unit tests on the service layer can't see: the response_model
conversion, the path param binding, and the actual status code returned over
the wire.
"""

from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.constants import (
    GroupVisibility,
    PostStatus,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_active_user, get_current_user
from app.main import app
from app.models.forum import ForumPost
from app.models.user import User

BASE = "/api/v1/forum/posts"


def _make_user(
    db_session,
    email: str,
    user_type: UserType | None = None,
    sector: Sector | None = None,
    role: UserRole = UserRole.USER,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_post(
    db_session,
    author: User,
    group_visibility: GroupVisibility,
    sector_visibility: SectorVisibility,
    status: PostStatus = PostStatus.VISIBLE,
) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="כותרת",
        content="תוכן ההודעה",
        group_visibility=group_visibility,
        sector_visibility=sector_visibility,
        status=status,
    )
    db_session.add(post)
    db_session.commit()
    return post


def _login_as(user: User) -> None:
    """
    Bypass real JWT auth for these tests – override get_current_user and
    get_current_active_user directly, the same way conftest.py's `client`
    fixture overrides get_db.
    """
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_active_user] = lambda: user


class TestGetPostEndpoint:
    async def test_success_returns_200_with_post_fields(self, client, db_session):
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, user, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )
        _login_as(user)

        r = await client.get(f"{BASE}/{post.id}")

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == post.id
        assert body["title"] == "כותרת"
        assert body["author"]["id"] == user.id

    async def test_nonexistent_id_returns_404(self, client, db_session):
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(user)

        r = await client.get(f"{BASE}/no-such-id")

        assert r.status_code == 404

    async def test_mismatched_group_returns_403(self, client, db_session):
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_author = _make_user(
            db_session, "widower@example.com", UserType.WIDOWER, Sector.HASIDIC
        )
        post = _make_post(
            db_session, other_author, GroupVisibility.WIDOWERS, SectorVisibility.HASIDIC
        )
        _login_as(user)

        r = await client.get(f"{BASE}/{post.id}")

        assert r.status_code == 403


class TestDeletePostEndpoint:
    async def test_author_delete_returns_200_with_deleted_status(
        self, client, db_session
    ):
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, user, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )
        _login_as(user)

        r = await client.delete(f"{BASE}/{post.id}")

        assert r.status_code == 200
        assert r.json()["status"] == "deleted"

    async def test_other_user_gets_403(self, client, db_session):
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_user = _make_user(
            db_session, "widow2@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )
        _login_as(other_user)

        r = await client.delete(f"{BASE}/{post.id}")

        assert r.status_code == 403


class TestReportPostEndpoint:
    async def test_success_returns_201_with_report_fields(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        author = _make_user(
            db_session, "author@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        reporter = _make_user(
            db_session, "reporter@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )
        _login_as(reporter)

        r = await client.post(
            f"{BASE}/{post.id}/report",
            json={"target_type": "forum_post", "target_id": post.id, "reason": "harassment"},
        )

        assert r.status_code == 201
        body = r.json()
        assert body["reporter_id"] == reporter.id
        assert body["target_id"] == post.id
        assert body["reason"] == "harassment"
        assert body["decision"] == "pending"

    async def test_mismatched_target_id_returns_400(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        author = _make_user(
            db_session, "author@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        reporter = _make_user(
            db_session, "reporter@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )
        _login_as(reporter)

        r = await client.post(
            f"{BASE}/{post.id}/report",
            json={"target_type": "forum_post", "target_id": "some-other-id", "reason": "spam"},
        )

        assert r.status_code == 400

    async def test_nonexistent_post_returns_404(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        reporter = _make_user(
            db_session, "reporter@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _login_as(reporter)

        r = await client.post(
            f"{BASE}/no-such-id/report",
            json={"target_type": "forum_post", "target_id": "no-such-id", "reason": "spam"},
        )

        assert r.status_code == 404

    async def test_duplicate_report_returns_409(
        self, client: AsyncClient, db_session: Session
    ) -> None:
        author = _make_user(
            db_session, "author@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        reporter = _make_user(
            db_session, "reporter@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )
        _login_as(reporter)
        payload = {"target_type": "forum_post", "target_id": post.id, "reason": "spam"}

        first = await client.post(f"{BASE}/{post.id}/report", json=payload)
        second = await client.post(f"{BASE}/{post.id}/report", json=payload)

        assert first.status_code == 201
        assert second.status_code == 409

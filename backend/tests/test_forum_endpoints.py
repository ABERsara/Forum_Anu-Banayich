"""
Integration tests for GET /forum/posts/{id}.

test_forum_service.py already covers the visibility rules in full via unit
tests on forum_service.get_post_by_id() directly. These tests instead go
through the real HTTP route, to catch wiring mistakes that unit tests on the
service function can't see: the response_model conversion, the path param
binding, and the actual status code returned over the wire.
"""

from app.core.constants import (
    GroupVisibility,
    PostStatus,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.core.dependencies import get_current_user
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
    Bypass real JWT auth for these tests – override get_current_user directly,
    the same way conftest.py's `client` fixture overrides get_db.
    """
    app.dependency_overrides[get_current_user] = lambda: user


class TestGetPostEndpoint:
    async def test_success_returns_200_with_post_fields(self, client, db_session):
        user = _make_user(db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC)
        post = _make_post(db_session, user, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC)
        _login_as(user)

        r = await client.get(f"{BASE}/{post.id}")

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == post.id
        assert body["title"] == "כותרת"
        assert body["author"]["id"] == user.id

    async def test_nonexistent_id_returns_404(self, client, db_session):
        user = _make_user(db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC)
        _login_as(user)

        r = await client.get(f"{BASE}/no-such-id")

        assert r.status_code == 404

    async def test_mismatched_group_returns_403(self, client, db_session):
        user = _make_user(db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC)
        other_author = _make_user(
            db_session, "widower@example.com", UserType.WIDOWER, Sector.HASIDIC
        )
        post = _make_post(
            db_session, other_author, GroupVisibility.WIDOWERS, SectorVisibility.HASIDIC
        )
        _login_as(user)

        r = await client.get(f"{BASE}/{post.id}")

        assert r.status_code == 403

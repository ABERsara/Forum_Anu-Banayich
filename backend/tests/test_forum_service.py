"""
Unit tests for forum_service.get_posts() and its content filter.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import (
    GroupVisibility,
    PostStatus,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.models.forum import ForumPost
from app.models.user import User
from app.services import forum_service


def _make_user(
    db_session: Session,
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
    db_session: Session,
    author: User,
    group_visibility: GroupVisibility,
    sector_visibility: SectorVisibility,
    status: PostStatus = PostStatus.VISIBLE,
    created_at: datetime | None = None,
) -> ForumPost:
    post = ForumPost(
        author_id=author.id,
        title="Title",
        content="Content",
        group_visibility=group_visibility,
        sector_visibility=sector_visibility,
        status=status,
        created_at=created_at or datetime.now(UTC).replace(tzinfo=None),
    )
    db_session.add(post)
    db_session.commit()
    return post


class TestGetPostsContentFilter:
    def test_user_sees_matching_group_and_sector_post(
        self, db_session: Session
    ) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_post(db_session, user, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC)

        result = forum_service.get_posts(db_session, user)

        assert result.total == 1

    def test_user_does_not_see_other_group_post(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_author = _make_user(
            db_session, "widower@example.com", UserType.WIDOWER, Sector.HASIDIC
        )
        _make_post(
            db_session, other_author, GroupVisibility.WIDOWERS, SectorVisibility.HASIDIC
        )

        result = forum_service.get_posts(db_session, user)

        assert result.total == 0

    def test_user_does_not_see_other_sector_post(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow-hasidic@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_author = _make_user(
            db_session, "widow-litvish@example.com", UserType.WIDOW, Sector.LITVISH
        )
        _make_post(
            db_session, other_author, GroupVisibility.WIDOWS, SectorVisibility.LITVISH
        )

        result = forum_service.get_posts(db_session, user)

        assert result.total == 0

    def test_user_sees_post_visible_to_all_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        _make_post(db_session, admin, GroupVisibility.ALL, SectorVisibility.ALL)

        result = forum_service.get_posts(db_session, user)

        assert result.total == 1

    def test_user_does_not_see_hidden_or_deleted_posts(
        self, db_session: Session
    ) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_post(
            db_session,
            user,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.HIDDEN,
        )
        _make_post(
            db_session,
            user,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.DELETED,
        )

        result = forum_service.get_posts(db_session, user)

        assert result.total == 0


class TestGetPostsAdminBypass:
    def test_admin_sees_posts_from_other_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        widow = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_post(db_session, widow, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC)

        result = forum_service.get_posts(db_session, admin)

        assert result.total == 1

    def test_admin_sees_hidden_posts(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        widow = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_post(
            db_session,
            widow,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.HIDDEN,
        )

        result = forum_service.get_posts(db_session, admin)

        assert result.total == 1

    def test_admin_does_not_see_deleted_posts(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        widow = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        _make_post(
            db_session,
            widow,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.DELETED,
        )

        result = forum_service.get_posts(db_session, admin)

        assert result.total == 0


class TestGetPostsPagination:
    def test_total_counts_all_matching_posts_not_just_current_page(
        self, db_session: Session
    ) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        for _ in range(5):
            _make_post(
                db_session, user, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
            )

        result = forum_service.get_posts(db_session, user, page=1, page_size=2)

        assert result.total == 5
        assert len(result.items) == 2

    def test_offset_returns_correct_page_ordered_by_newest_first(
        self, db_session: Session
    ) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        base = datetime.now(UTC).replace(tzinfo=None)
        posts = [
            _make_post(
                db_session,
                user,
                GroupVisibility.WIDOWS,
                SectorVisibility.HASIDIC,
                created_at=base + timedelta(minutes=i),
            )
            for i in range(5)
        ]

        page1 = forum_service.get_posts(db_session, user, page=1, page_size=2)
        page2 = forum_service.get_posts(db_session, user, page=2, page_size=2)

        assert [item.id for item in page1.items] == [posts[4].id, posts[3].id]
        assert [item.id for item in page2.items] == [posts[2].id, posts[1].id]


class TestGetPostsRoleGuard:
    def test_moderator_gets_403_not_500(self, db_session: Session) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_posts(db_session, moderator)

        assert exc_info.value.status_code == 403

    def test_professional_gets_403_not_500(self, db_session: Session) -> None:
        professional = _make_user(
            db_session, "pro@example.com", role=UserRole.PROFESSIONAL
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_posts(db_session, professional)

        assert exc_info.value.status_code == 403


class TestGetPostByIdRoleGuard:
    def test_professional_gets_403(self, db_session: Session) -> None:
        professional = _make_user(
            db_session, "pro@example.com", role=UserRole.PROFESSIONAL
        )
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_post_by_id(db_session, post.id, professional)

        assert exc_info.value.status_code == 403

    def test_nonexistent_id_gets_404(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_post_by_id(db_session, "no-such-id", user)

        assert exc_info.value.status_code == 404


class TestGetPostByIdAsUser:
    def test_sees_own_group_and_sector_post(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, user, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.get_post_by_id(db_session, post.id, user)

        assert result.id == post.id

    def test_mismatched_group_gets_403(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_author = _make_user(
            db_session, "widower@example.com", UserType.WIDOWER, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            other_author,
            GroupVisibility.WIDOWERS,
            SectorVisibility.HASIDIC,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_post_by_id(db_session, post.id, user)

        assert exc_info.value.status_code == 403

    def test_hidden_post_gets_404(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            user,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.HIDDEN,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_post_by_id(db_session, post.id, user)

        assert exc_info.value.status_code == 404

    def test_deleted_post_gets_404(self, db_session: Session) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            user,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.DELETED,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_post_by_id(db_session, post.id, user)

        assert exc_info.value.status_code == 404


class TestGetPostByIdAsAdmin:
    def test_sees_deleted_post(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            author,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.DELETED,
        )

        result = forum_service.get_post_by_id(db_session, post.id, admin)

        assert result.id == post.id

    def test_sees_hidden_post(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            author,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.HIDDEN,
        )

        result = forum_service.get_post_by_id(db_session, post.id, admin)

        assert result.id == post.id

    def test_sees_post_from_other_group_and_sector(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.get_post_by_id(db_session, post.id, admin)

        assert result.id == post.id


class TestGetPostByIdAsModerator:
    def test_sees_hidden_post(self, db_session: Session) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            author,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.HIDDEN,
        )

        result = forum_service.get_post_by_id(db_session, post.id, moderator)

        assert result.id == post.id

    def test_deleted_post_gets_404(self, db_session: Session) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            author,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            status=PostStatus.DELETED,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.get_post_by_id(db_session, post.id, moderator)

        assert exc_info.value.status_code == 404

    def test_sees_post_from_other_group_and_sector(self, db_session: Session) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.get_post_by_id(db_session, post.id, moderator)

        assert result.id == post.id

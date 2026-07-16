"""
Unit tests for forum_service.get_posts() and its content filter.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    PostStatus,
    Sector,
    SectorVisibility,
    UserRole,
    UserType,
)
from app.models.audit import AuditLog
from app.models.forum import ForumPost
from app.models.user import User
from app.schemas.forum import ForumPostCreate, ForumPostUpdate
from app.services import forum_service


def _make_user(
    db_session: Session,
    email: str,
    user_type: UserType | None = None,
    sector: Sector | None = None,
    role: UserRole = UserRole.USER,
    account_status: AccountStatus = AccountStatus.PENDING_OTP,
) -> User:
    user = User(
        email=email,
        password_hash="hashed",
        first_name="Test",
        last_name="User",
        role=role,
        user_type=user_type,
        sector=sector,
        account_status=account_status,
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

    def test_sees_post_visible_to_all_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        user = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        post = _make_post(db_session, admin, GroupVisibility.ALL, SectorVisibility.ALL)

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


class TestDeletePost:
    def test_author_can_delete_own_post(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.delete_post(db_session, post.id, author)

        assert result.status == PostStatus.DELETED

    def test_moderator_can_delete_post_from_other_group_and_sector(
        self, db_session: Session
    ) -> None:
        moderator = _make_user(db_session, "mod@example.com", role=UserRole.MODERATOR)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.delete_post(db_session, post.id, moderator)

        assert result.status == PostStatus.DELETED

    def test_admin_can_delete_any_post(self, db_session: Session) -> None:
        admin = _make_user(db_session, "admin@example.com", role=UserRole.ADMIN)
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.delete_post(db_session, post.id, admin)

        assert result.status == PostStatus.DELETED

    def test_other_regular_user_gets_403(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_user = _make_user(
            db_session, "widow2@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.delete_post(db_session, post.id, other_user)

        assert exc_info.value.status_code == 403

    def test_nonexistent_id_gets_404(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.delete_post(db_session, "no-such-id", author)

        assert exc_info.value.status_code == 404

    def test_deleting_already_deleted_post_is_idempotent(
        self, db_session: Session
    ) -> None:
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

        result = forum_service.delete_post(db_session, post.id, author)

        assert result.status == PostStatus.DELETED

    def test_delete_writes_a_single_audit_log_entry(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        forum_service.delete_post(db_session, post.id, author)

        entries = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.entity_id == post.id,
                AuditLog.action == AuditAction.POST_DELETED,
            )
            .all()
        )
        assert len(entries) == 1
        assert entries[0].actor_id == author.id

    def test_repeat_delete_does_not_duplicate_audit_log(
        self, db_session: Session
    ) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        forum_service.delete_post(db_session, post.id, author)
        forum_service.delete_post(db_session, post.id, author)

        entries = (
            db_session.query(AuditLog)
            .filter(
                AuditLog.entity_id == post.id,
                AuditLog.action == AuditAction.POST_DELETED,
            )
            .all()
        )
        assert len(entries) == 1


class TestCreatePost:
    def test_active_author_can_post_to_own_group_and_sector(
        self, db_session: Session
    ) -> None:
        author = _make_user(
            db_session,
            "widow@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )

        result = forum_service.create_post(
            db_session,
            ForumPostCreate(
                title="כותרת",
                content="תוכן",
                group_visibility=GroupVisibility.WIDOWS,
                sector_visibility=SectorVisibility.HASIDIC,
            ),
            author,
        )

        assert result.author_id == author.id
        assert result.status == PostStatus.VISIBLE

    def test_active_author_can_post_to_all_groups_and_sectors(
        self, db_session: Session
    ) -> None:
        author = _make_user(
            db_session,
            "widow@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )

        result = forum_service.create_post(
            db_session,
            ForumPostCreate(
                title="כותרת",
                content="תוכן",
                group_visibility=GroupVisibility.ALL,
                sector_visibility=SectorVisibility.ALL,
            ),
            author,
        )

        assert result.group_visibility == GroupVisibility.ALL

    def test_non_active_author_gets_403(self, db_session: Session) -> None:
        author = _make_user(
            db_session,
            "widow@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.PENDING_APPROVAL,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.create_post(
                db_session,
                ForumPostCreate(
                    title="כותרת",
                    content="תוכן",
                    group_visibility=GroupVisibility.WIDOWS,
                    sector_visibility=SectorVisibility.HASIDIC,
                ),
                author,
            )

        assert exc_info.value.status_code == 403

    def test_posting_to_a_different_group_gets_403(self, db_session: Session) -> None:
        author = _make_user(
            db_session,
            "widow@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.create_post(
                db_session,
                ForumPostCreate(
                    title="כותרת",
                    content="תוכן",
                    group_visibility=GroupVisibility.WIDOWERS,
                    sector_visibility=SectorVisibility.HASIDIC,
                ),
                author,
            )

        assert exc_info.value.status_code == 403

    def test_posting_to_a_different_sector_gets_403(self, db_session: Session) -> None:
        author = _make_user(
            db_session,
            "widow@example.com",
            UserType.WIDOW,
            Sector.HASIDIC,
            account_status=AccountStatus.ACTIVE,
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.create_post(
                db_session,
                ForumPostCreate(
                    title="כותרת",
                    content="תוכן",
                    group_visibility=GroupVisibility.WIDOWS,
                    sector_visibility=SectorVisibility.LITVISH,
                ),
                author,
            )

        assert exc_info.value.status_code == 403


class TestUpdatePost:
    def test_author_can_update_title_and_content(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.update_post(
            db_session,
            post.id,
            ForumPostUpdate(title="כותרת חדשה", content="תוכן חדש"),
            author,
        )

        assert result.title == "כותרת חדשה"
        assert result.content == "תוכן חדש"

    def test_partial_update_title_only_leaves_content_unchanged(
        self, db_session: Session
    ) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.update_post(
            db_session, post.id, ForumPostUpdate(title="כותרת חדשה"), author
        )

        assert result.title == "כותרת חדשה"
        assert result.content == "Content"

    def test_partial_update_content_only_leaves_title_unchanged(
        self, db_session: Session
    ) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        result = forum_service.update_post(
            db_session, post.id, ForumPostUpdate(content="תוכן חדש"), author
        )

        assert result.title == "Title"
        assert result.content == "תוכן חדש"

    def test_updated_at_advances_past_created_at(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session,
            author,
            GroupVisibility.WIDOWS,
            SectorVisibility.HASIDIC,
            created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=5),
        )

        result = forum_service.update_post(
            db_session, post.id, ForumPostUpdate(title="כותרת חדשה"), author
        )

        assert result.updated_at > result.created_at

    def test_non_author_gets_403(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        other_user = _make_user(
            db_session, "widow2@example.com", UserType.WIDOW, Sector.HASIDIC
        )
        post = _make_post(
            db_session, author, GroupVisibility.WIDOWS, SectorVisibility.HASIDIC
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.update_post(
                db_session, post.id, ForumPostUpdate(title="כותרת חדשה"), other_user
            )

        assert exc_info.value.status_code == 403

    def test_nonexistent_id_gets_404(self, db_session: Session) -> None:
        author = _make_user(
            db_session, "widow@example.com", UserType.WIDOW, Sector.HASIDIC
        )

        with pytest.raises(HTTPException) as exc_info:
            forum_service.update_post(
                db_session, "no-such-id", ForumPostUpdate(title="כותרת חדשה"), author
            )

        assert exc_info.value.status_code == 404

    def test_deleted_post_gets_404(self, db_session: Session) -> None:
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
            forum_service.update_post(
                db_session, post.id, ForumPostUpdate(title="כותרת חדשה"), author
            )

        assert exc_info.value.status_code == 404

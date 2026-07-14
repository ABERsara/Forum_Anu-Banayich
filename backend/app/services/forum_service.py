"""
Forum service.

⚠️  CRITICAL: Every query that returns content MUST apply the content filter.
    Never return posts that don't match the user's group+sector.
    The filter must be on the DB side – not in Python code after fetching all rows.

TODO list for junior developer:
  [ ] implement get_posts() – with content filter + pagination
  [ ] implement create_post()
  [ ] implement get_post_by_id() – verify user can see it
  [ ] implement search_users_for_dm() – name search within same group/sector
"""

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Query, Session, joinedload

from app.core.constants import GroupVisibility, PostStatus, SectorVisibility, UserRole
from app.models.forum import DirectMessage, ForumPost
from app.models.user import User
from app.schemas.forum import (
    DirectMessageCreate,
    ForumPostCreate,
    ForumPostListResponse,
    ForumPostResponse,
)


def _content_filter(query: Query[ForumPost], current_user: User) -> Query[ForumPost]:
    """
    Apply the visibility filter to a query on ForumPost.

    A post is visible to the user if:
      (group_visibility == user.user_type OR group_visibility == "all")
      AND
      (sector_visibility == user.sector OR sector_visibility == "all")

    This filter is the heart of the privacy model – do not skip it!
    """
    # user_type/sector are Optional on User (roles other than USER don't have them).
    # Only get_posts()'s non-admin branch calls this today, where they're always set –
    # but nothing enforces that at the type level, so assert it explicitly here rather
    # than let a future caller hit a confusing AttributeError deep inside the filter.
    assert current_user.user_type is not None, (
        "_content_filter() requires a user with user_type set"
    )
    assert current_user.sector is not None, (
        "_content_filter() requires a user with sector set"
    )
    group_visibility = GroupVisibility(current_user.user_type.value)
    sector_visibility = SectorVisibility(current_user.sector.value)
    return query.filter(
        or_(
            ForumPost.group_visibility == group_visibility,
            ForumPost.group_visibility == GroupVisibility.ALL,
        ),
        or_(
            ForumPost.sector_visibility == sector_visibility,
            ForumPost.sector_visibility == SectorVisibility.ALL,
        ),
    )


def get_posts(
    db: Session,
    current_user: User,
    page: int = 1,
    page_size: int = 20,
) -> ForumPostListResponse:
    """
    Return a paginated list of posts visible to the current user.

    TODO:
      1. Start with db.query(ForumPost)
      2. Apply _content_filter(query, current_user)
      3. Filter status == VISIBLE
      4. Order by created_at DESC
      5. Apply offset + limit for pagination
      6. Return ForumPostListResponse
    """
    if current_user.role not in (UserRole.USER, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="אין לך הרשאה לגשת לפורום הקהילתי.")

    query = db.query(ForumPost).options(joinedload(ForumPost.author))

    if current_user.role == UserRole.ADMIN:
        query = query.filter(ForumPost.status != PostStatus.DELETED)
    else:
        query = _content_filter(query, current_user)
        query = query.filter(ForumPost.status == PostStatus.VISIBLE)

    total = query.count()

    posts = (
        query.order_by(ForumPost.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ForumPostListResponse(
        items=[ForumPostResponse.model_validate(post) for post in posts],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_post_by_id(db: Session, post_id: str, current_user: User) -> ForumPost:
    """
    Return a single post – raise 404 if not found, 403 if not visible to user.

    TODO:
      1. Query ForumPost by id
      2. Check it passes _content_filter for this user
      3. Check status != DELETED
    """
    # TODO: implement this function
    raise NotImplementedError("get_post_by_id() is not yet implemented")


def create_post(db: Session, data: ForumPostCreate, author: User) -> ForumPost:
    """
    Create a new forum post.

    Validations:
      - Author must be ACTIVE
      - If group_visibility targets a specific group, it must match author's user_type
        (a widow cannot post in the widowers group)

    TODO:
      1. Validate visibility is not "broader" than author's actual group/sector
      2. Create ForumPost object
      3. db.add(), db.commit(), db.refresh()
      4. Return the post
    """
    # TODO: implement this function
    raise NotImplementedError("create_post() is not yet implemented")


def send_direct_message(
    db: Session, data: DirectMessageCreate, sender: User
) -> DirectMessage:
    """
    Send a private message.

    Validations:
      - Recipient must be in the same group as sender
      - Recipient must be ACTIVE
      - Sender is not blocked by recipient (check report history)

    TODO:
      1. Load recipient, validate same group
      2. Encrypt content (or mark as needing encryption)
      3. Create DirectMessage, save to DB
    """
    # TODO: implement this function
    raise NotImplementedError("send_direct_message() is not yet implemented")


def get_conversation(
    db: Session, current_user: User, other_user_id: str, page: int = 1
) -> list[DirectMessage]:
    """
    Return messages between current_user and other_user, newest first.

    TODO:
      1. Query DirectMessage where (sender=me AND recipient=other) OR (sender=other AND recipient=me)
      2. Order by created_at DESC
      3. Apply pagination (max 50 per page)
      4. Mark retrieved messages as is_read=True
    """
    # TODO: implement this function
    raise NotImplementedError("get_conversation() is not yet implemented")


def search_users_for_dm(db: Session, current_user: User, name: str) -> list[User]:
    """
    Search for users to send a DM to.

    Rules:
      - Only users in the SAME group as current_user
      - Search by first_name or last_name (case-insensitive)
      - Never expose contact details (phone/email) – name only

    TODO:
      1. Query users where user_type == current_user.user_type AND account_status == ACTIVE
      2. Filter by name ILIKE
      3. Return list (no PII beyond name)
    """
    # TODO: implement this function
    raise NotImplementedError("search_users_for_dm() is not yet implemented")

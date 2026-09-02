"""
Like service.

General-purpose "like" toggle — deliberately its own file rather than
folded into professional_service.py, since this infrastructure is meant to
serve ForumPost likes too (ABF-143), not just ProfessionalQuery.
"""

from fastapi import HTTPException
from sqlalchemy import Subquery, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import LikeTargetType, PostStatus, QueryStatus, UserRole
from app.models.forum import ForumPost
from app.models.like import Like
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.schemas.like import LikeResponse
from app.services import forum_service


def _may_view_professional_query(query: ProfessionalQuery, user: User) -> bool:
    """
    Visibility check for PROFESSIONAL_QUERY, shared with the public Q&A feed
    (see professional_service.get_public_qa()) — both compare against the
    asker's cell as frozen onto the query at creation time
    (asker_user_type/asker_sector), not a live join to the asker's current
    profile. Keeps a single visibility mechanism instead of two: a user's
    like access to an old question no longer shifts if they edit their own
    profile later.

    ADMIN sees everything. USER sees their own question, or any public
    question whose asker's frozen cell matches their own. PROFESSIONAL/
    MODERATOR are never expected here — the endpoint's require_role blocks
    them first.
    """
    if user.role == UserRole.ADMIN:
        return True

    if query.asker_id == user.id:
        return True

    if not query.is_public:
        return False

    if query.asker_user_type is None or query.asker_sector is None:
        return False
    if user.user_type is None or user.sector is None:
        return False
    return bool(
        query.asker_user_type == user.user_type and query.asker_sector == user.sector
    )


def _may_view_forum_post(post: ForumPost, user: User) -> bool:
    """
    Visibility check for FORUM_POST, reusing forum_service's own per-post
    content filter rather than duplicating its group/sector OR-logic here.

    ADMIN sees everything, same as get_post_by_id()'s admin branch. Every
    other role needs a VISIBLE post and a matching cell — _matches_content_filter()
    requires user_type/sector to be set, which is true for USER but not for
    MODERATOR, so this is only ever called for roles that have them (the
    endpoint's require_role restricts callers to USER/ADMIN).
    """
    if user.role == UserRole.ADMIN:
        return True
    return post.status == PostStatus.VISIBLE and forum_service._matches_content_filter(
        post, user
    )


def like_annotations(
    db: Session, target_type: LikeTargetType, current_user: User
) -> tuple[Subquery, Subquery]:
    """
    Grouped like_count subquery and current-user's-likes subquery for
    `target_type`, meant to be outerjoin'd onto a paginated listing query via
    add_columns() — one SELECT for the whole page, not one per row.

    Shared between forum_service.get_posts() and
    professional_service.get_public_qa() so the aggregation logic can't drift
    apart between the two call sites.
    """
    like_counts = (
        db.query(Like.target_id, func.count(Like.user_id).label("like_count"))
        .filter(Like.target_type == target_type)
        .group_by(Like.target_id)
        .subquery()
    )
    my_likes = (
        db.query(Like.target_id)
        .filter(Like.target_type == target_type, Like.user_id == current_user.id)
        .subquery()
    )
    return like_counts, my_likes


def _like_count(db: Session, target_type: LikeTargetType, target_id: str) -> int:
    return (
        db.query(Like)
        .filter(Like.target_type == target_type, Like.target_id == target_id)
        .count()
    )


def toggle_like(
    db: Session, target_type: LikeTargetType, target_id: str, user: User
) -> LikeResponse:
    """
    Like the target if the user hasn't liked it yet, otherwise un-like it.

    A double-click race (two requests both trying to insert the same
    (user, target) row) is caught explicitly: the composite primary key
    rejects the second INSERT, and that IntegrityError is treated as
    "already liked" instead of surfacing as a 500.

    The ANSWERED requirement below only gates creating a new like — removing
    an existing one is always allowed once visibility passes, so a like never
    gets stuck un-removable if the question's status later moves on.
    """
    if target_type == LikeTargetType.PROFESSIONAL_QUERY:
        query = (
            db.query(ProfessionalQuery)
            .filter(ProfessionalQuery.id == target_id)
            .first()
        )
        if query is None:
            raise HTTPException(status_code=404, detail="השאלה לא נמצאה.")
        if not _may_view_professional_query(query, user):
            raise HTTPException(status_code=403, detail="אין לך הרשאה לצפות בשאלה זו.")
    elif target_type == LikeTargetType.FORUM_POST:
        post = db.query(ForumPost).filter(ForumPost.id == target_id).first()
        if post is None:
            raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")
        if not _may_view_forum_post(post, user):
            raise HTTPException(status_code=403, detail="אין לך הרשאה לצפות בהודעה זו.")
    else:
        raise HTTPException(status_code=400, detail="סוג תוכן זה אינו נתמך ללייק כרגע.")

    existing = (
        db.query(Like)
        .filter(
            Like.user_id == user.id,
            Like.target_type == target_type,
            Like.target_id == target_id,
        )
        .first()
    )

    if existing is not None:
        db.delete(existing)
        db.commit()
        liked = False
    else:
        if (
            target_type == LikeTargetType.PROFESSIONAL_QUERY
            and query is not None
            and query.status != QueryStatus.ANSWERED
        ):
            raise HTTPException(
                status_code=409, detail="ניתן לסמן לייק רק לשאלה שנענתה."
            )
        db.add(Like(user_id=user.id, target_type=target_type, target_id=target_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
        liked = True

    return LikeResponse(liked=liked, like_count=_like_count(db, target_type, target_id))

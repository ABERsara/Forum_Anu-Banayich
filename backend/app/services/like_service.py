"""
Like service.

General-purpose "like" toggle — deliberately its own file rather than
folded into professional_service.py, since this infrastructure is meant to
serve ForumPost likes too (ABF-143), not just ProfessionalQuery.
"""

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.constants import LikeTargetType, QueryStatus, UserRole
from app.models.like import Like
from app.models.professional import ProfessionalQuery
from app.models.user import User
from app.schemas.like import LikeResponse


def _may_view_professional_query(query: ProfessionalQuery, user: User) -> bool:
    """
    Temporary, isolated visibility check for PROFESSIONAL_QUERY — no such
    check exists anywhere else in the code yet. ABF-140 will replace this
    with a check against frozen visibility fields snapshotted on the query
    itself; until then this joins through asker_id to the asker's live User
    row, in the spirit of forum_service._content_filter.

    ADMIN sees everything. USER sees their own question, or any public
    question whose asker shares their group+sector (the "visible to all
    members of the asker's group/sector" rule from professional.py's
    docstring). PROFESSIONAL/MODERATOR are never expected here — the
    endpoint's require_role blocks them first.
    """
    if user.role == UserRole.ADMIN:
        return True

    if query.asker_id == user.id:
        return True

    if not query.is_public:
        return False

    asker = query.asker
    if asker.user_type is None or asker.sector is None:
        return False
    if user.user_type is None or user.sector is None:
        return False
    return bool(asker.user_type == user.user_type and asker.sector == user.sector)


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

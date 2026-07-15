"""
Forum endpoints.

GET    /forum/posts           – list posts (auto-filtered by group+sector)
POST   /forum/posts           – create a new post
GET    /forum/posts/{id}      – single post
DELETE /forum/posts/{id}      – delete (soft-delete) a post
POST   /forum/posts/{id}/report – report a post

GET    /messages              – inbox (list of conversations)
POST   /messages              – send a direct message
GET    /messages/{user_id}    – conversation with a specific user
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_active_user, get_db
from app.models.user import User
from app.schemas.forum import (
    ConversationSummary,
    DirectMessageCreate,
    DirectMessageResponse,
    ForumPostCreate,
    ForumPostListResponse,
    ForumPostResponse,
)
from app.schemas.report import ReportCreate
from app.services import forum_service

router = APIRouter(tags=["Forum & Messages"])


# ──────────────────────────────────────────────────────────
# Forum posts
# ──────────────────────────────────────────────────────────


@router.get("/forum/posts", response_model=ForumPostListResponse)
def list_posts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ForumPostListResponse:
    """
    Return posts visible to the current user.
    Filtering is automatic – the user only sees their group+sector content.
    """
    return forum_service.get_posts(db, current_user, page, page_size)


@router.post("/forum/posts", response_model=ForumPostResponse, status_code=201)
def create_post(
    data: ForumPostCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ForumPostResponse:
    """
    Publish a new forum post.

    TODO: call forum_service.create_post(db, data, current_user)
    """
    # TODO: implement
    raise NotImplementedError


@router.get("/forum/posts/{post_id}", response_model=ForumPostResponse)
def get_post(
    post_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ForumPostResponse:
    """
    Return a single forum post.
    """
    post = forum_service.get_post_by_id(db, post_id, current_user)
    return ForumPostResponse.model_validate(post)


@router.delete("/forum/posts/{post_id}", response_model=ForumPostResponse)
def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ForumPostResponse:
    """
    Delete (soft-delete) a forum post. Allowed for the post's author, any
    moderator, or an admin.
    """
    post = forum_service.delete_post(db, post_id, current_user)
    return ForumPostResponse.model_validate(post)


@router.post("/forum/posts/{post_id}/report", status_code=201)
def report_post(
    post_id: str,
    data: ReportCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Report a forum post.

    TODO: call report_service.file_report(db, data, current_user)
    """
    # TODO: implement
    raise NotImplementedError


# ──────────────────────────────────────────────────────────
# Direct messages
# ──────────────────────────────────────────────────────────


@router.get("/messages", response_model=list[ConversationSummary])
def get_inbox(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[ConversationSummary]:
    """
    Return a list of conversations (inbox view).

    TODO: implement – group messages by conversation partner, show latest message
    """
    # TODO: implement
    return []


@router.post("/messages", response_model=DirectMessageResponse, status_code=201)
def send_message(
    data: DirectMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> DirectMessageResponse:
    """
    Send a private message.

    TODO: call forum_service.send_direct_message(db, data, current_user)
    """
    # TODO: implement
    raise NotImplementedError


@router.get("/messages/{user_id}", response_model=list[DirectMessageResponse])
def get_conversation(
    user_id: str,
    page: int = Query(1, ge=1),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[DirectMessageResponse]:
    """
    Return the conversation with a specific user.

    TODO: call forum_service.get_conversation(db, current_user, user_id, page)
    """
    # TODO: implement
    return []

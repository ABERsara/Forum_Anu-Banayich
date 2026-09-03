"""
Forum endpoints.

GET    /forum/posts           – list posts (auto-filtered by group+sector)
POST   /forum/posts           – create a new post
GET    /forum/posts/{id}      – single post
PATCH  /forum/posts/{id}      – edit a post (author only)
DELETE /forum/posts/{id}      – delete (soft-delete) a post
POST   /forum/posts/{id}/report – report a post
POST   /forum/broadcast       – admin-only post visible to all users

GET    /messages                          – inbox (list of conversations, paginated)
POST   /messages                          – send a direct message (own cell only)
GET    /conversations/{key}/messages      – one page of a conversation, newest first
GET    /cells/me/members                  – other ACTIVE users in your own cell
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.user import User
from app.schemas.forum import (
    BroadcastCreate,
    ConversationListResponse,
    ConversationMessagesPage,
    DirectMessageCreate,
    DirectMessageSendResponse,
    ForumPostCreate,
    ForumPostListResponse,
    ForumPostResponse,
    ForumPostUpdate,
)
from app.schemas.report import ReportCreate, ReportResponse
from app.schemas.user import UserPublic
from app.services import forum_service, report_service

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
    """
    post = forum_service.create_post(db, data, current_user)
    return ForumPostResponse.model_validate(post)


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


@router.patch("/forum/posts/{post_id}", response_model=ForumPostResponse)
def update_post(
    post_id: str,
    data: ForumPostUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ForumPostResponse:
    """
    Edit a forum post's title and/or content. Author only.
    """
    post = forum_service.update_post(db, post_id, data, current_user)
    return ForumPostResponse.model_validate(post)


@router.delete("/forum/posts/{post_id}", response_model=ForumPostResponse)
def delete_post(
    post_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ForumPostResponse:
    """
    Delete (soft-delete) a forum post. Allowed for the post's author, any
    moderator, or an admin.
    """
    post = forum_service.delete_post(db, post_id, current_user)
    return ForumPostResponse.model_validate(post)


@router.post(
    "/forum/broadcast",
    response_model=ForumPostResponse,
    status_code=201,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
def create_broadcast(
    data: BroadcastCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ForumPostResponse:
    """
    Publish an admin broadcast post, visible to all users regardless of
    group or sector.
    """
    post = forum_service.create_broadcast_post(db, data, current_user)
    return ForumPostResponse.model_validate(post)


@router.post(
    "/forum/posts/{post_id}/report", response_model=ReportResponse, status_code=201
)
def report_post(
    post_id: str,
    data: ReportCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """
    Report a forum post. Rejects if the body's target doesn't match the
    route's post_id, rather than silently overriding it. target_type support
    is validated by report_service.file_report() itself.
    """
    if data.target_id != post_id:
        raise HTTPException(
            status_code=400, detail="נתוני הדיווח אינם תואמים את ההודעה המבוקשת."
        )
    report = report_service.file_report(db, data, current_user)
    return ReportResponse.model_validate(report)


# ──────────────────────────────────────────────────────────
# Direct messages
# ──────────────────────────────────────────────────────────


@router.get("/messages", response_model=ConversationListResponse)
def get_inbox(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    """
    Return the current user's conversations (inbox view), most recent first.
    """
    return forum_service.get_inbox(db, current_user, page, page_size)


@router.post("/messages", response_model=DirectMessageSendResponse, status_code=201)
def send_message(
    data: DirectMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> DirectMessageSendResponse:
    """
    Send a private message to another member of your own cell.

    The response carries the stored message plus `pruned_message_ids` — which
    of the conversation's oldest messages spec §5.3's 1,000 cap cost this send
    — and `conversation_limit`, the cap itself. Ids rather than a count
    because the messages that go are the oldest *prunable* ones: anything
    under an open report is skipped, so a client trimming the top of its list
    by count would drop the wrong ones and keep showing a deleted message.
    """
    result = forum_service.send_direct_message(db, data, current_user)
    return DirectMessageSendResponse.model_validate(result)


@router.get(
    "/conversations/{conversation_key}/messages",
    response_model=ConversationMessagesPage,
)
def get_conversation_messages(
    conversation_key: str,
    limit: int = Query(
        forum_service.CONVERSATION_PAGE_SIZE,
        ge=1,
        le=forum_service.CONVERSATION_MAX_PAGE_SIZE,
    ),
    before: str | None = Query(
        None,
        description="A next_cursor from an earlier page; omit for the newest messages.",
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ConversationMessagesPage:
    """
    Return one page of a conversation, oldest first within the page.

    Omit `before` for the newest page — the one a chat screen opens on — then
    feed each response's `next_cursor` back as `before` to walk backwards
    through the history.

    Marking read (ABF-119) happens only on that first request. Opening a
    conversation is what says "I have seen this"; scrolling back through
    history is a read of content the user has already been shown, and issuing
    a write on every scroll page would be both pointless and, on a long
    scroll, expensive. The two calls stay separate because
    get_conversation_messages() is a pure read.
    """
    if before is None:
        forum_service.mark_conversation_read(db, current_user, conversation_key)
    page = forum_service.get_conversation_messages(
        db, current_user, conversation_key, limit=limit, before=before
    )
    return ConversationMessagesPage.model_validate(page)


@router.get("/cells/me/members", response_model=list[UserPublic])
def get_my_cell_members(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> list[UserPublic]:
    """
    List other ACTIVE users in the current user's own cell (group+sector) —
    the entry point for starting a private conversation.
    """
    members = forum_service.get_cell_members(db, current_user)
    return [UserPublic.model_validate(member) for member in members]

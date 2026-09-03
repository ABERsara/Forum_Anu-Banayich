"""
Pydantic schemas for forum posts and direct messages.
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import GroupVisibility, PostStatus, SectorVisibility
from app.schemas.user import UserPublic


class ForumPostCreate(BaseModel):
    """POST /forum/posts – create a new forum post."""

    title: str = Field(..., min_length=2, max_length=256)
    content: str = Field(..., min_length=1, max_length=5000)
    group_visibility: GroupVisibility
    sector_visibility: SectorVisibility
    # attachment_url is set by the backend after upload – not sent by the client directly


class ForumPostUpdate(BaseModel):
    """PATCH /forum/posts/{id} – edit an existing post's title and/or content."""

    title: str | None = Field(None, min_length=2, max_length=256)
    content: str | None = Field(None, min_length=1, max_length=5000)


class BroadcastCreate(BaseModel):
    """POST /forum/broadcast – admin-only post visible to all users."""

    title: str = Field(..., min_length=2, max_length=256)
    content: str = Field(..., min_length=1, max_length=5000)


class ForumPostResponse(BaseModel):
    """Single post as returned to the client."""

    id: str
    title: str
    content: str
    group_visibility: GroupVisibility
    sector_visibility: SectorVisibility
    status: PostStatus
    report_count: int
    author: UserPublic
    attachment_url: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ForumPostListResponse(BaseModel):
    """Paginated list of posts."""

    items: list[ForumPostResponse]
    total: int
    page: int
    page_size: int


class DirectMessageCreate(BaseModel):
    """POST /messages – send a direct message."""

    recipient_id: str
    content: str = Field(..., min_length=1, max_length=2000)


class DirectMessageResponse(BaseModel):
    """
    One message as both participants see it.

    `read_at` is null until the RECIPIENT opens the conversation. It is the
    only read state on the wire — the sender reads it as the receipt on her
    own bubble, the recipient as "this was already mine to read".
    """

    id: str
    sender: UserPublic
    recipient: UserPublic
    content: str
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DirectMessageSendResponse(BaseModel):
    """
    POST /messages – the stored message, plus what enforcing the storage cap
    cost this conversation.

    `pruned_message_ids` is normally empty, and holds one id on the send that
    crosses spec section 5.3's cap. It is on the send response rather than
    left implicit because the acceptance criterion is that the user is *told*
    an old message was dropped; a screen cannot say so if the API does not.

    Ids rather than a count: the messages deleted are the oldest *prunable*
    ones, which is not the same as the oldest ones — anything under an open
    report is skipped. A client that trimmed by count would take the wrong
    messages off the screen.

    `conversation_limit` travels with them so the notice can name the real
    number instead of hardcoding a copy of a server setting.
    """

    message: DirectMessageResponse
    pruned_message_ids: list[str]
    conversation_limit: int


class ConversationMessagesPage(BaseModel):
    """
    GET /conversations/{key}/messages – one page of history, oldest first.

    Cursor-based, not offset-based: a conversation grows from the newest end
    while the reader pages towards the oldest, and an offset counted from a
    moving end re-reads or skips rows every time a message arrives mid-scroll.
    A cursor names a row, so it keeps meaning whatever arrives after it.

    `next_cursor` points *older* — feed it back as `before` for the previous
    page. It is null exactly when `has_more` is false.
    """

    items: list[DirectMessageResponse]
    has_more: bool
    next_cursor: str | None


class ConversationSummary(BaseModel):
    """One entry in the inbox – shows the other person and last message snippet."""

    other_user: UserPublic
    last_message_preview: str
    last_message_at: datetime
    unread_count: int


class ConversationListResponse(BaseModel):
    """Paginated inbox – one entry per conversation, most recent first."""

    items: list[ConversationSummary]
    total: int
    page: int
    page_size: int

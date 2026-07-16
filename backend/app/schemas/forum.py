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
    id: str
    sender: UserPublic
    recipient: UserPublic
    content: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationSummary(BaseModel):
    """One entry in the inbox – shows the other person and last message snippet."""

    other_user: UserPublic
    last_message_preview: str
    last_message_at: datetime
    unread_count: int

"""
Forum service.

⚠️  CRITICAL: Every query that returns content MUST apply the content filter.
    Never return posts that don't match the user's group+sector.
    The filter must be on the DB side – not in Python code after fetching all rows.

TODO list for junior developer:
  [ ] implement get_posts() – with content filter + pagination
  [ ] implement get_post_by_id() – verify user can see it
  [ ] implement search_users_for_dm() – name search within same group/sector
"""

from datetime import datetime
from typing import TypedDict

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    LikeTargetType,
    PostStatus,
    SectorVisibility,
    UserRole,
)
from app.core.encryption import decrypt_message, encrypt_message
from app.models.forum import DirectMessage, ForumPost
from app.models.like import Like
from app.models.user import User
from app.schemas.forum import (
    BroadcastCreate,
    DirectMessageCreate,
    ForumPostCreate,
    ForumPostListResponse,
    ForumPostResponse,
    ForumPostUpdate,
)
from app.services.audit_service import log_action
from app.services.user_service import get_user_by_id

#: Generic 403 for anything DM-permission-related — never distinguishes
#: "wrong role", "wrong cell", or "no such user", per the DoD rule that a
#: denial must not leak whether a user or conversation exists.
#: A translation key, not display text — i18n DoD requires server errors to
#: come back as a key the client resolves via Transloco (he/en), not
#: hardcoded Hebrew.
_DM_FORBIDDEN_MESSAGE = "errors.dm_forbidden"


class DirectMessageData(TypedDict):
    """A decrypted DirectMessage row, shaped for DirectMessageResponse."""

    id: str
    sender: User
    recipient: User
    content: str
    is_read: bool
    created_at: datetime


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

    # like_count/liked_by_me are aggregated here via subqueries rather than
    # per-row, to avoid an N+1 query per post in the page. Imported locally
    # (not at module level) to avoid a circular import: like_service already
    # imports forum_service for _matches_content_filter().
    from app.services import like_service

    like_counts, my_likes = like_service.like_annotations(
        db, LikeTargetType.FORUM_POST, current_user
    )

    rows = (
        query.add_columns(
            func.coalesce(like_counts.c.like_count, 0).label("like_count"),
            my_likes.c.target_id.isnot(None).label("liked_by_me"),
        )
        .outerjoin(like_counts, like_counts.c.target_id == ForumPost.id)
        .outerjoin(my_likes, my_likes.c.target_id == ForumPost.id)
        .order_by(ForumPost.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [
        ForumPostResponse.model_validate(post).model_copy(
            update={"like_count": like_count, "liked_by_me": liked_by_me}
        )
        for post, like_count, liked_by_me in rows
    ]

    return ForumPostListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


def _matches_content_filter(post: ForumPost, current_user: User) -> bool:
    """
    Python-side equivalent of _content_filter(), for checking a single
    already-loaded post instead of querying again. Keep the two in sync —
    same group/sector OR-logic, just evaluated in memory vs. compiled to SQL.
    """
    assert current_user.user_type is not None, (
        "_matches_content_filter() requires a user with user_type set"
    )
    assert current_user.sector is not None, (
        "_matches_content_filter() requires a user with sector set"
    )
    group_visibility = GroupVisibility(current_user.user_type.value)
    sector_visibility = SectorVisibility(current_user.sector.value)
    return post.group_visibility in (group_visibility, GroupVisibility.ALL) and (
        post.sector_visibility in (sector_visibility, SectorVisibility.ALL)
    )


def get_post_by_id(db: Session, post_id: str, current_user: User) -> ForumPost:
    """
    Return a single post.

    Visibility rules (deliberately different from get_posts()'s list view):
      - ADMIN sees any status, including DELETED.
      - MODERATOR sees VISIBLE and HIDDEN (not DELETED), for any group/sector –
        bypasses the content filter, since moderators don't have user_type/sector set.
      - USER sees only VISIBLE posts within their own group/sector (content filter applies).

    Raises 404 if the post doesn't exist, or exists but this user shouldn't know that
    (wrong status for their role). Raises 403 if the post is VISIBLE but the user's
    group/sector don't match (the post exists, they just can't read it).
    """
    if current_user.role not in (UserRole.USER, UserRole.ADMIN, UserRole.MODERATOR):
        raise HTTPException(status_code=403, detail="אין לך הרשאה לגשת לפורום הקהילתי.")

    post = (
        db.query(ForumPost)
        .options(joinedload(ForumPost.author))
        .filter(ForumPost.id == post_id)
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")

    if current_user.role in (UserRole.ADMIN, UserRole.MODERATOR):
        if post.status == PostStatus.DELETED and current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")
        return _attach_like_fields(db, post, current_user)

    # הגענו לכאן רק אם role == USER (ADMIN/MODERATOR תמיד יוצאים למעלה, עם return או raise)
    if post.status != PostStatus.VISIBLE:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")

    if not _matches_content_filter(post, current_user):
        raise HTTPException(status_code=403, detail="אין לך הרשאה לצפות בהודעה זו.")

    return _attach_like_fields(db, post, current_user)


def _attach_like_fields(db: Session, post: ForumPost, current_user: User) -> ForumPost:
    """
    Set like_count/liked_by_me as plain (unmapped) attributes on an
    already-fetched post, for get_post_by_id() to return a single post
    outside get_posts()'s paginated-subquery path. ForumPostResponse picks
    these up via getattr (from_attributes=True) same as any mapped column.

    One query with conditional aggregation, not two separate COUNTs — same
    row set scanned once for both numbers.
    """
    like_count, liked_by_me = (
        db.query(
            func.count(Like.user_id),
            func.max(case((Like.user_id == current_user.id, 1), else_=0)),
        )
        .filter(
            Like.target_type == LikeTargetType.FORUM_POST, Like.target_id == post.id
        )
        .one()
    )
    post.like_count = like_count  # type: ignore[attr-defined]
    post.liked_by_me = bool(liked_by_me)  # type: ignore[attr-defined]
    return post


def delete_post(db: Session, post_id: str, current_user: User) -> ForumPost:
    """
    Soft-delete a forum post (status -> DELETED).

    Permission: the post's author, any moderator, or an admin. Moderators are
    NOT currently restricted to their own moderator_cells here – see the
    ABF-45 notes: that restriction is expected to live in the reports-triage
    layer once it's implemented, not in this function.

    Idempotent: deleting an already-deleted post is a no-op (returns the post
    as-is, no error, no duplicate audit log entry) rather than an error.
    """
    # Row-level lock: two people (e.g. the author and a moderator) hitting
    # delete at the same time must not race on the same status update.
    # No-op on SQLite (dev), enforced on PostgreSQL (production).
    #
    # joinedload(author) avoids a second (lazy-load) query when the response
    # is serialized later - log_action()'s commit expires `post`, and
    # db.refresh() below only reloads ForumPost's own columns, not author.
    # with_for_update(of=ForumPost) keeps the lock scoped to forum_posts only
    # - without `of=`, FOR UPDATE on a query with a JOIN locks every table in
    # it, which would lock the author's User row for no reason.
    post = (
        db.query(ForumPost)
        .options(joinedload(ForumPost.author))
        .filter(ForumPost.id == post_id)
        .with_for_update(of=ForumPost)
        .first()
    )
    if post is None:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")

    is_author = current_user.id == post.author_id
    is_privileged = current_user.role in (UserRole.MODERATOR, UserRole.ADMIN)
    if not (is_author or is_privileged):
        raise HTTPException(status_code=403, detail="אין לך הרשאה למחוק הודעה זו.")

    if post.status == PostStatus.DELETED:
        # Already deleted - nothing to do, and nothing new to audit-log.
        return post

    post.status = PostStatus.DELETED

    # log_action() calls db.commit() internally - this both writes the audit
    # entry AND persists the post.status change above. There's no separate
    # db.commit() in this function because of that.
    log_action(
        db,
        actor=current_user,
        action=AuditAction.POST_DELETED,
        entity_type="ForumPost",
        entity_id=post.id,
        details={
            "author_id": post.author_id,
            "deleted_by_role": current_user.role.value,
        },
    )
    db.refresh(post)

    return post


def create_post(db: Session, data: ForumPostCreate, author: User) -> ForumPost:
    """
    Create a new forum post.

    Validations:
      - Author must be ACTIVE
      - If group_visibility targets a specific group, it must match author's user_type
        (a widow cannot post in the widowers group)
    """
    if author.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="רק משתמש פעיל יכול לפרסם הודעה.")

    is_broadcast = (
        data.group_visibility == GroupVisibility.ALL
        and data.sector_visibility == SectorVisibility.ALL
    )
    if is_broadcast and author.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403, detail="רק מנהל יכול לפרסם הודעה לכלל המשתמשים."
        )

    if data.group_visibility != GroupVisibility.ALL and (
        author.user_type is None
        or data.group_visibility != GroupVisibility(author.user_type.value)
    ):
        raise HTTPException(
            status_code=403, detail="לא ניתן לפרסם הודעה לקבוצה שאינה שלך."
        )

    if data.sector_visibility != SectorVisibility.ALL and (
        author.sector is None
        or data.sector_visibility != SectorVisibility(author.sector.value)
    ):
        raise HTTPException(
            status_code=403, detail="לא ניתן לפרסם הודעה למגזר שאינו שלך."
        )

    post = ForumPost(
        author_id=author.id,
        title=data.title,
        content=data.content,
        group_visibility=data.group_visibility,
        sector_visibility=data.sector_visibility,
        status=PostStatus.VISIBLE,
    )
    db.add(post)
    db.commit()

    return (
        db.query(ForumPost)
        .options(joinedload(ForumPost.author))
        .filter(ForumPost.id == post.id)
        .one()
    )


def update_post(
    db: Session, post_id: str, data: ForumPostUpdate, current_user: User
) -> ForumPost:
    """
    Edit an existing post's title and/or content.

    Permission: author only. Editing a deleted post is treated as not-found,
    matching get_post_by_id()'s "don't reveal deleted posts" behavior.
    """
    post = (
        db.query(ForumPost)
        .options(joinedload(ForumPost.author))
        .filter(ForumPost.id == post_id)
        .with_for_update(of=ForumPost)
        .first()
    )
    if post is None or post.status == PostStatus.DELETED:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")

    if current_user.id != post.author_id:
        raise HTTPException(status_code=403, detail="רק המחבר יכול לערוך הודעה זו.")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(post, field, value)

    db.commit()
    db.refresh(post)

    return post


def create_broadcast_post(db: Session, data: BroadcastCreate, admin: User) -> ForumPost:
    """
    Create an admin broadcast post – visible to every active user
    regardless of group or sector.
    """
    post = ForumPost(
        author_id=admin.id,
        group_visibility=GroupVisibility.ALL,
        sector_visibility=SectorVisibility.ALL,
        title=data.title,
        content=data.content,
        status=PostStatus.VISIBLE,
    )
    db.add(post)
    db.flush()

    log_action(
        db,
        actor=admin,
        action=AuditAction.BROADCAST_SENT,
        entity_type="ForumPost",
        entity_id=post.id,
        details={"title": data.title},
    )

    db.refresh(post)
    return post


def can_message(sender: User, recipient: User) -> bool:
    """
    Single source of truth for "may sender privately message recipient".

    True only if both are USER-role, both ACTIVE, and they're in the same
    "cell" — spec §4.1's group×sector intersection (both axes, not just
    group: §3.2's permission table row reads "לקבוצתו" loosely, but §5.3
    pins the real rule as "בתוך קבוצתו/מגזרו" — within his group AND
    sector).
    """
    return (
        sender.role == UserRole.USER
        and recipient.role == UserRole.USER
        and sender.account_status == AccountStatus.ACTIVE
        and recipient.account_status == AccountStatus.ACTIVE
        and sender.user_type is not None
        and recipient.user_type is not None
        and sender.user_type == recipient.user_type
        and sender.sector is not None
        and recipient.sector is not None
        and sender.sector == recipient.sector
    )


def build_conversation_key(user_id_a: str, user_id_b: str) -> str:
    """
    Deterministic key for the pair, independent of who is sender/recipient.

    No "conversation" entity exists in the spec (§5.3 only talks about a cap
    of 1,000 messages "per conversation") — this is what groups a pair's
    messages instead of introducing one. Not a secret: both participants
    already know each other's id from the cell-members list, so this can
    (and does, in the frontend) get recomputed client-side identically.
    """
    first, second = sorted((user_id_a, user_id_b))
    return f"{first}:{second}"


def _parse_conversation_key(conversation_key: str) -> tuple[str, str] | None:
    """Split a conversation_key back into its two participant ids."""
    parts = conversation_key.split(":")
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def _to_response_dict(message: DirectMessage) -> DirectMessageData:
    """
    Decrypt one row's content for the API response layer.

    Returns a plain dict rather than mutating message.content in place: this
    ORM instance may still be session-tracked, and writing the decrypted
    plaintext into a tracked attribute risks it being flushed back to the DB
    on some later, unrelated commit — silently replacing the encrypted
    content. A dict can't have that accident.

    AES-GCM's InvalidTag means the stored row failed authentication (DB
    corruption, or content encrypted under a different key) — surfaced as a
    generic 500 rather than propagating, so the failure detail (and the fact
    that it's specifically a decryption failure) never reaches the client.
    """
    try:
        content = decrypt_message(message.content, message.key_version)
    except InvalidTag as exc:
        raise HTTPException(
            status_code=500, detail="errors.internal_server_error"
        ) from exc

    return {
        "id": message.id,
        "sender": message.sender,
        "recipient": message.recipient,
        "content": content,
        "is_read": message.is_read,
        "created_at": message.created_at,
    }


def send_direct_message(
    db: Session, data: DirectMessageCreate, sender: User
) -> DirectMessageData:
    """
    Send a private message within the sender's own cell.

    Never distinguishes "recipient doesn't exist" from "recipient exists but
    can't be messaged" (wrong cell, wrong role, inactive) — both return the
    same generic 403, per the DoD rule against leaking user existence. Also
    covers the sender's own role: a non-USER sender is denied and audited
    the same way as any other blocked send (§9.3 — a moderator's attempt to
    send a private message is itself an access to private content).
    """
    recipient = (
        None if sender.role != UserRole.USER else get_user_by_id(db, data.recipient_id)
    )
    if recipient is None or not can_message(sender, recipient):
        log_action(
            db,
            actor=sender,
            action=AuditAction.DIRECT_MESSAGE_ACCESS_DENIED,
            entity_type="DirectMessage",
            entity_id=data.recipient_id,
            details={"reason": "send_blocked"},
        )
        raise HTTPException(status_code=403, detail=_DM_FORBIDDEN_MESSAGE)

    encrypted_content, key_version = encrypt_message(data.content)
    message = DirectMessage(
        sender_id=sender.id,
        recipient_id=recipient.id,
        conversation_key=build_conversation_key(sender.id, recipient.id),
        content=encrypted_content,
        key_version=key_version,
    )
    db.add(message)
    db.commit()

    message = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.recipient))
        .filter(DirectMessage.id == message.id)
        .one()
    )
    return _to_response_dict(message)


def get_conversation_messages(
    db: Session, current_user: User, conversation_key: str
) -> list[DirectMessageData]:
    """
    Return every message for a conversation_key, oldest first.

    No pagination (out of scope — spec §5.3's 1,000/conversation cap isn't
    enforced here either) and no is_read mutation (marking as read is out of
    scope for this ticket, despite this function's old TODO comment).

    A well-formed key for a conversation with zero messages yet returns an
    empty list (200), not 404 — "no messages" is a normal empty state, not
    an error. What's checked is the caller's role and whether current_user
    is one of the two participants encoded in the key; wrong role, a
    malformed key, or one that doesn't include current_user all get the
    same generic 403 — and the same audit log entry (§9.3: any attempted
    access to private content that isn't the caller's own must be logged,
    including denied attempts).
    """
    parsed = _parse_conversation_key(conversation_key)
    if (
        current_user.role != UserRole.USER
        or parsed is None
        or current_user.id not in parsed
    ):
        log_action(
            db,
            actor=current_user,
            action=AuditAction.DIRECT_MESSAGE_ACCESS_DENIED,
            entity_type="DirectMessage",
            entity_id=conversation_key,
            details={"reason": "read_blocked"},
        )
        raise HTTPException(status_code=403, detail=_DM_FORBIDDEN_MESSAGE)

    messages = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.recipient))
        .filter(DirectMessage.conversation_key == conversation_key)
        .order_by(DirectMessage.created_at.asc())
        .all()
    )
    return [_to_response_dict(message) for message in messages]


def get_cell_members(db: Session, current_user: User) -> list[User]:
    """
    List every other ACTIVE user in current_user's own cell (group+sector).

    Name only (UserPublic drops everything else) — same "no PII beyond name"
    rule as the rest of this file. This is a plain list, not the spec's
    by-name search (§5.3) — search is explicitly out of scope for this
    ticket; that's a separate, still-unimplemented feature
    (search_users_for_dm / GET /users/search).
    """
    if current_user.role != UserRole.USER:
        log_action(
            db,
            actor=current_user,
            action=AuditAction.DIRECT_MESSAGE_ACCESS_DENIED,
            entity_type="DirectMessage",
            entity_id=current_user.id,
            details={"reason": "cell_members_role_blocked"},
        )
        raise HTTPException(status_code=403, detail=_DM_FORBIDDEN_MESSAGE)

    return (
        db.query(User)
        .filter(
            User.id != current_user.id,
            User.role == UserRole.USER,
            User.account_status == AccountStatus.ACTIVE,
            User.user_type == current_user.user_type,
            User.sector == current_user.sector,
        )
        .order_by(User.first_name, User.last_name)
        .all()
    )


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

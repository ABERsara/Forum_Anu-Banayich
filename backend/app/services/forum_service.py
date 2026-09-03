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

import base64
import binascii
from datetime import UTC, datetime
from typing import TypedDict

from cryptography.exceptions import InvalidTag
from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Query, Session, joinedload

from app.core.config import settings
from app.core.constants import (
    AccountStatus,
    AuditAction,
    GroupVisibility,
    PostStatus,
    ReportDecision,
    ReportTargetType,
    SectorVisibility,
    UserRole,
)
from app.core.encryption import decrypt_message, encrypt_message
from app.models.forum import DirectMessage, ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.forum import (
    BroadcastCreate,
    ConversationListResponse,
    ConversationSummary,
    DirectMessageCreate,
    ForumPostCreate,
    ForumPostListResponse,
    ForumPostResponse,
    ForumPostUpdate,
)
from app.schemas.user import UserPublic
from app.services.audit_service import log_action
from app.services.user_service import get_user_by_id

#: Generic 403 for anything DM-permission-related — never distinguishes
#: "wrong role", "wrong cell", or "no such user", per the DoD rule that a
#: denial must not leak whether a user or conversation exists.
#: A translation key, not display text — i18n DoD requires server errors to
#: come back as a key the client resolves via Transloco (he/en), not
#: hardcoded Hebrew.
_DM_FORBIDDEN_MESSAGE = "errors.dm_forbidden"

#: A history cursor the server did not issue. A translation key too, for the
#: same reason as _DM_FORBIDDEN_MESSAGE above.
_INVALID_CURSOR_MESSAGE = "errors.invalid_cursor"


#: Default and maximum number of messages one history request returns. The
#: default is a screenful and then some; the maximum bounds how much content
#: a single request can be made to decrypt.
CONVERSATION_PAGE_SIZE = 50
CONVERSATION_MAX_PAGE_SIZE = 100

#: Separates the two halves of a history cursor before base64 — see
#: _encode_cursor(). ':' is taken by conversation_key, '|' never appears in an
#: ISO timestamp or a uuid4.
_CURSOR_SEPARATOR = "|"


class DirectMessageData(TypedDict):
    """A decrypted DirectMessage row, shaped for DirectMessageResponse."""

    id: str
    sender: User
    recipient: User
    content: str
    read_at: datetime | None
    created_at: datetime


class ConversationPageData(TypedDict):
    """One page of history, shaped for ConversationMessagesPage."""

    items: list[DirectMessageData]
    has_more: bool
    next_cursor: str | None


class SentMessageData(TypedDict):
    """A stored message plus the cost of enforcing the cap, for
    DirectMessageSendResponse."""

    message: DirectMessageData
    pruned_count: int
    conversation_limit: int


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
        return post

    # הגענו לכאן רק אם role == USER (ADMIN/MODERATOR תמיד יוצאים למעלה, עם return או raise)
    if post.status != PostStatus.VISIBLE:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה.")

    if not _matches_content_filter(post, current_user):
        raise HTTPException(status_code=403, detail="אין לך הרשאה לצפות בהודעה זו.")

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
        "read_at": message.read_at,
        "created_at": message.created_at,
    }


def send_direct_message(
    db: Session, data: DirectMessageCreate, sender: User
) -> SentMessageData:
    """
    Send a private message within the sender's own cell.

    Never distinguishes "recipient doesn't exist" from "recipient exists but
    can't be messaged" (wrong cell, wrong role, inactive) — both return the
    same generic 403, per the DoD rule against leaking user existence. Also
    covers the sender's own role: a non-USER sender is denied and audited
    the same way as any other blocked send (§9.3 — a moderator's attempt to
    send a private message is itself an access to private content).

    The new message is stored first and the cap enforced after, never the
    other way round: pruning ahead of a send that then fails validation would
    delete history to make room for nothing.
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

    conversation_key = build_conversation_key(sender.id, recipient.id)
    encrypted_content, key_version = encrypt_message(data.content)
    message = DirectMessage(
        sender_id=sender.id,
        recipient_id=recipient.id,
        conversation_key=conversation_key,
        content=encrypted_content,
        key_version=key_version,
    )
    db.add(message)
    db.commit()

    message_id = message.id
    pruned_count = _enforce_conversation_limit(
        db, sender, conversation_key, keep_message_id=message_id
    )

    message = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.recipient))
        .filter(DirectMessage.id == message_id)
        .one()
    )
    return {
        "message": _to_response_dict(message),
        "pruned_count": pruned_count,
        "conversation_limit": settings.MAX_MESSAGES_PER_CONVERSATION,
    }


def _enforce_conversation_limit(
    db: Session, actor: User, conversation_key: str, keep_message_id: str
) -> int:
    """
    Hold the conversation at spec §5.3's cap of 1,000 messages, and return how
    many were deleted to do it.

    FIFO — oldest first — with two messages it will never touch:

    * `keep_message_id`, the message this send just stored. It is the newest
      row, so FIFO reaches it last and normally never; but when every older
      message is exempt it would be the only candidate left, and a send that
      deletes its own message is the one outcome that is never right.
    * anything carrying an **open** report (decision PENDING). A moderator can
      only ever see a private message that was reported to them (§5.3), so
      pruning a reported message would destroy the evidence before the report
      is ruled on. Once the report is decided the message is ordinary history
      again, so the exemption expires by itself.

    Those exemptions make the cap a target rather than an invariant: a
    conversation whose oldest messages are all under open report grows past
    1,000 instead of deleting them, and shrinks back once they are decided.

    Normally deletes exactly one row — the cap is checked on every send, so a
    conversation can only ever be one over. The loop is for a conversation
    that arrived over the cap another way (a restored backup, a lowered cap).

    Deletion is permanent and it is the user's own content, so each removed
    message gets its own audit entry (§9.3) — never with the content in it,
    which is exactly what an audit log must not carry.
    """
    limit = settings.MAX_MESSAGES_PER_CONVERSATION
    total = (
        db.query(func.count(DirectMessage.id))
        .filter(DirectMessage.conversation_key == conversation_key)
        .scalar()
        or 0
    )
    overflow = total - limit
    if overflow <= 0:
        return 0

    reported_message_ids = (
        db.query(Report.target_id)
        .filter(
            Report.target_type == ReportTargetType.DIRECT_MESSAGE,
            Report.decision == ReportDecision.PENDING,
        )
        .scalar_subquery()
    )
    doomed = (
        db.query(DirectMessage)
        .filter(
            DirectMessage.conversation_key == conversation_key,
            DirectMessage.id != keep_message_id,
            DirectMessage.id.notin_(reported_message_ids),
        )
        .order_by(DirectMessage.created_at.asc(), DirectMessage.id.asc())
        .limit(overflow)
        .all()
    )

    for message in doomed:
        message_id = message.id
        db.delete(message)
        log_action(
            db,
            actor=actor,
            action=AuditAction.DIRECT_MESSAGE_PRUNED,
            entity_type="DirectMessage",
            entity_id=message_id,
            details={"conversation_key": conversation_key, "reason": "storage_cap"},
        )

    return len(doomed)


def _authorize_conversation_access(
    db: Session, current_user: User, conversation_key: str
) -> None:
    """
    Shared guard for both reading and marking-read a conversation: the
    caller must be USER role AND one of the two participants encoded in
    conversation_key. A malformed key, wrong role, or non-participant all
    get the same generic 403 and the same audit log entry (§9.3: any
    attempted access to private content that isn't the caller's own must be
    logged, including denied attempts) — none of these are distinguishable
    to the caller.
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


def mark_conversation_read(
    db: Session, current_user: User, conversation_key: str
) -> None:
    """
    Mark every message *sent to* current_user in this conversation as read.

    A separate, explicit write step (ABF-119 code review) rather than a side
    effect buried inside get_conversation_messages() — a function named
    get_* should stay a safe, idempotent read. The router calls this first,
    then get_conversation_messages() to fetch the now-up-to-date history.
    Idempotent by construction: calling it again just finds nothing left to
    update.

    `recipient_id == current_user.id` is the whole of the acceptance criterion
    "a sender never marks her own message read": that filter is what keeps the
    receipt on the sender's own bubble honest, because since ABF-120 read_at is
    shown back to her. Drop it and every message would light up as read the
    moment its author opened the thread.

    Already-read messages keep their original read_at (`read_at IS NULL` in the
    filter) — re-opening a conversation must not move the timestamp of a
    message that was read yesterday.
    """
    _authorize_conversation_access(db, current_user, conversation_key)

    db.query(DirectMessage).filter(
        DirectMessage.conversation_key == conversation_key,
        DirectMessage.recipient_id == current_user.id,
        DirectMessage.read_at.is_(None),
    ).update({"read_at": datetime.now(UTC).replace(tzinfo=None)})
    db.commit()


def _encode_cursor(message: DirectMessage) -> str:
    """
    Name one row in the conversation's ordering, as an opaque string.

    The pair (created_at, id) — not created_at alone, and not an offset. Two
    messages can share a timestamp, so the id is what makes the ordering a
    total one; without it a page boundary landing inside a tie repeats a
    message on one page and drops it from the next, which is precisely the
    "no duplicates" acceptance criterion.

    base64 because a cursor is not the client's to build: only a value this
    function produced is a valid one.
    """
    raw = f"{message.created_at.isoformat()}{_CURSOR_SEPARATOR}{message.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """
    Read a cursor back into (created_at, id).

    Anything unreadable is a 400 with a translation key — not a 500, and not a
    silent fall back to "start from the newest": a client paging with a
    corrupted cursor should be told, not quietly served the top of the list
    again forever.
    """
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        created_at_text, message_id = raw.split(_CURSOR_SEPARATOR, 1)
        return datetime.fromisoformat(created_at_text), message_id
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=_INVALID_CURSOR_MESSAGE) from exc


def get_conversation_messages(
    db: Session,
    current_user: User,
    conversation_key: str,
    limit: int = CONVERSATION_PAGE_SIZE,
    before: str | None = None,
) -> ConversationPageData:
    """
    Return one page of a conversation's history, oldest first *within the page*.

    Paging runs backwards through time: with no cursor the newest `limit`
    messages come back (what a chat screen opens on), and `next_cursor` walks
    towards the oldest. Ordering by (created_at, id) descending and slicing on
    that same pair is what keeps a page seam stable while new messages keep
    arriving at the other end — an offset counted from a list that grows at
    the top re-serves or skips a row on every new arrival.

    Pure read, no side effects — see mark_conversation_read() for marking
    messages read.

    A well-formed key for a conversation with no messages yet returns an empty
    page (200), not 404 — "no messages" is a normal empty state, not an error.
    """
    _authorize_conversation_access(db, current_user, conversation_key)

    query = (
        db.query(DirectMessage)
        .options(joinedload(DirectMessage.sender), joinedload(DirectMessage.recipient))
        .filter(DirectMessage.conversation_key == conversation_key)
    )

    if before is not None:
        cursor_created_at, cursor_id = _decode_cursor(before)
        # Spelled out as OR/AND rather than a row-value comparison so the same
        # expression compiles on both databases: SQLite only learned row
        # values in 3.15, and SQLite is this app's dev database.
        query = query.filter(
            or_(
                DirectMessage.created_at < cursor_created_at,
                and_(
                    DirectMessage.created_at == cursor_created_at,
                    DirectMessage.id < cursor_id,
                ),
            )
        )

    # One row more than asked for: its presence *is* has_more, and it is
    # dropped rather than returned. Cheaper than a second COUNT(*), and it
    # cannot disagree with the page it describes the way a separate count can.
    rows = (
        query.order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    page = list(reversed(rows[:limit]))

    return {
        "items": [_to_response_dict(message) for message in page],
        "has_more": has_more,
        # The cursor is the page's OLDEST row — the next request asks for what
        # comes before it. Null when nothing older exists, so a client that
        # only looks at the cursor cannot loop forever.
        "next_cursor": _encode_cursor(page[0]) if has_more and page else None,
    }


def get_inbox(
    db: Session, current_user: User, page: int = 1, page_size: int = 20
) -> ConversationListResponse:
    """
    Return the current user's conversations, most recent message first.

    One query does the heavy lifting: a ROW_NUMBER() window picks each
    conversation_key's newest row, and a SUM() window computes that
    conversation's unread count in the same pass — no per-conversation
    query, so the query count doesn't grow with how many conversations a
    user has (§ABF-119 AC). `total` costs one more small query
    (COUNT DISTINCT conversation_key); still a fixed two queries overall.

    Only the page's own rows get decrypted — bounded by page_size, never the
    full history. Never mutates is_read (that's mark_conversation_read()'s
    job) — merely listing conversations isn't "reading" one, only opening it
    is. No audit entry on success either, same asymmetry as
    get_conversation_messages() (only denied access is logged).
    """
    if current_user.role != UserRole.USER:
        log_action(
            db,
            actor=current_user,
            action=AuditAction.DIRECT_MESSAGE_ACCESS_DENIED,
            entity_type="DirectMessage",
            entity_id=current_user.id,
            details={"reason": "inbox_role_blocked"},
        )
        raise HTTPException(status_code=403, detail=_DM_FORBIDDEN_MESSAGE)

    me = current_user.id
    own_messages = or_(DirectMessage.sender_id == me, DirectMessage.recipient_id == me)

    partner_id = case(
        (DirectMessage.sender_id == me, DirectMessage.recipient_id),
        else_=DirectMessage.sender_id,
    ).label("partner_id")
    unread_flag = case(
        (and_(DirectMessage.recipient_id == me, DirectMessage.read_at.is_(None)), 1),
        else_=0,
    )

    ranked = (
        db.query(
            DirectMessage.content,
            DirectMessage.key_version,
            DirectMessage.created_at,
            partner_id,
            func.row_number()
            .over(
                partition_by=DirectMessage.conversation_key,
                order_by=DirectMessage.created_at.desc(),
            )
            .label("rn"),
            func.sum(unread_flag)
            .over(partition_by=DirectMessage.conversation_key)
            .label("unread_count"),
        )
        .filter(own_messages)
        .subquery()
    )

    rows = (
        db.query(
            ranked.c.content,
            ranked.c.key_version,
            ranked.c.created_at,
            ranked.c.unread_count,
            User,
        )
        .join(User, User.id == ranked.c.partner_id)
        .filter(ranked.c.rn == 1)
        .order_by(ranked.c.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    total = (
        db.query(DirectMessage.conversation_key).filter(own_messages).distinct().count()
    )

    items = [
        ConversationSummary(
            other_user=UserPublic.model_validate(partner),
            last_message_preview=decrypt_message(content, key_version),
            last_message_at=created_at,
            unread_count=int(unread_count),
        )
        for content, key_version, created_at, unread_count, partner in rows
    ]

    return ConversationListResponse(
        items=items, total=total, page=page, page_size=page_size
    )


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

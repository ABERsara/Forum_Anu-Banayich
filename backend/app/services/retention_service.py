"""
Message retention, deletion and export (ABF-117).

Two entry points:
  purge_expired_direct_messages() – the scheduled 3-year retention job
      (spec §5.3/§9.4).
  purge_user_direct_messages()    – the message side of self-service account
      deletion (spec §9.4/UC-08): unlike a forum post, a private message is
      deleted outright, never anonymised.

Both share one rule for a message under an open report, and it is the same
rule forum_service._enforce_conversation_limit() already applies to its own
pruning: a moderator can only ever see a private message that was reported
to them (§5.3), so deleting one out from under a PENDING report would
destroy the evidence before the report is decided.

export_user_direct_messages() is the read side (spec §9.5 – GDPR/Israeli
privacy-law right of access): every message the caller sent or received,
decrypted.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, TypedDict

from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.selectable import ScalarSelect

from app.core.config import settings
from app.core.constants import AuditAction, ReportDecision, ReportTargetType
from app.core.encryption import decrypt_message
from app.models.audit import AuditLog
from app.models.forum import DirectMessage
from app.models.report import Report
from app.models.user import User
from app.services.audit_service import build_entry

#: actor_id for an audit entry no human triggered. AuditLog.actor_id carries
#: no FK (see app/models/audit.py), so any string is a valid, permanent value.
SYSTEM_ACTOR_ID = "system"


def _pending_reported_message_ids(db: Session) -> ScalarSelect[str]:
    """
    Subquery of DirectMessage ids currently under an open (PENDING) report —
    the set neither retention function is allowed to delete outright.

    Mirrors forum_service._enforce_conversation_limit()'s own subquery
    exactly, so the two places that may delete a DirectMessage agree on what
    "open report" means.
    """
    return (
        db.query(Report.target_id)
        .filter(
            Report.target_type == ReportTargetType.DIRECT_MESSAGE,
            Report.decision == ReportDecision.PENDING,
        )
        .scalar_subquery()
    )


def purge_expired_direct_messages(db: Session) -> list[str]:
    """
    Delete every DirectMessage older than settings.DIRECT_MESSAGE_RETENTION_DAYS.

    Meant to be called by any scheduler (cron, GitHub Actions, etc.); it is a
    plain function so it can also be invoked directly from tests — same shape
    as user_service.escalate_overdue_registrations().

    Skips a message still under an open report (see module docstring); it is
    swept up on a later run once the report is decided one way or another.

    The deletes and their audit entries commit together in one transaction —
    same reasoning as _enforce_conversation_limit(): pairing each delete with
    a separately-committed log entry would leave a partial purge with an
    audit trail that no longer says what was actually deleted, if a failure
    hit partway through.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        days=settings.DIRECT_MESSAGE_RETENTION_DAYS
    )

    expired_ids = [
        row[0]
        for row in db.query(DirectMessage.id)
        .filter(
            DirectMessage.created_at < cutoff,
            DirectMessage.id.notin_(_pending_reported_message_ids(db)),
        )
        .all()
    ]
    if not expired_ids:
        return []

    entries = [
        AuditLog(
            actor_id=SYSTEM_ACTOR_ID,
            action=AuditAction.DIRECT_MESSAGE_PRUNED,
            entity_type="DirectMessage",
            entity_id=message_id,
            details={"reason": "retention_expired"},
        )
        for message_id in expired_ids
    ]
    db.query(DirectMessage).filter(DirectMessage.id.in_(expired_ids)).delete(
        synchronize_session=False
    )
    db.add_all(entries)
    db.commit()

    return expired_ids


class MessagePurgeResult(TypedDict):
    deleted_message_ids: list[str]
    closed_report_ids: list[str]


def purge_user_direct_messages(
    db: Session, user: User
) -> tuple[MessagePurgeResult, list[AuditLog]]:
    """
    Delete every DirectMessage `user` sent or received, as the message side
    of deleting their account (spec §9.4: private messages are deleted, not
    anonymised, unlike forum posts).

    A message under an open report needs one of two outcomes depending on
    which side of the report `user` is on. Only a message's two participants
    can ever see it (§3.2's "קריאת הודעות פרטיות" — owner only), so whoever
    filed a report on it must be one of them, and the model has no separate
    field naming which one that was:
      - `user` is the message's sender (spec's "נמחק המדווח-עליו" — the
        reported-on user is the one deleting their account): the content is
        the deleted account's own, so it is deleted along with everything
        else, and the report auto-closes as CLOSED_ACCOUNT_DELETED — there
        is nothing left to investigate.
      - `user` is the message's recipient (spec's "נמחקת המדווחת" — the
        reporter is the one deleting their account): the message is kept so
        a moderator can still rule on it, and the report stays PENDING. The
        reporter's own identity is anonymised for free once the caller
        scrubs `user`'s PII in the same transaction — nothing further is
        needed on the Report row itself.

    Returns the counts alongside the AuditLog entries built for them, and
    commits neither: the caller (user_service.delete_own_account) commits
    this together with the account's own PII scrub in one transaction, per
    audit_service.build_entry()'s convention for an atomic multi-row change.
    """
    messages = (
        db.query(DirectMessage)
        .filter(
            or_(
                DirectMessage.sender_id == user.id,
                DirectMessage.recipient_id == user.id,
            )
        )
        .all()
    )
    if not messages:
        return {"deleted_message_ids": [], "closed_report_ids": []}, []

    message_ids = [message.id for message in messages]
    open_reports = {
        report.target_id: report
        for report in db.query(Report)
        .filter(
            Report.target_type == ReportTargetType.DIRECT_MESSAGE,
            Report.target_id.in_(message_ids),
            Report.decision == ReportDecision.PENDING,
        )
        .all()
    }

    to_delete: list[str] = []
    closed_report_ids: list[str] = []
    entries: list[AuditLog] = []

    for message in messages:
        report = open_reports.get(message.id)
        if report is not None and message.sender_id != user.id:
            # `user` is the recipient who filed this report — keep the
            # evidence, leave the report open.
            continue

        to_delete.append(message.id)
        entries.append(
            build_entry(
                actor=user,
                action=AuditAction.DIRECT_MESSAGE_PRUNED,
                entity_type="DirectMessage",
                entity_id=message.id,
                details={"reason": "account_deleted"},
            )
        )
        if report is not None:
            report.decision = ReportDecision.CLOSED_ACCOUNT_DELETED
            report.decided_at = datetime.now(UTC).replace(tzinfo=None)
            closed_report_ids.append(report.id)
            entries.append(
                build_entry(
                    actor=user,
                    action=AuditAction.REPORT_DECIDED,
                    entity_type="Report",
                    entity_id=report.id,
                    details={
                        "decision": ReportDecision.CLOSED_ACCOUNT_DELETED,
                        "system_triggered": True,
                    },
                )
            )

    if to_delete:
        db.query(DirectMessage).filter(DirectMessage.id.in_(to_delete)).delete(
            synchronize_session=False
        )

    return (
        {"deleted_message_ids": to_delete, "closed_report_ids": closed_report_ids},
        entries,
    )


def export_user_direct_messages(db: Session, user: User) -> list[dict[str, Any]]:
    """
    Every DirectMessage `user` sent or received, decrypted (spec §9.5 —
    GDPR/Israeli privacy-law right of access). Oldest first, across every
    conversation: this is a full personal-data export, not the inbox view.
    """
    messages = (
        db.query(DirectMessage)
        .filter(
            or_(
                DirectMessage.sender_id == user.id,
                DirectMessage.recipient_id == user.id,
            )
        )
        .order_by(DirectMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": message.id,
            "sender_id": message.sender_id,
            "recipient_id": message.recipient_id,
            "content": decrypt_message(message.content, message.key_version),
            "sent_at": message.created_at,
            "read_at": message.read_at,
        }
        for message in messages
    ]

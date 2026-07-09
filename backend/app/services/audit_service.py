"""
Audit log service.

Every sensitive admin/moderator action must be logged.
Logs are append-only (never update or delete).

Usage:
    from app.services.audit_service import log_action
    from app.core.constants import AuditAction

    log_action(
        db,
        actor=current_user,
        action=AuditAction.USER_APPROVED,
        entity_type="User",
        entity_id=user.id,
        details={"new_status": "active"},
        ip_address=request.client.host,
    )
"""

from typing import Any

from sqlalchemy.orm import Session

from app.core.constants import AuditAction
from app.models.audit import AuditLog
from app.models.user import User


def log_action(
    db: Session,
    actor: User,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Create an immutable audit log entry.

    This function should be called from every service method that performs
    a sensitive operation (approve/reject/suspend/delete/export).
    """
    entry = AuditLog(
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_audit_log(
    db: Session,
    page: int = 1,
    page_size: int = 50,
    action_filter: AuditAction | None = None,
    entity_type_filter: str | None = None,
) -> list[AuditLog]:
    """
    Return audit log entries for admin review.

    TODO:
      1. Query AuditLog
      2. Optionally filter by action and/or entity_type
      3. Order by timestamp DESC
      4. Apply pagination
    """
    # TODO: implement filters and pagination
    query = db.query(AuditLog).order_by(AuditLog.timestamp.desc())
    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size).all()

"""
User management service.

Handles registration approval, suspension, profile retrieval.

TODO list for junior developer:
  [x] implement approve_registration() – first or second admin approves
  [x] implement reject_registration()
  [x] implement get_pending_registrations()
  [x] implement suspend_user()
  [x] implement get_professionals_for_user() – filtered by sector+group
"""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, AuditAction, UserRole
from app.models.user import User
from app.services.audit_service import log_action
from app.services.email_service import (
    send_approval_email,
    send_rejection_email,
    send_suspension_notification,
)


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """
    Fetch a user by id, or None if no such user exists.
    """
    return db.query(User).filter(User.id == user_id).first()


def ensure_account_active(user: User) -> None:
    """
    Business rule: only ACTIVE accounts may proceed.

    Raises 403 otherwise (e.g. suspended/pending/cancelled accounts).
    """
    if user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="החשבון אינו פעיל.")


def get_pending_registrations(db: Session) -> list[User]:
    """
    Return all users awaiting admin approval.
    """
    return (
        db.query(User)
        .filter(
            User.account_status.in_(
                [AccountStatus.PENDING_APPROVAL, AccountStatus.PARTIALLY_APPROVED]
            )
        )
        .order_by(User.created_at.asc())
        .all()
    )


def get_active_users(db: Session) -> list[User]:
    """
    Return all active users (role=USER only, not admins/moderators/professionals).
    """
    return (
        db.query(User)
        .filter(User.account_status == AccountStatus.ACTIVE, User.role == UserRole.USER)
        .order_by(User.created_at.asc())
        .all()
    )


def _apply_first_approval(
    db: Session, user: User, admin: User, previous_status: AccountStatus
) -> None:
    """
    First admin approval: mark partially approved, no email yet.
    """
    user.first_approver_id = admin.id
    user.account_status = AccountStatus.PARTIALLY_APPROVED

    log_action(
        db,
        actor=admin,
        action=AuditAction.USER_PARTIALLY_APPROVED,
        entity_type="User",
        entity_id=user.id,
        details={"previous_status": previous_status, "new_status": user.account_status},
    )
    db.refresh(user)


def _apply_second_approval(
    db: Session, user: User, admin: User, previous_status: AccountStatus
) -> None:
    """
    Second admin approval: activate the account and notify the user by email.
    """
    user.second_approver_id = admin.id
    user.account_status = AccountStatus.ACTIVE
    user.approved_at = datetime.now(UTC)

    log_action(
        db,
        actor=admin,
        action=AuditAction.USER_APPROVED,
        entity_type="User",
        entity_id=user.id,
        details={"previous_status": previous_status, "new_status": user.account_status},
    )
    db.refresh(user)

    send_approval_email(user.email, user.first_name)


def approve_registration(db: Session, user_id: str, admin: User) -> User:
    """
    Admin approves a pending registration.

    Validates the user and status, then dispatches to the first or second
    approval transition (an admin cannot approve the same registration twice).
    """
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    if user.account_status not in (
        AccountStatus.PENDING_APPROVAL,
        AccountStatus.PARTIALLY_APPROVED,
    ):
        raise HTTPException(status_code=400, detail="ההרשמה אינה ממתינה לאישור")
    if user.first_approver_id == admin.id:
        raise HTTPException(status_code=400, detail="לא ניתן לאשר את אותה הרשמה פעמיים")

    previous_status = user.account_status

    if user.first_approver_id is None:
        _apply_first_approval(db, user, admin, previous_status)
    else:
        _apply_second_approval(db, user, admin, previous_status)

    return user


def reject_registration(db: Session, user_id: str, admin: User, reason: str) -> User:
    """
    Admin rejects a registration, records the reason, and notifies the user by email.
    """
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    if user.account_status not in (
        AccountStatus.PENDING_APPROVAL,
        AccountStatus.PARTIALLY_APPROVED,
    ):
        raise HTTPException(status_code=400, detail="ההרשמה אינה ממתינה לאישור")

    previous_status = user.account_status
    user.account_status = AccountStatus.REJECTED
    user.rejection_reason = reason

    log_action(
        db,
        actor=admin,
        action=AuditAction.USER_REJECTED,
        entity_type="User",
        entity_id=user.id,
        details={"previous_status": previous_status, "reason": reason},
    )
    db.refresh(user)

    send_rejection_email(user.email, user.first_name, reason)

    return user


def suspend_user(
    db: Session, user_id: str, actor: User, hours: int, reason: str
) -> User:
    """
    Temporarily suspend a user.
    """
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    if user.role != UserRole.USER:
        raise HTTPException(status_code=400, detail="ניתן להשעות רק משתמשים רגילים")
    if user.account_status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="ניתן להשעות רק משתמש פעיל")

    user.is_suspended = True
    user.suspended_until = datetime.now(UTC) + timedelta(hours=hours)
    user.account_status = AccountStatus.SUSPENDED

    log_action(
        db,
        actor=actor,
        action=AuditAction.USER_SUSPENDED,
        entity_type="User",
        entity_id=user.id,
        details={"hours": hours, "reason": reason},
    )
    db.refresh(user)

    send_suspension_notification(user.email, hours, reason)

    return user


def _visible_to_user(professional: User, current_user: User) -> bool:
    """
    A professional is visible if:
      - professional_groups contains current_user.user_type OR contains "all"
      - professional_sectors contains current_user.sector OR contains "all"
    """
    groups = professional.professional_groups or []
    sectors = professional.professional_sectors or []
    group_match = "all" in groups or current_user.user_type in groups
    sector_match = "all" in sectors or current_user.sector in sectors
    return group_match and sector_match


def get_professionals_for_user(db: Session, current_user: User) -> list[User]:
    """
    Return all active professionals visible to the given user.
    """
    professionals = (
        db.query(User)
        .filter(
            User.role == UserRole.PROFESSIONAL, User.is_active_professional.is_(True)
        )
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )
    return [pro for pro in professionals if _visible_to_user(pro, current_user)]

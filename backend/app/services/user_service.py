"""
User management service.

Handles registration approval, suspension, profile retrieval.

TODO list for junior developer:
  [ ] implement approve_registration() – first or second admin approves
  [ ] implement reject_registration()
  [ ] implement get_pending_registrations()
  [ ] implement suspend_user()
  [ ] implement get_professionals_for_user() – filtered by sector+group
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, AuditAction, UserRole
from app.models.user import User
from app.services.audit_service import log_action
from app.services.email_service import send_approval_email, send_rejection_email


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


def approve_registration(db: Session, user_id: str, admin: User) -> User:
    """
    Admin approves a pending registration.

    Logic:
      - If no first approver yet → set first_approver_id, status = PARTIALLY_APPROVED
      - If first approver already exists (and it's a different admin) →
        set second_approver_id, status = ACTIVE, send welcome email
      - An admin cannot approve their own approval twice

    TODO:
      1. Load user, verify status is PENDING_APPROVAL or PARTIALLY_APPROVED
      2. Apply the logic above
      3. Log to audit_log
      4. Return updated user
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
        user.first_approver_id = admin.id
        user.account_status = AccountStatus.PARTIALLY_APPROVED
    else:
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

    if user.account_status == AccountStatus.ACTIVE:
        send_approval_email(user.email, user.first_name)

    return user


def reject_registration(db: Session, user_id: str, admin: User, reason: str) -> User:
    """
    Admin rejects a registration.

    TODO:
      1. Load user, set status = REJECTED, save reason
      2. Send rejection email with reason
      3. Log to audit_log
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

    TODO:
      1. Load user
      2. Set is_suspended=True, suspended_until = now + hours
      3. Set account_status = SUSPENDED
      4. Log to audit_log with reason
      5. Send notification email to user
    """
    # TODO: implement this function
    raise NotImplementedError("suspend_user() is not yet implemented")


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

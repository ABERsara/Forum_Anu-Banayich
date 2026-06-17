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

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, Sector, UserRole, UserType
from app.models.user import User
from app.services.audit_service import log_action
from app.services.email_service import send_approval_email, send_rejection_email


def get_pending_registrations(db: Session) -> list[User]:
    """
    Return all users awaiting admin approval.

    TODO:
      1. Query users where account_status IN (PENDING_APPROVAL, PARTIALLY_APPROVED)
      2. Order by created_at ascending (oldest first)
    """
    # TODO: implement this function
    raise NotImplementedError("get_pending_registrations() is not yet implemented")


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
    # TODO: implement this function
    raise NotImplementedError("approve_registration() is not yet implemented")


def reject_registration(db: Session, user_id: str, admin: User, reason: str) -> User:
    """
    Admin rejects a registration.

    TODO:
      1. Load user, set status = REJECTED, save reason
      2. Send rejection email with reason
      3. Log to audit_log
    """
    # TODO: implement this function
    raise NotImplementedError("reject_registration() is not yet implemented")


def suspend_user(db: Session, user_id: str, actor: User, hours: int, reason: str) -> User:
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


def get_professionals_for_user(db: Session, current_user: User) -> list[User]:
    """
    Return all active professionals visible to the given user.

    A professional is visible if:
      - professional_groups contains current_user.user_type OR contains "all"
      - professional_sectors contains current_user.sector OR contains "all"

    TODO:
      1. Query users where role=PROFESSIONAL and is_active_professional=True
      2. Filter by the JSON arrays above (check if user_type/sector is in the list)
    """
    # TODO: implement this function
    raise NotImplementedError("get_professionals_for_user() is not yet implemented")

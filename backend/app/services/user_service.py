"""
User management service.

Handles registration approval, suspension, profile retrieval and the
admin-side moderator roster (SPEC §7).

TODO list for junior developer:
  [x] implement approve_registration() – first or second admin approves
  [x] implement reject_registration()
  [x] implement get_pending_registrations()
  [x] implement suspend_user()
  [x] implement get_professionals_for_user() – filtered by sector+group
  [x] implement get_moderators() / create_moderator() / update_moderator() /
      remove_moderator()
"""

import secrets
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.constants import AccountStatus, AuditAction, UserRole
from app.core.security import get_password_hash
from app.models.user import User
from app.schemas.user import (
    ModeratorCell,
    ModeratorCreateRequest,
    ModeratorUpdateRequest,
)
from app.services.audit_service import log_action
from app.services.email_service import (
    send_approval_email,
    send_rejection_email,
    send_sla_escalation_alert,
    send_suspension_notification,
)

SLA_ESCALATION_DAYS = 7


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


def escalate_overdue_registrations(db: Session) -> list[User]:
    """
    Find registrations stuck 7+ days without a status update and email the
    senior admin(s) once per request.

    Meant to be called by any scheduler (cron, Celery, etc.); it is a plain
    function so it can also be invoked directly from tests.
    """
    threshold = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        days=SLA_ESCALATION_DAYS
    )
    stuck_users = (
        db.query(User)
        .filter(
            User.account_status.in_(
                [AccountStatus.PENDING_APPROVAL, AccountStatus.PARTIALLY_APPROVED]
            ),
            User.updated_at <= threshold,
            User.sla_escalation_sent_at.is_(None),
        )
        .all()
    )
    if not stuck_users:
        return []

    senior_admins = (
        db.query(User)
        .filter(User.role == UserRole.ADMIN, User.alert_email.isnot(None))
        .all()
    )
    if not senior_admins:
        return []

    escalated: list[User] = []
    for user in stuck_users:
        for admin in senior_admins:
            assert admin.alert_email is not None, (
                "senior_admins is filtered to alert_email IS NOT NULL above"
            )
            send_sla_escalation_alert(admin.alert_email, user.id, user.email)
        user.sla_escalation_sent_at = datetime.now(UTC).replace(tzinfo=None)
        escalated.append(user)

    db.commit()
    return escalated


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


# ---------------------------------------------------------------------------
# Moderator roster – admin side (SPEC §7)
#
# A moderator oversees a set of cells of the group×sector matrix. The roster
# below is what the admin manages: who is appointed, over which cells, and
# where their report alerts are sent.
# ---------------------------------------------------------------------------

#: Bytes of entropy behind the unusable placeholder credential of a moderator
#: created by an admin. See create_moderator() for why there is one at all.
PLACEHOLDER_PASSWORD_BYTES = 32


def _cells_as_json(cells: Sequence[ModeratorCell]) -> list[dict[str, str]]:
    """
    Unwrap the cells the API validated into the plain dicts the JSON column
    holds: [{"group": "widow", "sector": "sephardic"}, ...].
    """
    return [{"group": cell.group.value, "sector": cell.sector.value} for cell in cells]


def get_moderators(db: Session) -> list[User]:
    """
    Return the moderator roster: every appointed moderator with their cells.

    A removed moderator keeps their row (see remove_moderator) but is off the
    roster, so they are filtered out here instead of lingering as an entry the
    admin can no longer act on.
    """
    return (
        db.query(User)
        .filter(
            User.role == UserRole.MODERATOR,
            User.account_status != AccountStatus.CANCELLED,
        )
        .order_by(User.last_name.asc(), User.first_name.asc())
        .all()
    )


def _load_moderator(db: Session, user_id: str) -> User:
    """
    Load a moderator for editing — locked for update — or raise why not.
    """
    user = db.query(User).filter(User.id == user_id).with_for_update().first()
    if not user:
        raise HTTPException(status_code=404, detail="משתמש לא נמצא")
    if user.role != UserRole.MODERATOR:
        raise HTTPException(status_code=400, detail="ניתן לערוך ממונים בלבד")
    if user.account_status == AccountStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="הממונה כבר הוסר מהמערכת")
    return user


def _log_appointment(
    db: Session, moderator: User, admin: User, *, reinstated: bool
) -> None:
    """
    Record an appointment.

    The cells are the *scope* a moderator answers for, not anyone's personal
    data, so they belong in the entry. The alert address is contact detail, so
    only whether one was given is recorded (CONTRIBUTING §4).
    """
    log_action(
        db,
        actor=admin,
        action=AuditAction.MODERATOR_ASSIGNED,
        entity_type="User",
        entity_id=moderator.id,
        details={
            "cells": moderator.moderator_cells,
            "alert_email_set": moderator.alert_email is not None,
            "reinstated": reinstated,
        },
    )


def _reinstate_moderator(
    db: Session, existing: User, data: ModeratorCreateRequest, admin: User
) -> User:
    """
    Re-appoint someone who had been removed from the roster.

    Removal keeps the row, so appointing the same person again would otherwise
    collide with their own record forever. Any *other* account holding the
    address is a genuine conflict and is rejected.
    """
    if not (
        existing.role == UserRole.MODERATOR
        and existing.account_status == AccountStatus.CANCELLED
    ):
        raise HTTPException(status_code=409, detail="כתובת המייל כבר רשומה במערכת")

    existing.first_name = data.first_name
    existing.last_name = data.last_name
    existing.account_status = AccountStatus.ACTIVE
    existing.moderator_cells = _cells_as_json(data.moderator_cells)
    existing.alert_email = data.alert_email

    _log_appointment(db, existing, admin, reinstated=True)
    db.refresh(existing)

    return existing


def create_moderator(db: Session, data: ModeratorCreateRequest, admin: User) -> User:
    """
    Appoint a moderator over the given cells.

    The account is ACTIVE on creation: the OTP and the two-admin approval flow
    exist to vet bereaved members registering themselves, and an admin
    appointing someone they chose already is that check.

    It is created with a random placeholder password nobody holds — the column
    is NOT NULL and an empty hash would accept an empty password. The moderator
    receives real credentials through the invitation flow (out of scope for this
    ticket); until then the appointment stands but the account cannot be signed
    into.
    """
    existing = db.query(User).filter(User.email == data.email).first()
    if existing is not None:
        return _reinstate_moderator(db, existing, data, admin)

    moderator = User(
        email=data.email,
        password_hash=get_password_hash(
            secrets.token_urlsafe(PLACEHOLDER_PASSWORD_BYTES)
        ),
        first_name=data.first_name,
        last_name=data.last_name,
        role=UserRole.MODERATOR,
        account_status=AccountStatus.ACTIVE,
        moderator_cells=_cells_as_json(data.moderator_cells),
        alert_email=data.alert_email,
    )
    db.add(moderator)
    db.flush()  # assigns the id the audit entry has to reference

    # log_action() commits, so the moderator and their audit trail land in the
    # same transaction — the roster can never gain an unlogged appointment.
    _log_appointment(db, moderator, admin, reinstated=False)
    db.refresh(moderator)

    return moderator


def _apply_moderator_updates(moderator: User, updates: dict[str, Any]) -> list[str]:
    """
    Write the submitted fields onto the row and return the ones that really
    changed, so a re-save of identical values is not logged as an edit.

    `updates` comes from model_dump(mode="json"), which is already the shape
    the columns hold: cells as plain dicts of strings, alert_email as a str.
    Cells arrive in one canonical order (see schemas.user), so re-ticking the
    same cells in another order compares equal.
    """
    changed: list[str] = []
    for field, value in updates.items():
        if getattr(moderator, field) != value:
            setattr(moderator, field, value)
            changed.append(field)
    return changed


def update_moderator(
    db: Session, user_id: str, data: ModeratorUpdateRequest, admin: User
) -> User:
    """
    Update a moderator's cells and/or alert address.

    Only the fields present in the request are touched — see
    ModeratorUpdateRequest. The audit entry records which fields changed and
    the cells the moderator now holds; the alert address itself never reaches
    the log (CONTRIBUTING §4).
    """
    moderator = _load_moderator(db, user_id)

    changed = _apply_moderator_updates(
        moderator, data.model_dump(exclude_unset=True, mode="json")
    )
    if not changed:
        return moderator

    log_action(
        db,
        actor=admin,
        action=AuditAction.MODERATOR_UPDATED,
        entity_type="User",
        entity_id=moderator.id,
        details={
            "updated_fields": sorted(changed),
            "cells": moderator.moderator_cells,
            "alert_email_set": moderator.alert_email is not None,
        },
    )
    db.refresh(moderator)

    return moderator


def remove_moderator(db: Session, user_id: str, admin: User) -> None:
    """
    Remove a moderator from the roster.

    The row is not deleted: audit entries, decided reports and any content the
    account touched all reference its id, and a hard delete would either fail
    on those references or orphan them. The appointment is revoked instead —
    the account is cancelled, so it can no longer sign in (see
    ensure_account_active), and the cells and alert address are cleared so
    nothing keeps routing to someone who no longer moderates.

    The same person can be appointed again later; create_moderator() reinstates
    this row rather than colliding with it.
    """
    moderator = _load_moderator(db, user_id)
    revoked_cells = moderator.moderator_cells or []

    moderator.account_status = AccountStatus.CANCELLED
    moderator.moderator_cells = []
    moderator.alert_email = None

    log_action(
        db,
        actor=admin,
        action=AuditAction.MODERATOR_REMOVED,
        entity_type="User",
        entity_id=moderator.id,
        details={"revoked_cells": revoked_cells},
    )

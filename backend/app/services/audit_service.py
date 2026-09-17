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

    Several rows deleted or changed as one atomic operation build their
    entries with build_entry() instead, and commit them together with the
    rows they describe.
"""

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from app.core.constants import AuditAction, AuditSortField, SortDirection
from app.models.audit import AuditLog
from app.models.user import User


def build_entry(
    actor: User,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> AuditLog:
    """
    Build one audit entry without staging or committing it.

    For the caller that changes several rows as a single change. log_action()
    commits on every call, so calling it once per row turns one change into N
    transactions, and a failure after the first leaves part of the change
    applied with an audit trail that no longer describes the data. Such a
    caller builds its entries with this, db.add_all()s them alongside its own
    writes, and commits once.

    A single sensitive action still goes through log_action() — this is how a
    batch stays atomic, not an alternative way to write one entry.
    """
    return AuditLog(
        actor_id=actor.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        ip_address=ip_address,
    )


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
    entry = build_entry(actor, action, entity_type, entity_id, details, ip_address)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


#: The columns AuditSortField names, as the ORDER BY has to address them.
#: A mapping rather than `getattr(AuditLog, sort)`: the value comes off the
#: query string, and getattr on a user-supplied name reaches every attribute
#: the model has — `ip_address` included, which this endpoint exists to keep
#: out of reach.
_SORT_COLUMNS: dict[AuditSortField, InstrumentedAttribute[Any]] = {
    AuditSortField.TIMESTAMP: AuditLog.timestamp,
}


def get_audit_log(
    db: Session,
    *,
    actor_id: str | None = None,
    action_type: AuditAction | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: AuditSortField = AuditSortField.TIMESTAMP,
    direction: SortDirection = SortDirection.DESC,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[AuditLog], int]:
    """
    Return one page of the audit log, with the total across all pages.

    Every filter of the frozen contract (SPEC §9.3, GDPR art. 30) is applied
    in SQL, and so are the ordering and the page window: the rows this
    returns are the rows the database sent, never a slice taken in Python.
    The table is append-only and kept for seven years, so "fetch it and
    filter afterwards" is not a slower version of this — it is an admin page
    that stops answering somewhere around year two.

    Filters combine with AND. Each one is applied only when it was given, so
    the intersection of any subset of them is what comes back, and no filter
    at all is the whole log.

    The total is a separate `COUNT(*)` over the same filters, deliberately
    not `len(rows)`: `rows` is one page, so counting it would report 50 for a
    log of ten thousand and put the pager on page 1 of 1 for every filter
    that matches more than a page.

    `date_from` / `date_to` are **dates, and both are inclusive**. The
    contract's names say days, an admin filtering a GDPR request thinks in
    days, and the timestamps stored are instants — so the window runs from
    midnight opening `date_from` to midnight *closing* `date_to`, expressed
    as `< date_to + 1 day` rather than `<= date_to`. Written the obvious way,
    `timestamp <= date_to` reads as midnight *opening* that day and silently
    drops every entry written during the last day of the range, which is the
    day the person filtering is most likely to care about.

    Returns `(rows, total_count)`.
    """
    query = db.query(AuditLog)

    if actor_id is not None:
        query = query.filter(AuditLog.actor_id == actor_id)
    if action_type is not None:
        query = query.filter(AuditLog.action == action_type)
    if entity_type is not None:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    if date_from is not None:
        query = query.filter(
            AuditLog.timestamp >= datetime.combine(date_from, time.min)
        )
    if date_to is not None:
        query = query.filter(
            AuditLog.timestamp < datetime.combine(date_to + timedelta(days=1), time.min)
        )

    # Before the page window, and over the filtered query rather than the
    # table: this is the number the pager divides into pages.
    total_count = query.count()

    column = _SORT_COLUMNS[sort]
    # AuditLog.id is part of the ordering, not decoration. `timestamp` has a
    # `server_default` of CURRENT_TIMESTAMP, which is whole seconds on SQLite
    # — a batch written by one admin action shares a timestamp exactly. A
    # page boundary falling inside such a tie is an undefined boundary, and
    # the row on both sides of it is either shown twice or skipped. The id
    # follows the same direction as the column, so `asc` and `desc` are exact
    # reverses of one another rather than two nearly-opposite orders.
    ordering = (
        (column.asc(), AuditLog.id.asc())
        if direction == SortDirection.ASC
        else (column.desc(), AuditLog.id.desc())
    )

    rows = (
        query.order_by(*ordering).offset((page - 1) * page_size).limit(page_size).all()
    )
    return rows, total_count

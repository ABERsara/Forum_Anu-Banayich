"""
Pydantic schemas for reading the audit log (GET /admin/audit-log, ABF-152).

There is no write schema here. Audit entries are never posted by a client —
`audit_service.log_action()` is the only thing that creates one, called from
the service that performed the action being recorded. This file is the read
contract, and nothing else.

**`ip_address` is absent on purpose, and its absence is the point.** The
column exists on the model, it is populated, and it is retained for the seven
years §9.3 requires — but the decision recorded on ABF-152 is that it is not
exposed on any screen, under any parameter, to any role. A schema that simply
does not declare the field is what makes that true by construction: every
response on this endpoint is built by `AuditLogEntry`, so there is no code
path that could serialise the column by accident, and adding the field back
would have to be a deliberate edit to this file rather than a `model_dump()`
that quietly grew a key.
"""

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from app.core.constants import AuditAction


class AuditLogEntry(BaseModel):
    """
    One audit log row, exactly as the frozen contract lists it: `id`,
    `actor_id`, `action_type`, `entity_type`, `entity_id`, `timestamp`,
    `details`.

    No actor *name*. The contract carries the actor's id and the model holds
    no name to join on anyway — `AuditLog.actor_id` has no foreign key, so
    that logs outlive the users they describe (deleting an admin must not
    take the record of what they did with them). A name resolved at read time
    would therefore be blank for exactly the rows that matter most, and the
    id is the only identifier that is still true seven years later.
    """

    id: str
    actor_id: str
    #: `action_type` on the wire, `action` on the model. The contract is
    #: frozen on the former and the column was named the latter long before
    #: it; an alias is cheaper than a migration, and cheaper than renaming
    #: the field on a table nothing may rewrite.
    action_type: AuditAction = Field(
        validation_alias=AliasChoices("action", "action_type")
    )
    entity_type: str
    entity_id: str
    timestamp: datetime
    #: Free-form context the logging service attached — never message text,
    #: an ID number or an email address (CONTRIBUTING §4, "אין PII בלוגים").
    details: dict[str, Any] | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class AuditLogListResponse(BaseModel):
    """
    GET /admin/audit-log — `{ items, total_count, page, page_size }`.

    `total_count`, not the `total` its sibling list responses use: this one
    is named by a frozen contract and follows it rather than the house style
    it would otherwise match.

    The count is over everything the filters select, not over `items` — it is
    what the pager needs in order to know there *is* a page 2.
    """

    items: list[AuditLogEntry]
    total_count: int
    page: int
    page_size: int

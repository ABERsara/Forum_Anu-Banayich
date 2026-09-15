"""
Moderator endpoints.

All routes require UserRole.MODERATOR (or ADMIN).

GET  /moderator/reports             – pending reports in moderator's cells
GET  /moderator/reports/history     – reports already decided, paginated
GET  /moderator/restrictions        – automatic restrictions in force in those cells
GET  /moderator/reports/{id}        – single report with full context
POST /moderator/reports/{id}/decide – decide on a report (valid/invalid)
GET  /moderator/users/{id}/card     – one user's moderation history
POST /moderator/users/{id}/suspend  – suspend that user by hand
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import ReportTargetType, UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.report import (
    ReportDecideRequest,
    ReportHistoryResponse,
    ReportListResponse,
    ReportResponse,
    ReportWithContent,
)
from app.schemas.restriction import (
    RestrictedMember,
    RestrictionListResponse,
    RestrictionWithMember,
)
from app.schemas.user import SuspendUserRequest, UserModerationCard
from app.services import report_service, restriction_service

router = APIRouter(
    prefix="/moderator",
    tags=["Moderator"],
    dependencies=[Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))],
)


def _to_reports_with_content(db: Session, reports: list[Report]) -> list[ReportWithContent]:
    """
    Enrich a batch of reports with the context a moderator needs to see
    them — the two target_types share nothing to read from, so each report
    branches on it, but the content itself is fetched in two bounded
    queries (one per target_type) up front rather than one query per
    report: get_pending_reports() alone is unpaginated, so a per-report
    query here would cost the whole cell's queue size in DB round trips
    for every load.

    Never decrypts DIRECT_MESSAGE content: this is what backs the pending
    and history lists too (§7.3), and a list row is metadata only —
    decrypting one there would mean auditing a "view" that never happened
    (report_service.decrypt_reported_message() is the one place that ever
    calls decrypt_message() on a report, and get_report() below is the only
    caller of it). message_content stays at its schema default (None) here;
    get_report() fills it in afterwards, for the one report actually opened.

    A FORUM_POST's post is never actually missing today — delete_post()
    only ever sets status=DELETED, the row stays — so this has nothing to
    degrade against yet. It still doesn't raise: this function backs
    list_pending_reports()/list_decided_reports() as well as get_report()
    now, and a 404 raised here would take down every other report in the
    response over one row, the same inconsistency decide_report()'s own
    "target_gone" branch already exists to avoid on the decide side.
    Content fields are simply left at the schema's None default — the same
    degrade-gracefully answer the DIRECT_MESSAGE branch below already gives.
    """
    post_ids = [r.target_id for r in reports if r.target_type == ReportTargetType.FORUM_POST]
    posts_by_id = {
        post.id: post for post in db.query(ForumPost).filter(ForumPost.id.in_(post_ids)).all()
    }

    items: list[ReportWithContent] = []
    for report in reports:
        base = ReportResponse.model_validate(report).model_dump()
        if report.target_type == ReportTargetType.FORUM_POST:
            post = posts_by_id.get(report.target_id)
            if post is None:
                items.append(ReportWithContent(**base))
                continue
            items.append(
                ReportWithContent(
                    **base,
                    content_title=post.title,
                    content_text=post.content,
                    content_status=post.status,
                    report_count=post.report_count,
                )
            )
            continue

        # DIRECT_MESSAGE. No content lookup at all: a list row never shows
        # decrypted content (see the docstring above), and there is nothing
        # else about a DM report worth reading from the live row here — its
        # hidden/visible state is already implied by report.decision (VALID
        # always hides, INVALID never does; a report is decided at most
        # once), so there is no independent fact left for a live lookup to
        # add, unlike a ForumPost's content_status.
        items.append(ReportWithContent(**base))
    return items


@router.get("/reports", response_model=ReportListResponse)
def list_pending_reports(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    """
    Return pending reports in the moderator's assigned cells.
    Sorted by report_count DESC (most-reported content first, SPEC §7.3) —
    a DIRECT_MESSAGE report counts as 1 (see report_service.get_pending_
    reports() for why that's exact, not a placeholder).
    """
    reports = report_service.get_pending_reports(db, current_user)
    items = _to_reports_with_content(db, reports)

    return ReportListResponse(items=items, total=len(items), pending_count=len(items))


# Declared before /reports/{report_id}: FastAPI matches routes in order, and
# the path-parameter route would otherwise swallow "history" as an id.
@router.get("/reports/history", response_model=ReportHistoryResponse)
def list_decided_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportHistoryResponse:
    """
    Return decisions already made in the moderator's assigned cells,
    newest first (SPEC §7.3, "היסטוריית דיווחים").
    """
    reports, total = report_service.get_decided_reports(db, current_user, page, page_size)

    return ReportHistoryResponse(
        items=_to_reports_with_content(db, reports),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/restrictions", response_model=RestrictionListResponse)
def list_active_restrictions(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> RestrictionListResponse:
    """
    Return the automatic restrictions in force right now in the moderator's
    assigned cells, newest first (§7.2 "התראה למבקר", §7.3).

    Scoped exactly like the report queue: a moderator sees her own cells, an
    admin sees everything. A restriction names a member and what the platform
    stopped her doing — it is the same private fact as the reports behind it,
    and it does not travel outside the cell the moderator is responsible for.

    Never any report content, and never a reporter's identity. The list says
    how many decided reports crossed the threshold and over what window; the
    reports themselves are read one at a time in the queue above.
    """
    pairs = restriction_service.list_active_restrictions(db, current_user)
    items = [
        RestrictionWithMember(
            id=restriction.id,
            restriction_type=restriction.restriction_type,
            expires_at=restriction.expires_at,
            report_count=restriction.report_count,
            window_days=restriction.window_days,
            created_at=restriction.created_at,
            member=RestrictedMember.model_validate(member),
        )
        for restriction, member in pairs
    ]
    return RestrictionListResponse(items=items, total=len(items))


@router.get("/reports/{report_id}", response_model=ReportWithContent)
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportWithContent:
    """
    Return a single report with the full context of the reported content.

    The one path that ever decrypts a DIRECT_MESSAGE report's content — and
    the one that is audited for it (ABF-113, spec §9.1/§9.3): opening this
    report is the "צפייה" that report_service.decrypt_reported_message()
    logs, not merely knowing it exists (which listing already allows).
    """
    report = report_service.get_report_for_moderator(db, report_id, current_user)
    item = _to_reports_with_content(db, [report])[0]

    if report.target_type == ReportTargetType.DIRECT_MESSAGE:
        item.message_content = report_service.decrypt_reported_message(
            db, report, current_user
        )

    return item


@router.post("/reports/{report_id}/decide", response_model=ReportResponse)
def decide_report(
    report_id: str,
    data: ReportDecideRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """
    Moderator decides on a report, with a mandatory note for the record.

    VALID   → a ForumPost is deleted; a DIRECT_MESSAGE is hidden from both
              participants. Either way, the reported-on user is notified.
    INVALID → a ForumPost the 2-report rule auto-hid is restored to visible;
              a DIRECT_MESSAGE, never auto-hidden to begin with, is left as
              it was.
    """
    report = report_service.decide_report(db, report_id, data, current_user)
    return ReportResponse.model_validate(report)


# ---------------------------------------------------------------------------
# The user card (SPEC §7.3)
# ---------------------------------------------------------------------------


@router.get("/users/{user_id}/card", response_model=UserModerationCard)
def get_user_card(
    user_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> UserModerationCard:
    """
    Return one user's moderation history: how often they were reported, how
    those reports were decided, how many of the reports they filed turned out
    to be false, and whether they are currently suspended.

    Scoped to the moderator's own cells – 403 for a user outside them.
    """
    return report_service.get_user_card(db, user_id, current_user)


@router.post("/users/{user_id}/suspend", response_model=UserModerationCard)
def suspend_user(
    user_id: str,
    data: SuspendUserRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> UserModerationCard:
    """
    Suspend a user by hand for `hours` hours, with a reason for the record.

    Answers with the card as it now stands, rather than with UserAdminView as
    the admin route does: the reply goes back to a moderator, and the card is
    the moderator's view of a user – counts and cell, no contact details.
    """
    return report_service.suspend_user_for_moderator(db, user_id, current_user, data)

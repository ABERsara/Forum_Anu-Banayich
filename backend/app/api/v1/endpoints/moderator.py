"""
Moderator endpoints.

All routes require UserRole.MODERATOR (or ADMIN).

GET  /moderator/reports             – pending reports in moderator's cells
GET  /moderator/reports/history     – reports already decided, paginated
GET  /moderator/reports/{id}        – single report with full context
POST /moderator/reports/{id}/decide – decide on a report (valid/invalid)
GET  /moderator/users/{id}/card     – one user's moderation history
POST /moderator/users/{id}/suspend  – suspend that user by hand
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.constants import UserRole
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
from app.schemas.user import SuspendUserRequest, UserModerationCard
from app.services import report_service

router = APIRouter(
    prefix="/moderator",
    tags=["Moderator"],
    dependencies=[Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))],
)


def _to_report_with_content(report: Report, post: ForumPost) -> ReportWithContent:
    return ReportWithContent(
        **ReportResponse.model_validate(report).model_dump(),
        content_title=post.title,
        content_text=post.content,
        content_status=post.status,
        report_count=post.report_count,
    )


@router.get("/reports", response_model=ReportListResponse)
def list_pending_reports(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    """
    Return pending reports in the moderator's assigned cells.
    Sorted by report_count DESC (most-reported content first).
    """
    pairs = report_service.get_pending_reports(db, current_user)
    items = [_to_report_with_content(report, post) for report, post in pairs]

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
    pairs, total = report_service.get_decided_reports(db, current_user, page, page_size)

    return ReportHistoryResponse(
        items=[_to_report_with_content(report, post) for report, post in pairs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/reports/{report_id}", response_model=ReportWithContent)
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportWithContent:
    """
    Return a single report with the full context of the reported content.
    """
    report, post = report_service.get_report_for_moderator(db, report_id, current_user)
    return _to_report_with_content(report, post)


@router.post("/reports/{report_id}/decide", response_model=ReportResponse)
def decide_report(
    report_id: str,
    data: ReportDecideRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """
    Moderator decides on a report, with a mandatory note for the record.

    VALID   → the reported post is deleted and its author is notified
    INVALID → a post that was auto-hidden is restored to visible
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

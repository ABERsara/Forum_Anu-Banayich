"""
Moderator endpoints.

All routes require UserRole.MODERATOR (or ADMIN).

GET  /moderator/reports           – pending reports in moderator's cells
GET  /moderator/reports/{id}      – single report with full context
POST /moderator/reports/{id}/decide – decide on a report (valid/invalid)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.constants import UserRole
from app.core.dependencies import get_current_active_user, get_db, require_role
from app.models.forum import ForumPost
from app.models.report import Report
from app.models.user import User
from app.schemas.report import (
    ReportDecideRequest,
    ReportListResponse,
    ReportResponse,
    ReportWithContent,
)
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
    Moderator decides on a report.

    VALID  → content is deleted, reporter is notified, auto-suspension check runs
    INVALID → content is restored if hidden, false-reporter check runs

    TODO: call report_service.decide_report(db, report_id, data, current_user)
    """
    # TODO: implement
    raise NotImplementedError

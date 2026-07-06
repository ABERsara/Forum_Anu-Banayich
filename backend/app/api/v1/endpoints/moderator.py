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
from app.core.dependencies import get_current_user, get_db, require_role
from app.models.user import User
from app.schemas.report import ReportDecideRequest, ReportListResponse, ReportResponse

router = APIRouter(
    prefix="/moderator",
    tags=["Moderator"],
    dependencies=[Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))],
)


@router.get("/reports", response_model=ReportListResponse)
def list_pending_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    """
    Return pending reports in the moderator's assigned cells.
    Sorted by report_count DESC (most-reported content first).

    TODO: call report_service.get_pending_reports(db, current_user)
    """
    # TODO: implement
    return ReportListResponse(items=[], total=0, pending_count=0)


@router.get("/reports/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportResponse:
    """
    Return a single report with the full context of the reported content.

    TODO:
      1. Load report
      2. Verify moderator is responsible for this report's cell
      3. Load the reported content (post/message/query) for context
    """
    # TODO: implement
    raise NotImplementedError


@router.post("/reports/{report_id}/decide", response_model=ReportResponse)
def decide_report(
    report_id: str,
    data: ReportDecideRequest,
    current_user: User = Depends(get_current_user),
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

"""
Moderator endpoints.

All routes require UserRole.MODERATOR (or ADMIN).

GET  /moderator/reports             – pending reports in moderator's cells
GET  /moderator/reports/history     – reports already decided, paginated
GET  /moderator/reports/{id}        – single report with full context
POST /moderator/reports/{id}/decide – decide on a report (valid/invalid)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
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


def _with_content(db: Session, reports: list[Report]) -> list[ReportWithContent]:
    """
    Attach the reported post to each report, in one query rather than one
    per row. A report whose post has vanished is dropped instead of raising:
    a moderator's queue is not the place to surface an orphaned row.
    """
    if not reports:
        return []

    posts_by_id = {
        post.id: post
        for post in db.query(ForumPost)
        .filter(ForumPost.id.in_([r.target_id for r in reports]))
        .all()
    }
    return [
        _to_report_with_content(report, posts_by_id[report.target_id])
        for report in reports
        if report.target_id in posts_by_id
    ]


@router.get("/reports", response_model=ReportListResponse)
def list_pending_reports(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> ReportListResponse:
    """
    Return pending reports in the moderator's assigned cells.
    Sorted by report_count DESC (most-reported content first).
    """
    reports = report_service.get_pending_reports(db, current_user)
    items = _with_content(db, reports)

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
    reports, total = report_service.get_decided_reports(
        db, current_user, page, page_size
    )

    return ReportHistoryResponse(
        items=_with_content(db, reports),
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
    report = report_service.get_report_for_moderator(db, report_id, current_user)
    post = db.query(ForumPost).filter(ForumPost.id == report.target_id).first()
    if post is None:
        raise HTTPException(status_code=404, detail="התוכן המדווח לא נמצא.")

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

"""Exception and Comparison API endpoints.

Provides REST API for exception management, comparison operations,
and dashboard data retrieval.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    CommitteeAgendaItemOut,
    ExceptionCommentCreate,
    ExceptionCommentOut,
    ExceptionDetailOut,
    ExceptionOut,
    ExceptionSummary,
    ExceptionUpdate,
    ResolutionData,
    ValuationComparisonOut,
)
from app.services.comparison import ComparisonEngine
from app.services.exceptions import ExceptionManager

router = APIRouter(prefix="/exceptions", tags=["Exceptions"])


# ── Exception CRUD ───────────────────────────────────────────────


@router.get("/", response_model=list[ExceptionOut])
async def list_exceptions(
    severity: Optional[str] = Query(None, pattern="^(AMBER|RED)$"),
    status: Optional[str] = Query(
        None, pattern="^(OPEN|INVESTIGATING|RESOLVED|ESCALATED)$"
    ),
    asset_class: Optional[str] = None,
    assigned_to: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """Get list of exceptions with filters.

    - **severity**: Filter by AMBER or RED
    - **status**: Filter by OPEN, INVESTIGATING, RESOLVED, or ESCALATED
    - **asset_class**: Filter by position asset class (FX, Rates, Credit, Equity)
    - **assigned_to**: Filter by assigned analyst
    - **start_date/end_date**: Filter by creation date range
    """
    manager = ExceptionManager(db)
    return await manager.list_exceptions(
        severity=severity,
        status=status,
        asset_class=asset_class,
        assigned_to=assigned_to,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=ExceptionSummary)
async def get_exception_summary(db: AsyncSession = Depends(get_db)):
    """Get summary statistics for exceptions dashboard."""
    engine = ComparisonEngine(db)
    return await engine.get_exception_summary()


@router.get("/statistics")
async def get_exception_statistics(db: AsyncSession = Depends(get_db)):
    """Get detailed exception statistics for analytics."""
    manager = ExceptionManager(db)
    return await manager.get_exception_statistics()


@router.get("/{exception_id}", response_model=ExceptionDetailOut)
async def get_exception_detail(exception_id: int, db: AsyncSession = Depends(get_db)):
    """Get full exception detail including comments and position info."""
    manager = ExceptionManager(db)
    exc = await manager.get_exception(exception_id)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exc


@router.patch("/{exception_id}", response_model=ExceptionOut)
async def update_exception(
    exception_id: int,
    data: ExceptionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update exception status, assignment, or notes."""
    manager = ExceptionManager(db)
    exc = await manager.update_exception(exception_id, data)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exc


@router.post("/{exception_id}/assign", response_model=ExceptionOut)
async def assign_exception(
    exception_id: int,
    assigned_to: str = Query(..., description="Analyst name or ID"),
    db: AsyncSession = Depends(get_db),
):
    """Assign exception to a VC analyst."""
    manager = ExceptionManager(db)
    exc = await manager.assign_exception(exception_id, assigned_to)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exc


@router.put("/{exception_id}/resolve", response_model=ExceptionOut)
async def resolve_exception(
    exception_id: int,
    resolution: ResolutionData,
    db: AsyncSession = Depends(get_db),
):
    """Mark exception as resolved with resolution notes."""
    manager = ExceptionManager(db)
    exc = await manager.resolve_exception(exception_id, resolution)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exc


# ── Comments ─────────────────────────────────────────────────────


@router.post("/{exception_id}/comment", response_model=ExceptionCommentOut, status_code=201)
async def add_comment(
    exception_id: int,
    comment: ExceptionCommentCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add comment to exception (from VC analyst or Desk trader)."""
    # Verify exception exists
    manager = ExceptionManager(db)
    exc = await manager.get_exception(exception_id)
    if not exc:
        raise HTTPException(status_code=404, detail="Exception not found")

    return await manager.add_comment(exception_id, comment)


# ── Comparison Operations ────────────────────────────────────────


comparison_router = APIRouter(prefix="/comparisons", tags=["Comparisons"])


@comparison_router.post("/run/{position_id}")
async def run_comparison(position_id: int, db: AsyncSession = Depends(get_db)):
    """Run VC vs Desk comparison for a single position."""
    engine = ComparisonEngine(db)
    try:
        return await engine.compare_valuation(position_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@comparison_router.post("/run-batch")
async def run_batch_comparison(
    asset_class: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Run daily comparison on all positions (or filtered by asset class).

    This is typically run as a scheduled daily job.
    """
    engine = ComparisonEngine(db)
    return await engine.compare_all_positions(asset_class)


@comparison_router.get("/history/{position_id}", response_model=list[ValuationComparisonOut])
async def get_comparison_history(
    position_id: int,
    limit: int = Query(30, le=365),
    db: AsyncSession = Depends(get_db),
):
    """Get historical comparisons for a position."""
    engine = ComparisonEngine(db)
    return await engine.get_comparison_history(position_id, limit)


# ── Escalation Operations ────────────────────────────────────────


escalation_router = APIRouter(prefix="/escalation", tags=["Escalation"])


@escalation_router.post("/check")
async def check_escalations(db: AsyncSession = Depends(get_db)):
    """Run escalation check on all open exceptions.

    This is typically run as a scheduled daily job.
    Returns summary of escalation actions taken.
    """
    manager = ExceptionManager(db)
    return await manager.check_escalations()


@escalation_router.post("/update-aging")
async def update_exception_aging(db: AsyncSession = Depends(get_db)):
    """Update days_open for all active exceptions.

    This is typically run as a scheduled daily job.
    """
    manager = ExceptionManager(db)
    count = await manager.update_days_open()
    return {"updated": count}


# ── Committee Agenda ─────────────────────────────────────────────


committee_router = APIRouter(prefix="/committee", tags=["Committee"])


@committee_router.get("/agenda", response_model=list[CommitteeAgendaItemOut])
async def get_committee_agenda(
    meeting_date: Optional[date] = None,
    status: Optional[str] = Query(None, pattern="^(PENDING_COMMITTEE|DISCUSSED|RESOLVED)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get Valuation Committee agenda items."""
    manager = ExceptionManager(db)
    return await manager.get_committee_agenda(meeting_date, status)


@committee_router.get("/next-meeting")
async def get_next_meeting_date(db: AsyncSession = Depends(get_db)):
    """Get the date of the next Valuation Committee meeting (Wednesday)."""
    manager = ExceptionManager(db)
    next_date = manager._get_next_committee_date()
    agenda = await manager.get_committee_agenda(meeting_date=next_date)
    return {
        "meeting_date": next_date,
        "pending_items": len(agenda),
    }

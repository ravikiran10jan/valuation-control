"""API endpoints for the IPV Orchestrator.

Provides REST endpoints for:
  - Starting and monitoring IPV runs
  - Querying run history and results
  - Health checks and upstream agent status
  - WebSocket subscription for real-time progress
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.core.database import get_db
from app.models.postgres import IPVPositionResult, IPVRun, IPVStepResult
from app.models.schemas import (
    FairValueLevel,
    IPVRunListItem,
    IPVRunRequest,
    IPVRunStatus,
    IPVRunSummary,
    PositionInput,
    ProgressUpdate,
)
from app.services.ipv_pipeline import IPVPipeline
from app.services.upstream import UpstreamClient
from app.api.websocket import manager, progress_callback

log = structlog.get_logger()

router = APIRouter(prefix="/ipv", tags=["IPV Orchestrator"])

# In-memory store for active runs (for demo/development)
_active_runs: dict[str, IPVRunSummary] = {}
_run_lock = asyncio.Lock()

# The 7 reference positions from the IPV FX Model Excel
REFERENCE_POSITIONS = [
    PositionInput(
        position_id="FX-SPOT-001",
        currency_pair="EUR/USD",
        product_type="Spot",
        notional=Decimal("150000000"),
        desk_mark=Decimal("1.0825"),
        fair_value_level=FairValueLevel.L1,
    ),
    PositionInput(
        position_id="FX-SPOT-002",
        currency_pair="GBP/USD",
        product_type="Spot",
        notional=Decimal("85000000"),
        desk_mark=Decimal("1.2648"),
        fair_value_level=FairValueLevel.L1,
    ),
    PositionInput(
        position_id="FX-SPOT-003",
        currency_pair="USD/JPY",
        product_type="Spot",
        notional=Decimal("50000000"),
        desk_mark=Decimal("149.85"),
        fair_value_level=FairValueLevel.L1,
    ),
    PositionInput(
        position_id="FX-SPOT-004",
        currency_pair="USD/TRY",
        product_type="Spot (EM)",
        notional=Decimal("25000000"),
        desk_mark=Decimal("32.45"),
        fair_value_level=FairValueLevel.L2,
    ),
    PositionInput(
        position_id="FX-SPOT-005",
        currency_pair="USD/BRL",
        product_type="Spot (EM)",
        notional=Decimal("10000000"),
        desk_mark=Decimal("5.12"),
        fair_value_level=FairValueLevel.L2,
    ),
    PositionInput(
        position_id="FX-FWD-001",
        currency_pair="EUR/USD",
        product_type="1Y Forward",
        notional=Decimal("120000000"),
        desk_mark=Decimal("1.095"),
        fair_value_level=FairValueLevel.L2,
    ),
    PositionInput(
        position_id="FX-OPT-001",
        currency_pair="EUR/USD",
        product_type="Barrier (DNT)",
        notional=Decimal("50000000"),
        desk_mark=Decimal("425000"),
        fair_value_level=FairValueLevel.L3,
        lower_barrier=Decimal("1.0500"),
        upper_barrier=Decimal("1.1200"),
        barrier_type="DNT",
        volatility=Decimal("0.0850"),
        time_to_expiry=Decimal("0.5"),
        domestic_rate=Decimal("0.0425"),
        foreign_rate=Decimal("0.0300"),
    ),
]


@router.post("/runs", response_model=IPVRunSummary, status_code=201)
async def start_ipv_run(
    request: IPVRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a new IPV run.

    Executes the full 8-step IPV pipeline for all positions or a subset.
    Supports real-time progress updates via WebSocket.
    """
    # Determine which positions to process
    if request.position_ids:
        positions = [
            p for p in REFERENCE_POSITIONS
            if p.position_id in request.position_ids
        ]
        if not positions:
            raise HTTPException(
                status_code=400,
                detail=f"No matching positions found for IDs: {request.position_ids}",
            )
    else:
        positions = REFERENCE_POSITIONS

    # Create pipeline and run
    pipeline = IPVPipeline(db=db, progress_callback=progress_callback)
    summary = await pipeline.run(request, positions)

    # Store in active runs
    async with _run_lock:
        _active_runs[summary.run_id] = summary

    return summary


@router.post("/runs/async", status_code=202)
async def start_ipv_run_async(
    request: IPVRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start an IPV run asynchronously.

    Returns immediately with the run_id. Monitor progress via WebSocket
    at /ipv/ws/{run_id} or poll GET /ipv/runs/{run_id}.
    """
    if request.position_ids:
        positions = [
            p for p in REFERENCE_POSITIONS
            if p.position_id in request.position_ids
        ]
        if not positions:
            raise HTTPException(
                status_code=400,
                detail=f"No matching positions found for IDs: {request.position_ids}",
            )
    else:
        positions = REFERENCE_POSITIONS

    pipeline = IPVPipeline(db=db, progress_callback=progress_callback)

    # Generate a preliminary run_id
    import uuid
    from datetime import datetime
    run_id = f"IPV-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

    async def _run_pipeline():
        try:
            summary = await pipeline.run(request, positions)
            async with _run_lock:
                _active_runs[summary.run_id] = summary
        except Exception as exc:
            log.error("async_pipeline_failed", run_id=run_id, error=str(exc))

    asyncio.create_task(_run_pipeline())

    return {
        "run_id": run_id,
        "message": "IPV run started asynchronously",
        "instructions": "Monitor progress via WebSocket at /ipv/ws or poll /ipv/runs",
    }


@router.get("/runs", response_model=list[IPVRunListItem])
async def list_ipv_runs(
    status: Optional[str] = None,
    valuation_date: Optional[date] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List recent IPV runs with optional filters."""
    stmt = select(IPVRun).order_by(IPVRun.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(IPVRun.status == status)
    if valuation_date:
        stmt = stmt.where(IPVRun.valuation_date == valuation_date)

    try:
        result = await db.execute(stmt)
        runs = result.scalars().all()
        return [
            IPVRunListItem(
                run_id=r.run_id,
                valuation_date=r.valuation_date,
                run_type=r.run_type,
                status=IPVRunStatus(r.status),
                triggered_by=r.triggered_by,
                started_at=r.started_at,
                completed_at=r.completed_at,
                total_positions=r.total_positions,
                green_count=r.green_count,
                amber_count=r.amber_count,
                red_count=r.red_count,
                exceptions_raised=r.exceptions_raised,
            )
            for r in runs
        ]
    except Exception:
        # Fallback: return from in-memory store if DB is unavailable
        items = list(_active_runs.values())
        return [
            IPVRunListItem(
                run_id=s.run_id,
                valuation_date=s.valuation_date,
                run_type=s.run_type,
                status=s.status,
                triggered_by=s.triggered_by,
                started_at=s.started_at,
                completed_at=s.completed_at,
                total_positions=s.total_positions,
                green_count=s.green_count,
                amber_count=s.amber_count,
                red_count=s.red_count,
                exceptions_raised=s.exceptions_raised,
            )
            for s in items[offset : offset + limit]
        ]


@router.get("/runs/{run_id}", response_model=IPVRunSummary)
async def get_ipv_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed results of a specific IPV run."""
    # Check in-memory first
    if run_id in _active_runs:
        return _active_runs[run_id]

    # Try database
    try:
        stmt = select(IPVRun).where(IPVRun.run_id == run_id)
        result = await db.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail=f"IPV run {run_id} not found")

        # Fetch step results
        steps_stmt = (
            select(IPVStepResult)
            .where(IPVStepResult.run_id == run_id)
            .order_by(IPVStepResult.step_number)
        )
        steps_result = await db.execute(steps_stmt)
        steps = steps_result.scalars().all()

        # Fetch position results
        pos_stmt = select(IPVPositionResult).where(IPVPositionResult.run_id == run_id)
        pos_result = await db.execute(pos_stmt)
        positions = pos_result.scalars().all()

        return IPVRunSummary(
            run_id=run.run_id,
            valuation_date=run.valuation_date,
            run_type=run.run_type,
            status=IPVRunStatus(run.status),
            triggered_by=run.triggered_by,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_seconds=run.duration_seconds,
            total_positions=run.total_positions,
            green_count=run.green_count,
            amber_count=run.amber_count,
            red_count=run.red_count,
            l1_count=run.l1_count,
            l2_count=run.l2_count,
            l3_count=run.l3_count,
            exceptions_raised=run.exceptions_raised,
            disputes_created=run.disputes_created,
            escalations_triggered=run.escalations_triggered,
            total_breach_amount_usd=run.total_breach_amount_usd or Decimal("0"),
            total_reserves_usd=run.total_reserves_usd or Decimal("0"),
            steps_completed=sum(1 for s in steps if s.status == "COMPLETED"),
            steps_total=8,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail=f"IPV run {run_id} not found")


@router.get("/positions")
async def list_reference_positions():
    """List the reference positions from the IPV FX Model Excel."""
    return [
        {
            "position_id": p.position_id,
            "currency_pair": p.currency_pair,
            "product_type": p.product_type,
            "notional": str(p.notional),
            "desk_mark": str(p.desk_mark),
            "fair_value_level": p.fair_value_level.value,
        }
        for p in REFERENCE_POSITIONS
    ]


@router.get("/thresholds")
async def get_tolerance_thresholds():
    """Return the current tolerance thresholds configuration."""
    return {
        "G10_Spot": {
            "green_bps": settings.fx_g10_spot_threshold_green_bps,
            "amber_bps": settings.fx_g10_spot_threshold_amber_bps,
            "description": "GREEN <5bps, AMBER 5-10bps, RED >10bps",
        },
        "EM_Spot": {
            "green_pct": settings.fx_em_spot_threshold_green_pct,
            "amber_pct": settings.fx_em_spot_threshold_amber_pct,
            "description": "GREEN <2%, AMBER 2-5%, RED >5%",
        },
        "FX_Forward": {
            "green_bps": settings.fx_forward_threshold_green_bps,
            "amber_bps": settings.fx_forward_threshold_amber_bps,
            "description": "GREEN <10bps, AMBER 10-20bps, RED >20bps",
        },
        "FX_Option": {
            "green_pct": settings.fx_option_threshold_green_pct,
            "amber_pct": settings.fx_option_threshold_amber_pct,
            "description": "GREEN <5%, AMBER 5-10%, RED >10%",
        },
    }


@router.get("/agents/health")
async def check_upstream_agents():
    """Check health of all upstream agents."""
    client = UpstreamClient()
    results = await client.check_all_agents()
    healthy = sum(1 for r in results if r["status"] == "healthy")
    return {
        "total": len(results),
        "healthy": healthy,
        "unhealthy": len(results) - healthy,
        "agents": results,
    }


@router.get("/ws-status")
async def websocket_status():
    """Return current WebSocket connection statistics."""
    return {
        "active_connections": manager.active_count,
        "subscriptions": manager.subscriptions,
    }

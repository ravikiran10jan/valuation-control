"""Day 1 P&L API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    Day1PnLResult,
    Day1PnLWithRedFlags,
    Day1PnLWithSchedule,
    PositionInput,
    RedFlagReport,
)
from app.services import day1_pnl as d1_svc
from app.services.red_flag_detector import detect_red_flags

router = APIRouter(prefix="/reserves/day1-pnl", tags=["Day 1 P&L"])


class Day1PnLWithRedFlagsRequest(BaseModel):
    """Request for Day 1 P&L with red flag analysis."""
    position: PositionInput
    recent_trade_count: Optional[int] = None
    average_trade_count: Optional[int] = None
    remark_count: Optional[int] = None
    remark_period_days: int = 30


class RedFlagCheckRequest(BaseModel):
    """Request for standalone red flag check (without Day 1 P&L calculation)."""
    position: PositionInput
    recent_trade_count: Optional[int] = None
    average_trade_count: Optional[int] = None
    remark_count: Optional[int] = None
    remark_period_days: int = 30


@router.post("/calculate", response_model=Day1PnLWithSchedule)
async def calculate_day1_pnl(
    position: PositionInput,
    db: AsyncSession = Depends(get_db),
):
    """Calculate Day 1 P&L and determine recognition status (IFRS 13)."""
    result = await d1_svc.calculate_day1_pnl(db, position)
    await db.commit()
    return result


@router.post("/calculate/with-red-flags", response_model=Day1PnLWithRedFlags)
async def calculate_day1_pnl_with_red_flags(
    req: Day1PnLWithRedFlagsRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate Day 1 P&L with full red flag analysis.

    Runs all 6 red flags from the Excel Day1_PnL_RedFlags sheet:
      1. Client Overpaid >20% (SEVERE)
      2. No Observable Market (Level 3)
      3. Bank Has Information Advantage
      4. Earnings Manipulation Risk
      5. Volume Spike at Period End
      6. Frequent Re-marks

    If a SEVERE red flag is triggered on a non-Level3 position,
    the Day 1 P&L is automatically deferred pending investigation.
    """
    result = await d1_svc.calculate_day1_pnl_with_red_flags(
        db,
        req.position,
        recent_trade_count=req.recent_trade_count,
        average_trade_count=req.average_trade_count,
        remark_count=req.remark_count,
        remark_period_days=req.remark_period_days,
    )
    await db.commit()
    return result


@router.post("/red-flags", response_model=RedFlagReport)
async def check_red_flags(
    req: RedFlagCheckRequest,
):
    """Run red flag checks without calculating Day 1 P&L.

    Useful for pre-trade red flag screening or standalone
    red flag assessment on existing positions.
    """
    return detect_red_flags(
        position=req.position,
        recent_trade_count=req.recent_trade_count,
        average_trade_count=req.average_trade_count,
        remark_count=req.remark_count,
        remark_period_days=req.remark_period_days,
    )


@router.get("/history/{position_id}", response_model=list[Day1PnLResult])
async def day1_pnl_history(
    position_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get historical Day 1 P&L records for a position."""
    return await d1_svc.get_day1_pnl_history(db, position_id)


# ── Enhanced Day 1 P&L Reserve endpoints ─────────────────────────

from app.models.schemas import (
    AmortizationMethod,
    Day1PnLReserve,
    Day1PnLPortfolioSummary,
)
from app.services import day1_pnl_reserve as d1_reserve_svc


class Day1PnLReserveRequest(BaseModel):
    """Request for enhanced Day 1 P&L reserve calculation."""
    position: PositionInput
    amortization_method: str = "STRAIGHT_LINE"  # STRAIGHT_LINE, FV_CONVERGENCE, ACCELERATED_RELEASE
    recent_trade_count: Optional[int] = None
    average_trade_count: Optional[int] = None
    remark_count: Optional[int] = None
    remark_period_days: int = 30


class Day1PnLPortfolioRequest(BaseModel):
    """Request for portfolio-level Day 1 P&L calculation."""
    positions: list[PositionInput]
    amortization_method: str = "STRAIGHT_LINE"


@router.post("/reserve/calculate", response_model=Day1PnLReserve)
async def calculate_day1_reserve(
    req: Day1PnLReserveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate Day 1 P&L with classification, reserve, amortization & accounting.

    Classifies the Day 1 P&L as SUSPICIOUS, NORMAL, or IDEAL based on:
      - |Day1 P&L| / FV > 20% -> SUSPICIOUS
      - Level 3 with |P&L| > 10% FV -> SUSPICIOUS
      - SEVERE red flags -> SUSPICIOUS
      - 2% < |Day1 P&L| / FV <= 20% -> NORMAL
      - |Day1 P&L| / FV <= 2% -> IDEAL

    Amortization methods: STRAIGHT_LINE, FV_CONVERGENCE, ACCELERATED_RELEASE

    Accounting: Dr Trading Revenue / Cr Day 1 P&L Reserve
    """
    method = AmortizationMethod(req.amortization_method)
    result = await d1_reserve_svc.calculate_day1_pnl_reserve(
        db,
        req.position,
        amortization_method=method,
        recent_trade_count=req.recent_trade_count,
        average_trade_count=req.average_trade_count,
        remark_count=req.remark_count,
        remark_period_days=req.remark_period_days,
    )
    await db.commit()
    return result


@router.post("/reserve/portfolio", response_model=Day1PnLPortfolioSummary)
async def calculate_portfolio_day1_reserve(
    req: Day1PnLPortfolioRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate Day 1 P&L reserves for a portfolio of positions.

    Returns aggregated summary with suspicious/normal/ideal counts
    and all accounting entries.
    """
    method = AmortizationMethod(req.amortization_method)
    result = await d1_reserve_svc.calculate_portfolio_day1_pnl(
        db, req.positions, amortization_method=method,
    )
    await db.commit()
    return result


@router.post("/reserve/release-expired", response_model=Day1PnLReserve)
async def release_expired_reserve(
    position: PositionInput,
    db: AsyncSession = Depends(get_db),
):
    """Release Day 1 P&L reserve for an expired position.

    Forces maturity_date to today to trigger expiry release logic.
    """
    from datetime import date as dt_date
    position.maturity_date = dt_date.today()
    result = await d1_reserve_svc.calculate_day1_pnl_reserve(db, position)
    await db.commit()
    return result

"""Day 1 P&L API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import Day1PnLResult, Day1PnLWithSchedule, PositionInput
from app.services import day1_pnl as d1_svc

router = APIRouter(prefix="/reserves/day1-pnl", tags=["Day 1 P&L"])


@router.post("/calculate", response_model=Day1PnLWithSchedule)
async def calculate_day1_pnl(
    position: PositionInput,
    db: AsyncSession = Depends(get_db),
):
    """Calculate Day 1 P&L and determine recognition status (IFRS 13)."""
    result = await d1_svc.calculate_day1_pnl(db, position)
    await db.commit()
    return result


@router.get("/history/{position_id}", response_model=list[Day1PnLResult])
async def day1_pnl_history(
    position_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get historical Day 1 P&L records for a position."""
    return await d1_svc.get_day1_pnl_history(db, position_id)

"""Reserve summary API endpoints — aggregated view across all reserve types."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.postgres import Reserve
from app.models.schemas import (
    FVAByAssetClass,
    PositionReserveRequest,
    PositionReserveResult,
    ReserveOut,
    ReserveSummary,
)
from app.services import ava as ava_svc
from app.services import day1_pnl as d1_svc
from app.services import fva as fva_svc
from app.services import model_reserve as mr_svc

router = APIRouter(prefix="/reserves", tags=["Reserves"])


@router.post("/calculate-all", response_model=PositionReserveResult)
async def calculate_all_reserves(
    req: PositionReserveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate FVA, AVA, Model Reserve, and Day 1 P&L for a single position."""
    pos = req.position

    fva_result = await fva_svc.calculate_fva(db, pos)

    ava_result = await ava_svc.calculate_ava(
        db,
        pos,
        dealer_quotes=req.dealer_quotes,
        model_results=req.model_results,
        total_book_value=req.total_book_value,
    )

    mr_result = None
    if req.model_results and len(req.model_results) >= 1:
        mr_result = await mr_svc.calculate_model_reserve(db, pos, req.model_results)

    d1_result = await d1_svc.calculate_day1_pnl(db, pos)

    await db.commit()

    total = (
        fva_result.fva_amount
        + ava_result.total_ava
        + (mr_result.model_reserve if mr_result else Decimal(0))
        + d1_result.deferred_amount
    )

    return PositionReserveResult(
        position_id=pos.position_id,
        fva=fva_result,
        ava=ava_result,
        model_reserve=mr_result,
        day1_pnl=d1_result,
        total_reserve=total,
        calculation_date=date.today(),
    )


@router.post("/calculate-batch", response_model=list[PositionReserveResult])
async def calculate_batch_reserves(
    requests: list[PositionReserveRequest],
    db: AsyncSession = Depends(get_db),
):
    """Calculate all reserves for multiple positions in one call."""
    results = []
    for req in requests:
        pos = req.position

        fva_result = await fva_svc.calculate_fva(db, pos)

        ava_result = await ava_svc.calculate_ava(
            db,
            pos,
            dealer_quotes=req.dealer_quotes,
            model_results=req.model_results,
            total_book_value=req.total_book_value,
        )

        mr_result = None
        if req.model_results and len(req.model_results) >= 1:
            mr_result = await mr_svc.calculate_model_reserve(db, pos, req.model_results)

        d1_result = await d1_svc.calculate_day1_pnl(db, pos)

        total = (
            fva_result.fva_amount
            + ava_result.total_ava
            + (mr_result.model_reserve if mr_result else Decimal(0))
            + d1_result.deferred_amount
        )

        results.append(
            PositionReserveResult(
                position_id=pos.position_id,
                fva=fva_result,
                ava=ava_result,
                model_reserve=mr_result,
                day1_pnl=d1_result,
                total_reserve=total,
                calculation_date=date.today(),
            )
        )

    await db.commit()
    return results


@router.get("/summary", response_model=ReserveSummary)
async def reserve_summary(
    calculation_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return an aggregated summary of all reserve types for a given date."""
    target_date = calculation_date or date.today()

    stmt = (
        select(Reserve.reserve_type, func.sum(Reserve.amount), func.count())
        .where(Reserve.calculation_date == target_date)
        .group_by(Reserve.reserve_type)
    )
    result = await db.execute(stmt)
    rows = result.all()

    totals: dict[str, Decimal] = {}
    count = 0
    for reserve_type, total, cnt in rows:
        totals[reserve_type] = total or Decimal(0)
        count += cnt

    fva = totals.get("FVA", Decimal(0))
    ava = totals.get("AVA", Decimal(0))
    model = totals.get("Model_Reserve", Decimal(0))
    d1 = totals.get("Day1_PnL", Decimal(0))

    return ReserveSummary(
        total_fva=fva,
        total_ava=ava,
        total_model_reserve=model,
        total_day1_deferred=d1,
        grand_total=fva + ava + model + d1,
        position_count=count,
        calculation_date=target_date,
    )


@router.get("/fva-by-asset-class", response_model=list[FVAByAssetClass])
async def fva_by_asset_class(
    calculation_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
):
    """Return FVA reserves grouped by asset class for chart display."""
    # This query joins reserves with a position_asset_class CTE
    # For now, parse asset class from the rationale/components or use position lookup
    target_date = calculation_date or date.today()

    stmt = (
        select(Reserve)
        .where(Reserve.reserve_type == "FVA", Reserve.calculation_date == target_date)
    )
    result = await db.execute(stmt)
    reserves = result.scalars().all()

    # Group by asset class from components if available
    by_class: dict[str, dict] = {}
    for r in reserves:
        ac = (r.components or {}).get("asset_class", "Unknown")
        if ac not in by_class:
            by_class[ac] = {"total_fva": Decimal(0), "count": 0}
        by_class[ac]["total_fva"] += r.amount
        by_class[ac]["count"] += 1

    return [
        FVAByAssetClass(
            asset_class=ac,
            total_fva=data["total_fva"],
            position_count=data["count"],
        )
        for ac, data in by_class.items()
    ]


@router.get("/by-position/{position_id}", response_model=list[ReserveOut])
async def reserves_by_position(
    position_id: int,
    reserve_type: Optional[str] = Query(None, description="FVA, AVA, Model_Reserve, Day1_PnL"),
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Return all reserves for a single position, optionally filtered by type."""
    stmt = select(Reserve).where(Reserve.position_id == position_id)
    if reserve_type:
        stmt = stmt.where(Reserve.reserve_type == reserve_type)
    stmt = stmt.order_by(Reserve.calculation_date.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())

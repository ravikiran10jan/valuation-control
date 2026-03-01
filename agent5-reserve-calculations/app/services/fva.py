"""FVA (Fair Value Adjustment) calculator.

FVA = Desk Mark - VC Fair Value  (only when VC < Desk, conservative approach).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import Reserve
from app.models.schemas import FVAResult, FVAAggregateResult, PositionInput

log = structlog.get_logger()


async def calculate_fva(db: AsyncSession, position: PositionInput) -> FVAResult:
    """Compute FVA for a single position and persist the reserve."""
    desk_mark = position.desk_mark or Decimal(0)
    vc_fv = position.vc_fair_value or Decimal(0)

    # FVA only applies when VC is more conservative (lower) than the desk mark
    if vc_fv < desk_mark:
        fva = desk_mark - vc_fv
    else:
        fva = Decimal(0)

    rationale = (
        f"VC FV ${vc_fv:,.0f} < Desk ${desk_mark:,.0f}"
        if fva > 0
        else "No FVA required: VC >= Desk"
    )

    calc_date = date.today()

    reserve = Reserve(
        position_id=position.position_id,
        reserve_type="FVA",
        amount=fva,
        calculation_date=calc_date,
        rationale=rationale,
    )
    db.add(reserve)
    await db.flush()

    log.info(
        "fva_calculated",
        position_id=position.position_id,
        fva=float(fva),
    )

    return FVAResult(
        position_id=position.position_id,
        fva_amount=fva,
        desk_mark=desk_mark,
        vc_fair_value=vc_fv,
        rationale=rationale,
        calculation_date=calc_date,
    )


async def aggregate_fva(
    db: AsyncSession,
    positions: list[PositionInput],
    asset_class: str | None = None,
) -> FVAAggregateResult:
    """Compute total FVA across a set of positions."""
    details: list[FVAResult] = []
    for pos in positions:
        result = await calculate_fva(db, pos)
        details.append(result)

    await db.commit()

    total = sum((d.fva_amount for d in details), Decimal(0))

    return FVAAggregateResult(
        total_fva=total,
        position_count=len(details),
        asset_class=asset_class,
        details=details,
    )


async def get_fva_history(
    db: AsyncSession,
    position_id: int,
    limit: int = 30,
) -> list[Reserve]:
    """Return historical FVA reserves for a position."""
    stmt = (
        select(Reserve)
        .where(Reserve.position_id == position_id, Reserve.reserve_type == "FVA")
        .order_by(Reserve.calculation_date.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

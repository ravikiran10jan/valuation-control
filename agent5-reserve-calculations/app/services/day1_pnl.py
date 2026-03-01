"""Day 1 P&L recognition per IFRS 13 / ASC 820.

Rules:
  - Level 1 / Level 2: recognise immediately (all inputs observable)
  - Level 3: defer and amortise over the life of the instrument
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from dateutil.relativedelta import relativedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import AmortizationSchedule, Day1PnL as Day1PnLRow, Reserve
from app.models.schemas import (
    AmortizationEntry,
    Day1PnLResult,
    Day1PnLWithSchedule,
    PositionInput,
)

log = structlog.get_logger()


async def calculate_day1_pnl(
    db: AsyncSession,
    position: PositionInput,
) -> Day1PnLWithSchedule:
    """Compute Day 1 P&L, decide recognition, and build amortization if deferred."""
    transaction_price = position.transaction_price or Decimal(0)
    fair_value = position.vc_fair_value or Decimal(0)

    day1_pnl = transaction_price - fair_value

    if position.classification == "Level3":
        recognition_status = "DEFERRED"
        recognized_amount = Decimal(0)
        deferred_amount = day1_pnl
    else:
        recognition_status = "RECOGNIZED"
        recognized_amount = day1_pnl
        deferred_amount = Decimal(0)

    # Persist Day1PnL row
    pnl_row = Day1PnLRow(
        position_id=position.position_id,
        transaction_price=transaction_price,
        fair_value=fair_value,
        day1_pnl=day1_pnl,
        recognition_status=recognition_status,
        recognized_amount=recognized_amount,
        deferred_amount=deferred_amount,
        trade_date=position.trade_date,
    )
    db.add(pnl_row)

    # Also persist into unified reserves table
    reserve = Reserve(
        position_id=position.position_id,
        reserve_type="Day1_PnL",
        amount=deferred_amount,
        calculation_date=date.today(),
        rationale=(
            f"Day1 P&L ${float(day1_pnl):,.0f} — {recognition_status}; "
            f"Txn ${float(transaction_price):,.0f} vs FV ${float(fair_value):,.0f}"
        ),
    )
    db.add(reserve)

    # Build amortization schedule for deferred amounts
    schedule: list[AmortizationEntry] = []
    if recognition_status == "DEFERRED" and deferred_amount != 0:
        schedule = await _create_amortization_schedule(
            db, position.position_id, deferred_amount, position.trade_date, position.maturity_date
        )

    await db.flush()

    log.info(
        "day1_pnl_calculated",
        position_id=position.position_id,
        day1_pnl=float(day1_pnl),
        status=recognition_status,
    )

    return Day1PnLWithSchedule(
        position_id=position.position_id,
        transaction_price=transaction_price,
        fair_value=fair_value,
        day1_pnl=day1_pnl,
        recognition_status=recognition_status,
        recognized_amount=recognized_amount,
        deferred_amount=deferred_amount,
        trade_date=position.trade_date,
        amortization_schedule=schedule,
    )


async def _create_amortization_schedule(
    db: AsyncSession,
    position_id: int,
    deferred_amount: Decimal,
    trade_date: date | None,
    maturity_date: date | None,
) -> list[AmortizationEntry]:
    """Generate a monthly straight-line amortization schedule."""
    start = trade_date or date.today()
    end = maturity_date or start + relativedelta(years=1)

    if end <= start:
        return []

    # Count monthly periods
    periods: list[date] = []
    current = start + relativedelta(months=1)
    while current <= end:
        periods.append(current)
        current += relativedelta(months=1)

    if not periods:
        periods = [end]

    monthly_amount = deferred_amount / Decimal(len(periods))
    entries: list[AmortizationEntry] = []
    cumulative = Decimal(0)

    for period_date in periods:
        cumulative += monthly_amount
        remaining = deferred_amount - cumulative

        row = AmortizationSchedule(
            position_id=position_id,
            period_date=period_date,
            amortization_amount=monthly_amount,
            cumulative_recognized=cumulative,
            remaining_deferred=remaining,
        )
        db.add(row)

        entries.append(
            AmortizationEntry(
                period_date=period_date,
                amortization_amount=monthly_amount,
                cumulative_recognized=cumulative,
                remaining_deferred=remaining,
            )
        )

    return entries


async def get_day1_pnl_history(
    db: AsyncSession,
    position_id: int,
) -> list[Day1PnLRow]:
    """Return historical Day 1 P&L records for a position."""
    stmt = (
        select(Day1PnLRow)
        .where(Day1PnLRow.position_id == position_id)
        .order_by(Day1PnLRow.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())

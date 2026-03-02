"""FVA (Fair Value Adjustment) calculator.

Two modes:
  1. Simple FVA: Desk Mark - VC Fair Value (when VC < Desk, conservative approach)
  2. Premium-based FVA: Premium Paid - Fair Value at inception, amortized over life

The premium-based FVA matches the Excel model:
  - Barrier option: Premium $425k - Fair Value $310k = $115,000 FVA
  - Monthly release: $115,000 / 11 months = $10,455/month
  - Full amortization schedule with dates
  - FVA balance tracks from $115k -> $0 at maturity
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

import structlog
from dateutil.relativedelta import relativedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import Reserve
from app.models.schemas import (
    FVAAmortizationEntry,
    FVAResult,
    FVAWithAmortization,
    FVAAggregateResult,
    PositionInput,
)

log = structlog.get_logger()


def _round2(value: Decimal) -> Decimal:
    """Round to 2 decimal places."""
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def calculate_fva(db: AsyncSession, position: PositionInput) -> FVAResult:
    """Compute FVA for a single position and persist the reserve.

    Standard mode: FVA = max(0, desk_mark - vc_fair_value)
    """
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


async def calculate_premium_fva(
    db: AsyncSession,
    position: PositionInput,
    premium_paid: Decimal,
    fair_value_at_inception: Decimal | None = None,
) -> FVAWithAmortization:
    """Compute premium-based FVA with full amortization schedule.

    Matches the Excel FVA sheet:
      FVA = Premium Paid - Fair Value at inception
      Monthly release = FVA / months to maturity
      Amortization runs from trade date + 1 month through maturity

    For barrier option example:
      Premium = $425,000
      FV at inception = $310,000
      FVA = $115,000
      Months to maturity = 11
      Monthly release = $10,454.55
      Schedule: 11 entries, balance from $115k -> $0
    """
    fv_inception = fair_value_at_inception or (position.vc_fair_value or Decimal(0))
    calc_date = date.today()

    # Total FVA = premium paid above fair value
    total_fva = premium_paid - fv_inception
    if total_fva < 0:
        total_fva = Decimal(0)

    # Calculate months to maturity
    trade_dt = position.trade_date or calc_date
    maturity_dt = position.maturity_date

    if maturity_dt is None or maturity_dt <= trade_dt:
        # No amortization possible
        rationale = (
            f"Premium ${premium_paid:,.0f} - FV ${fv_inception:,.0f} = "
            f"FVA ${total_fva:,.0f}; no amortization (no valid maturity)"
        )

        reserve = Reserve(
            position_id=position.position_id,
            reserve_type="FVA",
            amount=total_fva,
            calculation_date=calc_date,
            rationale=rationale,
            components={
                "premium_paid": float(premium_paid),
                "fair_value_at_inception": float(fv_inception),
                "total_fva": float(total_fva),
            },
        )
        db.add(reserve)
        await db.flush()

        return FVAWithAmortization(
            position_id=position.position_id,
            fva_amount=total_fva,
            desk_mark=position.desk_mark,
            vc_fair_value=position.vc_fair_value,
            rationale=rationale,
            calculation_date=calc_date,
            premium_paid=premium_paid,
            fair_value_at_inception=fv_inception,
            total_fva=total_fva,
            months_to_maturity=0,
            monthly_release=Decimal(0),
            amortization_schedule=[],
        )

    # Count months between trade date and maturity
    months = 0
    check_date = trade_dt + relativedelta(months=1)
    while check_date <= maturity_dt:
        months += 1
        check_date += relativedelta(months=1)

    if months == 0:
        months = 1  # At least 1 period

    monthly_release = _round2(total_fva / Decimal(months))

    # Build amortization schedule
    schedule: list[FVAAmortizationEntry] = []
    opening_balance = total_fva

    for i in range(1, months + 1):
        period_date = trade_dt + relativedelta(months=i)

        # Last period absorbs rounding difference
        if i == months:
            release = opening_balance
        else:
            release = monthly_release

        closing_balance = _round2(opening_balance - release)
        if closing_balance < 0:
            closing_balance = Decimal(0)

        schedule.append(
            FVAAmortizationEntry(
                period_number=i,
                period_date=period_date,
                opening_balance=_round2(opening_balance),
                monthly_release=_round2(release),
                closing_balance=closing_balance,
            )
        )

        opening_balance = closing_balance

    rationale = (
        f"Premium ${premium_paid:,.0f} - FV ${fv_inception:,.0f} = "
        f"FVA ${total_fva:,.0f}; "
        f"amortized over {months} months at ${float(monthly_release):,.2f}/month"
    )

    # Persist reserve
    reserve = Reserve(
        position_id=position.position_id,
        reserve_type="FVA",
        amount=total_fva,
        calculation_date=calc_date,
        rationale=rationale,
        components={
            "premium_paid": float(premium_paid),
            "fair_value_at_inception": float(fv_inception),
            "total_fva": float(total_fva),
            "months_to_maturity": months,
            "monthly_release": float(monthly_release),
            "schedule_count": len(schedule),
        },
    )
    db.add(reserve)
    await db.flush()

    log.info(
        "premium_fva_calculated",
        position_id=position.position_id,
        premium=float(premium_paid),
        fv_inception=float(fv_inception),
        total_fva=float(total_fva),
        months=months,
        monthly_release=float(monthly_release),
    )

    return FVAWithAmortization(
        position_id=position.position_id,
        fva_amount=total_fva,
        desk_mark=position.desk_mark,
        vc_fair_value=position.vc_fair_value,
        rationale=rationale,
        calculation_date=calc_date,
        premium_paid=premium_paid,
        fair_value_at_inception=fv_inception,
        total_fva=total_fva,
        months_to_maturity=months,
        monthly_release=monthly_release,
        amortization_schedule=schedule,
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

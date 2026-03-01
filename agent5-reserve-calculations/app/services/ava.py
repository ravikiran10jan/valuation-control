"""AVA (Additional Valuation Adjustment) calculator — Basel III Article 105.

Seven categories:
  1. Market Price Uncertainty (MPU)
  2. Close-Out Costs
  3. Model Risk
  4. Unearned Credit Spreads
  5. Investment & Funding Costs
  6. Concentrated Positions
  7. Future Administrative Costs
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.postgres import AVADetail, Reserve
from app.models.schemas import (
    AVAComponents,
    AVAResult,
    AVAAggregateResult,
    DealerQuoteInput,
    ModelComparisonEntry,
    PositionInput,
)

log = structlog.get_logger()

# Level multipliers for MPU
_MPU_MULTIPLIERS: dict[str, Decimal] = {
    "Level1": Decimal("1.0"),
    "Level2": Decimal("1.5"),
    "Level3": Decimal("2.83"),
}

# Industry-standard model-risk percentages
_MODEL_RISK_PCT: dict[str, Decimal] = {
    "Level1": Decimal("0.02"),
    "Level2": Decimal("0.05"),
    "Level3": Decimal("0.07"),
}


# ── Individual AVA category calculators ──────────────────────────


def _calculate_mpu(
    position: PositionInput,
    dealer_quotes: list[DealerQuoteInput] | None,
) -> Decimal:
    """Category 1: Market Price Uncertainty — based on dealer-quote spread."""
    vc_fv = position.vc_fair_value or Decimal(0)

    if not dealer_quotes or len(dealer_quotes) < 3:
        # Fallback: percentage of FV
        return abs(vc_fv) * Decimal(str(settings.ava_mpu_fallback_pct))

    high = max(q.value for q in dealer_quotes)
    low = min(q.value for q in dealer_quotes)
    spread = high - low

    mpu_base = spread / 2

    level = position.classification
    multiplier = _MPU_MULTIPLIERS.get(level, Decimal("1.5"))
    return mpu_base * multiplier


def _calculate_close_out(mpu: Decimal) -> Decimal:
    """Category 2: Close-Out Costs — 50 % of MPU (one side of bid-ask)."""
    return mpu * Decimal("0.50")


def _calculate_model_risk(
    position: PositionInput,
    model_results: list[ModelComparisonEntry] | None,
) -> Decimal:
    """Category 3: Model Risk — largest AVA driver."""
    vc_fv = abs(position.vc_fair_value or Decimal(0))
    level = position.classification

    industry_pct = _MODEL_RISK_PCT.get(level, Decimal("0.05"))
    industry_ava = vc_fv * industry_pct

    if model_results and len(model_results) >= 3:
        values = [Decimal(str(m.value)) for m in model_results]
        model_range = max(values) - min(values)
        range_ava = model_range / 2
        return max(range_ava, industry_ava)

    return industry_ava


def _calculate_credit_spreads(position: PositionInput) -> Decimal:
    """Category 4: Unearned Credit Spreads — credit products only."""
    if position.asset_class in ("Credit", "Structured_Credit"):
        # Placeholder — real implementation depends on specific product cash-flow
        return Decimal(0)
    return Decimal(0)


def _calculate_funding(position: PositionInput) -> Decimal:
    """Category 5: Investment & Funding Costs — long positions only."""
    if position.position_direction != "LONG":
        return Decimal(0)

    vc_fv = abs(position.vc_fair_value or Decimal(0))
    funding_spread = Decimal(str(settings.ava_funding_spread_bps)) / Decimal("10000")

    if position.maturity_date is None:
        return Decimal(0)

    ttm = Decimal((position.maturity_date - date.today()).days) / Decimal("365")
    if ttm <= 0:
        return Decimal(0)

    return vc_fv * funding_spread * ttm


def _calculate_concentration(
    position: PositionInput,
    total_book_value: Decimal | None,
) -> Decimal:
    """Category 6: Concentrated Positions — flag only, multiplier applied elsewhere."""
    if total_book_value is None or total_book_value == 0:
        return Decimal(0)

    vc_fv = abs(position.vc_fair_value or Decimal(0))
    concentration_pct = vc_fv / total_book_value

    if concentration_pct > Decimal("0.05"):
        # Informational — multiplier applied at aggregate level
        return Decimal(0)

    return Decimal(0)


def _calculate_admin(position: PositionInput) -> Decimal:
    """Category 7: Future Administrative Costs — 10 bps p.a."""
    vc_fv = abs(position.vc_fair_value or Decimal(0))
    admin_rate = Decimal(str(settings.ava_admin_rate_bps)) / Decimal("10000")

    if position.maturity_date is None:
        return Decimal(0)

    ttm = Decimal((position.maturity_date - date.today()).days) / Decimal("365")
    if ttm <= 0:
        return Decimal(0)

    admin_ava = vc_fv * admin_rate * ttm

    if position.classification == "Level3":
        admin_ava *= Decimal("1.58")

    return admin_ava


# ── Public entry-points ──────────────────────────────────────────


async def calculate_ava(
    db: AsyncSession,
    position: PositionInput,
    dealer_quotes: list[DealerQuoteInput] | None = None,
    model_results: list[ModelComparisonEntry] | None = None,
    total_book_value: Decimal | None = None,
) -> AVAResult:
    """Compute all 7 AVA categories for a single position and persist."""
    mpu = _calculate_mpu(position, dealer_quotes)
    close_out = _calculate_close_out(mpu)
    model_risk = _calculate_model_risk(position, model_results)
    credit_spreads = _calculate_credit_spreads(position)
    funding = _calculate_funding(position)
    concentration = _calculate_concentration(position, total_book_value)
    admin = _calculate_admin(position)

    total_ava = mpu + close_out + model_risk + credit_spreads + funding + concentration + admin
    calc_date = date.today()

    components = AVAComponents(
        mpu=mpu,
        close_out=close_out,
        model_risk=model_risk,
        credit_spreads=credit_spreads,
        funding=funding,
        concentration=concentration,
        admin=admin,
    )

    # Persist AVA detail row
    ava_row = AVADetail(
        position_id=position.position_id,
        total_ava=total_ava,
        mpu=mpu,
        close_out=close_out,
        model_risk=model_risk,
        credit_spreads=credit_spreads,
        funding=funding,
        concentration=concentration,
        admin=admin,
        calculation_date=calc_date,
    )
    db.add(ava_row)

    # Also persist into unified reserves table
    reserve = Reserve(
        position_id=position.position_id,
        reserve_type="AVA",
        amount=total_ava,
        calculation_date=calc_date,
        rationale=f"AVA total across 7 Basel III categories",
        components={
            "mpu": float(mpu),
            "close_out": float(close_out),
            "model_risk": float(model_risk),
            "credit_spreads": float(credit_spreads),
            "funding": float(funding),
            "concentration": float(concentration),
            "admin": float(admin),
        },
    )
    db.add(reserve)
    await db.flush()

    log.info(
        "ava_calculated",
        position_id=position.position_id,
        total_ava=float(total_ava),
    )

    return AVAResult(
        position_id=position.position_id,
        total_ava=total_ava,
        components=components,
        calculation_date=calc_date,
    )


async def aggregate_ava(
    db: AsyncSession,
    positions: list[PositionInput],
    dealer_quotes_map: dict[int, list[DealerQuoteInput]] | None = None,
    model_results_map: dict[int, list[ModelComparisonEntry]] | None = None,
    total_book_value: Decimal | None = None,
) -> AVAAggregateResult:
    """Compute AVA across many positions and return category-level totals."""
    details: list[AVAResult] = []
    dq_map = dealer_quotes_map or {}
    mr_map = model_results_map or {}

    for pos in positions:
        result = await calculate_ava(
            db,
            pos,
            dealer_quotes=dq_map.get(pos.position_id),
            model_results=mr_map.get(pos.position_id),
            total_book_value=total_book_value,
        )
        details.append(result)

    await db.commit()

    total = sum((d.total_ava for d in details), Decimal(0))
    cat = AVAComponents(
        mpu=sum((d.components.mpu for d in details), Decimal(0)),
        close_out=sum((d.components.close_out for d in details), Decimal(0)),
        model_risk=sum((d.components.model_risk for d in details), Decimal(0)),
        credit_spreads=sum((d.components.credit_spreads for d in details), Decimal(0)),
        funding=sum((d.components.funding for d in details), Decimal(0)),
        concentration=sum((d.components.concentration for d in details), Decimal(0)),
        admin=sum((d.components.admin for d in details), Decimal(0)),
    )

    return AVAAggregateResult(
        total_ava=total,
        position_count=len(details),
        category_totals=cat,
        details=details,
    )

"""Model Reserve calculator.

Reserves for model uncertainty — distinct from AVA Model Risk:
  - Model Reserve: P&L impact (taken through P&L statement)
  - AVA Model Risk: CET1 capital deduction
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.postgres import Reserve
from app.models.schemas import ModelComparisonEntry, ModelReserveResult, PositionInput

log = structlog.get_logger()


async def calculate_model_reserve(
    db: AsyncSession,
    position: PositionInput,
    model_results: list[ModelComparisonEntry],
) -> ModelReserveResult:
    """Compute model reserve as a fraction of the model-range and persist."""
    if not model_results:
        raise ValueError(f"No model results provided for position {position.position_id}")

    values = [Decimal(str(m.value)) for m in model_results]
    model_range = max(values) - min(values)

    reserve_pct = Decimal(str(settings.model_reserve_pct))
    model_reserve = model_range * reserve_pct

    calc_date = date.today()

    reserve = Reserve(
        position_id=position.position_id,
        reserve_type="Model_Reserve",
        amount=model_reserve,
        calculation_date=calc_date,
        rationale=(
            f"Model range ${float(model_range):,.0f} across "
            f"{len(model_results)} models; reserve = {float(reserve_pct)*100:.0f}% of range"
        ),
        components={
            "model_comparison": [m.model_dump() for m in model_results],
            "model_range": float(model_range),
        },
    )
    db.add(reserve)
    await db.flush()

    log.info(
        "model_reserve_calculated",
        position_id=position.position_id,
        model_reserve=float(model_reserve),
        model_count=len(model_results),
    )

    return ModelReserveResult(
        position_id=position.position_id,
        model_reserve=model_reserve,
        model_range=model_range,
        model_comparison=model_results,
        calculation_date=calc_date,
    )

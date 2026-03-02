"""FVA reserve API endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    FVAAggregateResult,
    FVAResult,
    FVAWithAmortization,
    PositionInput,
    ReserveOut,
)
from app.services import fva as fva_svc

router = APIRouter(prefix="/reserves/fva", tags=["FVA"])


class PremiumFVARequest(BaseModel):
    """Request for premium-based FVA calculation with amortization schedule."""
    position: PositionInput
    premium_paid: Decimal
    fair_value_at_inception: Optional[Decimal] = None


@router.post("/calculate", response_model=FVAResult)
async def calculate_fva(
    position: PositionInput,
    db: AsyncSession = Depends(get_db),
):
    """Calculate FVA for a single position (standard desk mark vs VC fair value)."""
    result = await fva_svc.calculate_fva(db, position)
    await db.commit()
    return result


@router.post("/calculate/premium", response_model=FVAWithAmortization)
async def calculate_premium_fva(
    req: PremiumFVARequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate premium-based FVA with full amortization schedule.

    Matches the Excel FVA sheet:
      FVA = Premium Paid - Fair Value at inception
      Monthly release = FVA / months to maturity
      Full schedule from trade date to maturity

    Example (Barrier Option):
      Premium = $425,000
      FV at inception = $310,000
      FVA = $115,000
      Months to maturity = 11
      Monthly release = $10,454.55/month
    """
    result = await fva_svc.calculate_premium_fva(
        db,
        req.position,
        premium_paid=req.premium_paid,
        fair_value_at_inception=req.fair_value_at_inception,
    )
    await db.commit()
    return result


@router.post("/calculate/batch", response_model=FVAAggregateResult)
async def calculate_fva_batch(
    positions: list[PositionInput],
    asset_class: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Calculate FVA across multiple positions."""
    return await fva_svc.aggregate_fva(db, positions, asset_class)


@router.get("/history/{position_id}", response_model=list[ReserveOut])
async def fva_history(
    position_id: int,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Get historical FVA reserves for a position."""
    return await fva_svc.get_fva_history(db, position_id, limit)

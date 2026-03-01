"""FVA reserve API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    FVAAggregateResult,
    FVAResult,
    PositionInput,
    ReserveOut,
)
from app.services import fva as fva_svc

router = APIRouter(prefix="/reserves/fva", tags=["FVA"])


@router.post("/calculate", response_model=FVAResult)
async def calculate_fva(
    position: PositionInput,
    db: AsyncSession = Depends(get_db),
):
    """Calculate FVA for a single position."""
    result = await fva_svc.calculate_fva(db, position)
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

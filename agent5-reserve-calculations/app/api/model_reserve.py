"""Model Reserve API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import ModelComparisonEntry, ModelReserveResult, PositionInput
from app.services import model_reserve as mr_svc

router = APIRouter(prefix="/reserves/model-reserve", tags=["Model Reserve"])


class ModelReserveRequest(BaseModel):
    position: PositionInput
    model_results: list[ModelComparisonEntry]


@router.post("/calculate", response_model=ModelReserveResult)
async def calculate_model_reserve(
    req: ModelReserveRequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate model reserve for a single position given model comparison data."""
    result = await mr_svc.calculate_model_reserve(db, req.position, req.model_results)
    await db.commit()
    return result

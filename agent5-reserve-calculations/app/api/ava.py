"""AVA (Additional Valuation Adjustment) API endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    AVAAggregateResult,
    AVAResult,
    DealerQuoteInput,
    DetailedAVAResult,
    ModelComparisonEntry,
    ModelComparisonInput,
    PositionInput,
)
from app.services import ava as ava_svc

router = APIRouter(prefix="/reserves/ava", tags=["AVA"])


class SingleAVARequest(BaseModel):
    position: PositionInput
    dealer_quotes: Optional[list[DealerQuoteInput]] = None
    model_results: Optional[list[ModelComparisonEntry]] = None
    total_book_value: Optional[Decimal] = None


class DetailedAVARequest(BaseModel):
    """Request for detailed AVA calculation matching the Excel AVA_Calculation sheet."""
    position: PositionInput
    dealer_quotes: Optional[list[DealerQuoteInput]] = None
    model_comparisons: Optional[list[ModelComparisonInput]] = None
    model_results: Optional[list[ModelComparisonEntry]] = None
    total_book_value: Optional[Decimal] = None


class BatchAVARequest(BaseModel):
    positions: list[PositionInput]
    dealer_quotes_map: Optional[dict[int, list[DealerQuoteInput]]] = None
    model_results_map: Optional[dict[int, list[ModelComparisonEntry]]] = None
    total_book_value: Optional[Decimal] = None


@router.post("/calculate", response_model=AVAResult)
async def calculate_ava(
    req: SingleAVARequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate all 7 AVA categories for a single position."""
    result = await ava_svc.calculate_ava(
        db,
        req.position,
        dealer_quotes=req.dealer_quotes,
        model_results=req.model_results,
        total_book_value=req.total_book_value,
    )
    await db.commit()
    return result


@router.post("/calculate/detailed", response_model=DetailedAVAResult)
async def calculate_detailed_ava(
    req: DetailedAVARequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate all 7 AVA categories with full sub-calculation breakdowns.

    This endpoint matches the Excel AVA_Calculation sheet, returning all
    intermediate calculation steps for each of the 7 categories:

    1. MPU: Dealer quote spread, level multiplier, adjusted MPU
    2. Close-Out: 50% of MPU with validation cross-check
    3. Model Risk: 3-method comparison (range/2, industry %, param sensitivity)
    4. Credit Spreads: Applicability check by asset class
    5. Funding: Position direction, TTM, funding spread
    6. Concentration: Book percentage check with 5% threshold
    7. Admin: Base rate with Level 3 multiplier (1.58x)

    Total AVA is deducted from CET1 capital.
    """
    result = await ava_svc.calculate_detailed_ava(
        db,
        req.position,
        dealer_quotes=req.dealer_quotes,
        model_comparisons=req.model_comparisons,
        model_results=req.model_results,
        total_book_value=req.total_book_value,
    )
    await db.commit()
    return result


@router.post("/calculate/batch", response_model=AVAAggregateResult)
async def calculate_ava_batch(
    req: BatchAVARequest,
    db: AsyncSession = Depends(get_db),
):
    """Calculate AVA across multiple positions with category-level totals."""
    return await ava_svc.aggregate_ava(
        db,
        req.positions,
        dealer_quotes_map=req.dealer_quotes_map,
        model_results_map=req.model_results_map,
        total_book_value=req.total_book_value,
    )

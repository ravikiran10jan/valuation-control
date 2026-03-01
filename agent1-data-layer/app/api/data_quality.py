"""Data quality monitoring API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter

from app.models.schemas import DataQualitySummary
from app.services.data_quality import compute_quality_summary

router = APIRouter(prefix="/data-quality", tags=["Data Quality"])


@router.get("/", response_model=DataQualitySummary)
async def get_quality_summary(valuation_date: Optional[str] = None):
    """Return data quality metrics for a given valuation date (defaults to today)."""
    as_of = date.fromisoformat(valuation_date) if valuation_date else None
    return await compute_quality_summary(as_of)

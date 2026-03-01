"""Proxy routes for comparison and valuation operations."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.upstream import agent1_get, agent1_post

router = APIRouter(prefix="/api/valuations", tags=["Valuations"])


@router.post("/trigger")
async def trigger_batch_valuation(asset_class: Optional[str] = None):
    """Trigger batch comparison for all positions (or by asset class)."""
    params = {}
    if asset_class:
        params["asset_class"] = asset_class
    return await agent1_post(f"/comparisons/run-batch", json=params)


@router.get("/history/{position_id}")
async def get_comparison_history(
    position_id: int,
    limit: int = Query(30, le=365),
):
    """Get valuation comparison history for a position."""
    return await agent1_get(
        f"/comparisons/history/{position_id}",
        params={"limit": limit},
    )

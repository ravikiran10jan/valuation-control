"""Proxy routes for Agent 5 reserve endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.upstream import agent5_get, agent5_post

router = APIRouter(prefix="/api/reserves", tags=["Reserves"])


@router.get("/summary")
async def get_reserve_summary(calculation_date: Optional[str] = None):
    """Aggregated reserve summary from Agent 5."""
    params = {}
    if calculation_date:
        params["calculation_date"] = calculation_date
    return await agent5_get("/reserves/summary", params=params)


@router.get("/by-position/{position_id}")
async def get_reserves_for_position(
    position_id: int,
    reserve_type: Optional[str] = None,
):
    """Reserves for a specific position."""
    params = {}
    if reserve_type:
        params["reserve_type"] = reserve_type
    return await agent5_get(f"/reserves/by-position/{position_id}", params=params)


@router.post("/fva/calculate/batch")
async def trigger_fva_batch(asset_class: Optional[str] = None):
    """Trigger batch FVA recalculation."""
    body = {}
    if asset_class:
        body["asset_class"] = asset_class
    return await agent5_post("/reserves/fva/calculate/batch", json=body)

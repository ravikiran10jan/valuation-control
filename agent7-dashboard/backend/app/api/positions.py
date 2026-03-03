"""Proxy routes for Agent 1 position endpoints and enriched detail."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.upstream import agent1_get
from app.services.dashboard import get_position_detail

router = APIRouter(prefix="/api/positions", tags=["Positions"])


@router.get("/")
async def list_positions(
    asset_class: Optional[str] = None,
    exception_status: Optional[str] = None,
    limit: int = Query(100, le=10000),
    offset: int = 0,
):
    """List positions (proxied from Agent 1)."""
    params = {"limit": limit, "offset": offset}
    if asset_class:
        params["asset_class"] = asset_class
    if exception_status:
        params["exception_status"] = exception_status
    try:
        return await agent1_get("/positions/", params=params)
    except Exception:
        return []


@router.get("/{position_id}")
async def get_position(position_id: int):
    """Get enriched position detail with reserves and comparison history."""
    return await get_position_detail(position_id)

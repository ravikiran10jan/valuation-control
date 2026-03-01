"""Proxy routes for Agent 1 exception endpoints.

These thin proxies forward requests from the frontend to Agent 1,
keeping the frontend decoupled from internal service topology.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.services.upstream import agent1_get, agent1_post

router = APIRouter(prefix="/api/exceptions", tags=["Exceptions"])


@router.get("/")
async def list_exceptions(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    asset_class: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    """List exceptions (proxied from Agent 1)."""
    params = {"limit": limit, "offset": offset}
    if severity:
        params["severity"] = severity
    if status:
        params["status"] = status
    if asset_class:
        params["asset_class"] = asset_class
    if assigned_to:
        params["assigned_to"] = assigned_to
    return await agent1_get("/exceptions/", params=params)


@router.get("/summary")
async def get_exception_summary():
    """Exception summary statistics."""
    return await agent1_get("/exceptions/summary")


@router.get("/statistics")
async def get_exception_statistics():
    """Detailed exception analytics."""
    return await agent1_get("/exceptions/statistics")


@router.get("/{exception_id}")
async def get_exception_detail(exception_id: int):
    """Full exception detail with position and comments."""
    return await agent1_get(f"/exceptions/{exception_id}")

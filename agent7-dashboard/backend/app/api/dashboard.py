"""Dashboard API routes — aggregation endpoints for the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.services import dashboard

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/kpis")
async def get_kpis():
    """Aggregated KPIs for the executive dashboard.

    Pulls positions, exceptions, and reserves from Agent 1 & 5,
    returning a single payload with all top-level metrics.
    """
    return await dashboard.get_dashboard_kpis()


@router.get("/asset-breakdown")
async def get_asset_breakdown():
    """Fair value and reserve breakdown by asset class."""
    return await dashboard.get_asset_class_breakdown()


@router.get("/exception-trends")
async def get_exception_trends(days: int = Query(90, le=365)):
    """Exception counts over the last N days grouped by date."""
    return await dashboard.get_exception_trends(days)

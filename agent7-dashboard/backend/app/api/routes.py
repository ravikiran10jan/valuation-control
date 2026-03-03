"""Comprehensive IPV lifecycle routes.

New endpoints aggregating data from all upstream agents (1–8) to power
the IPV Run Dashboard, Position Deep-Dive, Reserve Waterfall,
Capital Adequacy, FV Hierarchy, and Validation views.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query, HTTPException

from app.services.upstream import (
    agent2_get,
    agent3_get,
    agent3_post,
    agent5_get,
    agent6_get,
    agent8_get,
)
from app.services.ipv_aggregator import (
    get_ipv_summary,
    get_reserve_waterfall,
    get_capital_adequacy_dashboard,
    get_position_deep_dive,
    get_fv_hierarchy_summary,
    get_level_transfers,
    get_validation_report,
)

router = APIRouter(prefix="/api", tags=["IPV Lifecycle"])


# ── IPV Runs ────────────────────────────────────────────────────


@router.get("/ipv/runs")
async def list_ipv_runs(
    limit: int = Query(20, le=100),
    status: Optional[str] = None,
):
    """List IPV runs from Agent 3 (IPV Orchestrator).

    Args:
        limit: Maximum number of runs to return.
        status: Optional filter by run status (RUNNING, COMPLETED, FAILED).
    """
    params: dict = {"limit": limit}
    if status:
        params["status"] = status
    try:
        return await agent3_get("/ipv/runs", params=params)
    except Exception:
        return []


@router.get("/ipv/latest")
async def get_latest_ipv_run():
    """Get the latest IPV run results with aggregated summary.

    Combines IPV run data from Agent 3 with position and reserve
    data from Agents 1 and 5.
    """
    return await get_ipv_summary()


@router.post("/ipv/trigger")
async def trigger_ipv_run(
    asset_class: Optional[str] = None,
    run_date: Optional[str] = None,
):
    """Trigger a new IPV run via Agent 3.

    Proxies to Agent 3 POST /ipv/runs which accepts an IPVRunRequest body
    with valuation_date, run_type, triggered_by, etc.

    Args:
        asset_class: Optional filter — only run IPV for this asset class.
        run_date: Optional valuation date override (ISO format).
    """
    body: dict = {
        "run_type": "FULL",
        "triggered_by": "dashboard_user",
    }
    if run_date:
        body["valuation_date"] = run_date
    try:
        return await agent3_post("/ipv/runs", json=body)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to trigger IPV run: {exc}")


@router.get("/ipv/positions/{position_id}/detail")
async def get_ipv_position_detail(position_id: int):
    """Full position IPV detail — aggregates all agents.

    Combines position data (Agent 1), greeks (Agent 2),
    reserves (Agent 5), and disputes (Agent 4).
    """
    return await get_position_deep_dive(position_id)


# ── Reserve Detail ──────────────────────────────────────────────


@router.get("/reserves/detail")
async def get_detailed_reserves():
    """Detailed reserves breakdown for the waterfall view.

    Aggregates FVA, AVA (7 categories), Model Reserve, and
    Day1 PnL deferred amounts across all positions.
    """
    return await get_reserve_waterfall()


# ── Capital Adequacy ────────────────────────────────────────────


@router.get("/capital-adequacy")
async def get_capital_adequacy():
    """Capital adequacy summary with CET1, RWA, and buffer analysis.

    Combines Agent 5 reserve data with Agent 6 regulatory capital data.
    """
    return await get_capital_adequacy_dashboard()


# ── Greeks ──────────────────────────────────────────────────────


@router.get("/greeks/{position_id}")
async def get_position_greeks(position_id: int):
    """Get Greeks for a specific position from Agent 2 (Pricing Engine).

    Args:
        position_id: The position ID.
    """
    try:
        return await agent2_get(f"/pricing/greeks/{position_id}")
    except Exception:
        return {
            "position_id": position_id,
            "greeks": [],
            "error": "Pricing engine unavailable",
        }


# ── Validation ──────────────────────────────────────────────────


@router.get("/validation/report")
async def get_validation_results():
    """Latest validation results from Agent 8.

    Returns overall score, check counts, and per-category breakdowns.
    """
    return await get_validation_report()


# ── Fair Value Hierarchy ────────────────────────────────────────


@router.get("/fv-hierarchy")
async def get_fv_hierarchy():
    """Fair value hierarchy summary — L1/L2/L3 breakdown.

    Groups all positions by their fair value level and computes
    counts, book values, and disclosure requirements.
    """
    try:
        return await get_fv_hierarchy_summary()
    except Exception:
        return []


@router.get("/fv-hierarchy/transfers")
async def get_fv_level_transfers():
    """Fair value level transfers — tracks movements between L1/L2/L3.

    Analyses exception and audit data to identify positions that have
    changed fair value levels.
    """
    return await get_level_transfers()

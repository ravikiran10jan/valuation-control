"""Dashboard aggregation service.

Combines data from Agent 1 (Data Layer) and Agent 5 (Reserves)
to produce dashboard-ready KPIs, trends, and breakdowns.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, timedelta

import structlog

from app.services.upstream import agent1_get, agent5_get

log = structlog.get_logger()


async def get_dashboard_kpis() -> dict:
    """Aggregate KPIs from upstream services for the executive dashboard.

    Returns:
        Dict with total_positions, total_fair_value, open_exceptions,
        red_exceptions, amber_exceptions, total_fva_reserve, total_ava,
        and a trends sub-dict.
    """
    # Fetch from agent1 and agent5 in parallel
    positions_task = agent1_get("/positions/", params={"limit": 10000})
    exceptions_task = agent1_get("/exceptions/summary")
    statistics_task = agent1_get("/exceptions/statistics")
    reserves_task = agent5_get("/reserves/summary")

    results = await asyncio.gather(
        positions_task,
        exceptions_task,
        statistics_task,
        reserves_task,
        return_exceptions=True,
    )

    positions = results[0] if not isinstance(results[0], Exception) else []
    summary = results[1] if not isinstance(results[1], Exception) else {}
    statistics = results[2] if not isinstance(results[2], Exception) else {}
    reserves = results[3] if not isinstance(results[3], Exception) else {}

    total_fv = sum(float(p.get("vc_fair_value") or 0) for p in positions)

    return {
        "total_positions": len(positions),
        "total_fair_value": total_fv,
        "open_exceptions": summary.get("total_exceptions", 0),
        "red_exceptions": summary.get("red_count", 0),
        "amber_exceptions": summary.get("amber_count", 0),
        "total_fva_reserve": reserves.get("total_fva", 0),
        "total_ava": reserves.get("total_ava", 0),
        "avg_days_to_resolve": summary.get("avg_days_to_resolve", 0),
        "trends": {
            "positions_trend": 0,
            "fair_value_trend": 0,
            "exceptions_trend": statistics.get("created_last_7_days", 0),
            "red_trend": 0,
            "fva_trend": 0,
            "ava_trend": 0,
        },
    }


async def get_asset_class_breakdown() -> list[dict]:
    """Aggregate positions by asset class.

    Returns:
        List of dicts with asset_class, fair_value, fva_reserve, position_count.
    """
    positions = await agent1_get("/positions/", params={"limit": 10000})

    breakdown: dict[str, dict] = defaultdict(
        lambda: {"fair_value": 0.0, "position_count": 0, "fva_reserve": 0.0}
    )

    for pos in positions:
        ac = pos.get("asset_class") or "Unknown"
        breakdown[ac]["fair_value"] += float(pos.get("vc_fair_value") or 0)
        breakdown[ac]["position_count"] += 1
        breakdown[ac]["fva_reserve"] += float(pos.get("fva_usd") or 0)

    return [
        {
            "asset_class": ac,
            "fair_value": data["fair_value"],
            "fva_reserve": data["fva_reserve"],
            "position_count": data["position_count"],
        }
        for ac, data in sorted(breakdown.items(), key=lambda x: -x[1]["fair_value"])
    ]


async def get_exception_trends(days: int = 90) -> list[dict]:
    """Get exception trends over the last N days.

    Fetches exception statistics grouped by creation date.

    Args:
        days: Number of past days to return trend data for.

    Returns:
        List of dicts with date, total, red, amber counts.
    """
    start = date.today() - timedelta(days=days)

    try:
        all_exceptions = await agent1_get("/exceptions/", params={
            "limit": 10000,
            "start_date": start.isoformat(),
        })
    except Exception:
        log.warning("exception_trends_fetch_failed")
        all_exceptions = []

    # Group by created_date and severity
    by_date: dict[str, dict] = {}
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        by_date[d] = {"date": d, "total": 0, "red": 0, "amber": 0}

    for exc in all_exceptions:
        d = exc.get("created_date", "")
        if d in by_date:
            by_date[d]["total"] += 1
            severity = exc.get("severity", "")
            if severity == "RED":
                by_date[d]["red"] += 1
            elif severity == "AMBER":
                by_date[d]["amber"] += 1

    return sorted(by_date.values(), key=lambda x: x["date"])


async def get_position_detail(position_id: int) -> dict:
    """Get enriched position detail with reserves data.

    Combines position info from Agent 1 with reserves from Agent 5.

    Args:
        position_id: The position ID.

    Returns:
        Merged position + reserves dict.
    """
    position_task = agent1_get(f"/positions/{position_id}")
    reserves_task = agent5_get(f"/reserves/by-position/{position_id}")
    comparisons_task = agent1_get(
        f"/comparisons/history/{position_id}", params={"limit": 30}
    )

    results = await asyncio.gather(
        position_task, reserves_task, comparisons_task,
        return_exceptions=True,
    )

    position = results[0] if not isinstance(results[0], Exception) else {}
    reserves = results[1] if not isinstance(results[1], Exception) else []
    comparisons = results[2] if not isinstance(results[2], Exception) else []

    # Parse reserves into FVA / AVA / Model Reserve / Day1 PnL
    reserve_summary = {"fva": 0, "ava": 0, "model_reserve": 0, "day_1_pnl": 0}
    for r in reserves:
        rtype = r.get("reserve_type", "").lower()
        if rtype == "fva":
            reserve_summary["fva"] += float(r.get("amount") or 0)
        elif rtype == "ava":
            reserve_summary["ava"] += float(r.get("amount") or 0)
        elif rtype == "model_reserve":
            reserve_summary["model_reserve"] += float(r.get("amount") or 0)
        elif rtype == "day1_pnl":
            reserve_summary["day_1_pnl"] += float(r.get("amount") or 0)

    return {
        **position,
        "reserves": reserve_summary,
        "comparison_history": comparisons,
    }

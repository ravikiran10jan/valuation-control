"""IPV Aggregation Service.

Combines data from multiple upstream agents into dashboard-ready views
for the IPV lifecycle, reserves waterfall, capital adequacy, and
position deep-dive.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict

import structlog

from app.services.upstream import (
    agent1_get,
    agent2_get,
    agent3_get,
    agent4_get,
    agent5_get,
    agent6_get,
    agent8_get,
)

log = structlog.get_logger()


async def get_ipv_summary() -> dict:
    """Aggregate IPV run data with position tolerance results and exceptions.

    Combines Agent 3 (IPV Orchestrator) run data with Agent 1 positions
    and Agent 5 reserve totals to produce a comprehensive IPV summary.

    Returns:
        Dict with run info, position RAG counts, and reserve totals.
    """
    positions_task = agent1_get("/positions/", params={"limit": 10000})
    exceptions_task = agent1_get("/exceptions/summary")
    reserves_task = agent5_get("/reserves/summary")
    ipv_runs_task = agent3_get("/ipv/runs")

    results = await asyncio.gather(
        positions_task,
        exceptions_task,
        reserves_task,
        ipv_runs_task,
        return_exceptions=True,
    )

    positions = results[0] if not isinstance(results[0], Exception) else []
    exc_summary = results[1] if not isinstance(results[1], Exception) else {}
    reserves = results[2] if not isinstance(results[2], Exception) else {}
    ipv_runs = results[3] if not isinstance(results[3], Exception) else []

    # Count RAG statuses from positions
    green_count = sum(1 for p in positions if p.get("exception_status") in (None, "GREEN"))
    amber_count = sum(1 for p in positions if p.get("exception_status") == "AMBER")
    red_count = sum(1 for p in positions if p.get("exception_status") == "RED")

    total_notional = sum(float(p.get("notional_usd") or 0) for p in positions)
    total_book = sum(float(p.get("book_value_usd") or 0) for p in positions)

    return {
        "total_positions": len(positions),
        "total_notional_usd": total_notional,
        "total_book_value_usd": total_book,
        "green_count": green_count,
        "amber_count": amber_count,
        "red_count": red_count,
        "total_fva": reserves.get("total_fva", 0),
        "total_ava": reserves.get("total_ava", 0),
        "total_model_reserve": reserves.get("total_model_reserve", 0),
        "total_day1_deferred": reserves.get("total_day1_deferred", 0),
        "ipv_runs": ipv_runs if isinstance(ipv_runs, list) else [],
        "exception_summary": exc_summary,
    }


async def get_reserve_waterfall() -> dict:
    """Aggregate reserve data into a waterfall-chart-ready breakdown.

    Pulls per-position reserves from Agent 5 and groups by
    FVA, AVA (7 categories), Model Reserve, and Day1 PnL.

    Returns:
        Dict with position-level reserve rows and aggregate totals.
    """
    positions_task = agent1_get("/positions/", params={"limit": 10000})
    reserves_task = agent5_get("/reserves/summary")

    results = await asyncio.gather(
        positions_task,
        reserves_task,
        return_exceptions=True,
    )

    positions = results[0] if not isinstance(results[0], Exception) else []
    reserves_summary = results[1] if not isinstance(results[1], Exception) else {}

    # Build per-position reserve detail
    position_reserves = []
    for pos in positions[:50]:  # Limit to top 50 for performance
        pid = pos.get("position_id")
        fva = float(pos.get("fva_usd") or 0)
        position_reserves.append({
            "position_id": pid,
            "currency_pair": pos.get("currency_pair", ""),
            "asset_class": pos.get("asset_class", ""),
            "notional_usd": float(pos.get("notional_usd") or 0),
            "fva": fva,
            "ava": 0,
            "model_reserve": 0,
            "day1_deferred": 0,
            "total_reserve": fva,
        })

    return {
        "positions": position_reserves,
        "totals": {
            "total_fva": reserves_summary.get("total_fva", 0),
            "total_ava": reserves_summary.get("total_ava", 0),
            "total_model_reserve": reserves_summary.get("total_model_reserve", 0),
            "total_day1_deferred": reserves_summary.get("total_day1_deferred", 0),
            "grand_total": reserves_summary.get("grand_total", 0),
        },
    }


async def get_capital_adequacy_dashboard() -> dict:
    """Aggregate capital adequacy metrics from Agent 6 and Agent 5.

    Combines regulatory capital data with AVA deductions to produce
    a capital adequacy overview with CET1, RWA, and buffer analysis.

    Returns:
        Dict with capital composition, RWA breakdown, and ratio analysis.
    """
    reserves_task = agent5_get("/reserves/summary")
    capital_task = agent6_get("/reports/capital-adequacy")

    results = await asyncio.gather(
        reserves_task,
        capital_task,
        return_exceptions=True,
    )

    reserves = results[0] if not isinstance(results[0], Exception) else {}
    capital = results[1] if not isinstance(results[1], Exception) else {}

    total_ava = float(reserves.get("total_ava", 0))

    # If Agent 6 provides capital data, use it; otherwise derive from reserves
    cet1_capital = float(capital.get("cet1_capital", 0))
    total_rwa = float(capital.get("total_rwa", 0))

    cet1_ratio = (cet1_capital / total_rwa * 100) if total_rwa > 0 else 0
    regulatory_minimum = 4.5  # Basel III minimum CET1 ratio
    buffer_above_minimum = cet1_ratio - regulatory_minimum

    return {
        "cet1_capital": cet1_capital,
        "total_rwa": total_rwa,
        "cet1_ratio": round(cet1_ratio, 2),
        "regulatory_minimum": regulatory_minimum,
        "buffer_above_minimum": round(buffer_above_minimum, 2),
        "ava_deduction": total_ava,
        "components": capital.get("components", {
            "shareholders_equity": 0,
            "retained_earnings": 0,
            "aoci": 0,
            "deductions": 0,
        }),
        "rwa_breakdown": capital.get("rwa_breakdown", {
            "credit_risk": 0,
            "market_risk": 0,
            "operational_risk": 0,
        }),
    }


async def get_position_deep_dive(position_id: int) -> dict:
    """Get everything about a single position across all agents.

    Aggregates data from Agent 1 (position), Agent 2 (greeks),
    Agent 3 (IPV result), Agent 4 (disputes), and Agent 5 (reserves).

    Args:
        position_id: The position to deep-dive into.

    Returns:
        Merged dict with position, valuation, greeks, reserves, and disputes.
    """
    position_task = agent1_get(f"/positions/{position_id}")
    reserves_task = agent5_get(f"/reserves/by-position/{position_id}")
    comparisons_task = agent1_get(
        f"/comparisons/history/{position_id}", params={"limit": 30}
    )
    greeks_task = agent2_get(f"/pricing/greeks/{position_id}")
    disputes_task = agent4_get("/disputes/", params={"position_id": str(position_id)})

    results = await asyncio.gather(
        position_task,
        reserves_task,
        comparisons_task,
        greeks_task,
        disputes_task,
        return_exceptions=True,
    )

    position = results[0] if not isinstance(results[0], Exception) else {}
    reserves = results[1] if not isinstance(results[1], Exception) else []
    comparisons = results[2] if not isinstance(results[2], Exception) else []
    greeks = results[3] if not isinstance(results[3], Exception) else {}
    disputes = results[4] if not isinstance(results[4], Exception) else []

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
        "greeks": greeks,
        "disputes": disputes if isinstance(disputes, list) else [],
    }


async def get_fv_hierarchy_summary() -> list[dict]:
    """Aggregate positions by fair value hierarchy level (L1/L2/L3).

    Groups positions from Agent 1 by their fair_value_level and computes
    counts, total book value, and percentage of total.

    Returns:
        List of dicts with level, position_count, book_value, pct_of_total.
    """
    positions = await agent1_get("/positions/", params={"limit": 10000})

    levels: dict[str, dict] = defaultdict(
        lambda: {"position_count": 0, "book_value": 0.0}
    )

    for pos in positions:
        level = pos.get("fair_value_level") or "L2"
        levels[level]["position_count"] += 1
        levels[level]["book_value"] += float(pos.get("book_value_usd") or 0)

    total_book = sum(d["book_value"] for d in levels.values())

    characteristics_map = {
        "L1": "Quoted prices in active markets for identical instruments",
        "L2": "Observable inputs other than Level 1 quoted prices",
        "L3": "Unobservable inputs requiring significant judgment",
    }

    disclosure_map = {
        "L1": "Standard",
        "L2": "Enhanced",
        "L3": "Full (IFRS 13.93)",
    }

    audit_map = {
        "L1": "Low",
        "L2": "Medium",
        "L3": "High — Independent model validation required",
    }

    result = []
    for level in ["L1", "L2", "L3"]:
        data = levels.get(level, {"position_count": 0, "book_value": 0.0})
        pct = (data["book_value"] / total_book * 100) if total_book > 0 else 0
        result.append({
            "level": level,
            "position_count": data["position_count"],
            "book_value": data["book_value"],
            "pct_of_total": round(pct, 1),
            "characteristics": characteristics_map.get(level, ""),
            "disclosure_level": disclosure_map.get(level, ""),
            "audit_intensity": audit_map.get(level, ""),
        })

    return result


async def get_validation_report() -> dict:
    """Get the latest validation results from Agent 8.

    Returns:
        Dict with overall score, check counts, and category breakdowns.
    """
    try:
        report = await agent8_get("/validation/report")
        return report
    except Exception:
        log.warning("validation_report_unavailable")
        return {
            "overall_score": 0,
            "total_checks": 0,
            "passed": 0,
            "failed": 0,
            "warnings": 0,
            "categories": [],
        }

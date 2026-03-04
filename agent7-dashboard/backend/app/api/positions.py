"""Proxy routes for Agent 1 position endpoints and enriched detail."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Optional

import structlog
from fastapi import APIRouter, Query

from app.services.upstream import agent1_get
from app.services.dashboard import get_position_detail

log = structlog.get_logger()

router = APIRouter(prefix="/api/positions", tags=["Positions"])

# ── Synthetic fallback data ─────────────────────────────────────

_PRODUCTS = [
    ("FX Forward", "FX", ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CHF", "USD/CAD"]),
    ("FX Option", "FX", ["EUR/USD", "GBP/USD", "USD/JPY"]),
    ("IRS", "Rates", ["USD/USD", "EUR/EUR", "GBP/GBP"]),
    ("Cross-Currency Swap", "Rates", ["EUR/USD", "GBP/USD", "USD/JPY"]),
    ("Swaption", "Rates", ["USD/USD", "EUR/EUR"]),
    ("Equity Option", "Equity", ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]),
    ("Equity Swap", "Equity", ["SPX", "NDX", "STOXX50E"]),
    ("CDS", "Credit", ["USD/USD", "EUR/EUR"]),
    ("CDX Index", "Credit", ["CDX.NA.IG", "CDX.NA.HY", "ITRAXX.EUR"]),
    ("Commodity Swap", "Commodities", ["XAU/USD", "WTI/USD", "BRENT/USD"]),
    ("Commodity Option", "Commodities", ["XAU/USD", "WTI/USD"]),
]

_COUNTERPARTIES = [
    "Deutsche Bank", "JP Morgan", "Goldman Sachs", "Barclays",
    "Morgan Stanley", "Citibank", "HSBC", "BNP Paribas",
    "UBS", "Credit Suisse", "Nomura", "Societe Generale",
]

_DESKS = ["FX Spot", "FX Options", "Rates Trading", "Equity Derivatives",
          "Credit Trading", "Commodities"]


def _generate_synthetic_positions(
    count: int = 48,
    asset_class: Optional[str] = None,
    exception_status: Optional[str] = None,
) -> list[dict]:
    """Generate realistic synthetic position data."""
    rng = random.Random(42)  # fixed seed for stable output
    today = datetime.utcnow().strftime("%Y-%m-%d")
    positions = []

    for i in range(1, count + 1):
        product_type, ac, pairs = rng.choice(_PRODUCTS)
        ccy_pair = rng.choice(pairs)

        notional = rng.choice([1_000_000, 5_000_000, 10_000_000, 25_000_000,
                               50_000_000, 100_000_000])
        desk_mark = round(rng.uniform(50_000, 5_000_000), 2)
        diff_pct = round(rng.gauss(0, 1.5), 4)
        vc_fair_value = round(desk_mark * (1 + diff_pct / 100), 2)
        difference = round(vc_fair_value - desk_mark, 2)

        abs_diff = abs(diff_pct)
        if abs_diff > 5:
            status = "RED"
        elif abs_diff > 2:
            status = "AMBER"
        else:
            status = "GREEN"

        fv_level = rng.choices(["L1", "L2", "L3"], weights=[30, 55, 15])[0]
        trade_date = (datetime.utcnow() - timedelta(days=rng.randint(30, 365))).strftime("%Y-%m-%d")
        maturity_date = (datetime.utcnow() + timedelta(days=rng.randint(90, 1825))).strftime("%Y-%m-%d")

        positions.append({
            "position_id": i,
            "trade_id": f"{ac[:2].upper()}-{20250100 + i:08d}-{rng.randint(1,9):03d}",
            "product_type": product_type,
            "asset_class": ac,
            "currency_pair": ccy_pair,
            "notional": notional,
            "notional_usd": notional,
            "currency": "USD",
            "trade_date": trade_date,
            "maturity_date": maturity_date,
            "settlement_date": None,
            "counterparty": rng.choice(_COUNTERPARTIES),
            "desk_mark": desk_mark,
            "vc_fair_value": vc_fair_value,
            "book_value_usd": desk_mark,
            "difference": difference,
            "difference_pct": round(diff_pct, 2),
            "exception_status": status,
            "fair_value_level": fv_level,
            "pricing_source": rng.choice(["Bloomberg", "MarkIT", "Reuters", "Internal Model"]),
            "fva_usd": round(rng.uniform(500, 50_000), 2),
            "valuation_date": today,
            "created_at": f"{trade_date}T10:00:00Z",
            "updated_at": f"{today}T06:13:00Z",
        })

    # Apply filters
    if asset_class:
        positions = [p for p in positions if p["asset_class"] == asset_class]
    if exception_status:
        positions = [p for p in positions if p["exception_status"] == exception_status]

    return positions


@router.get("/")
async def list_positions(
    asset_class: Optional[str] = None,
    exception_status: Optional[str] = None,
    limit: int = Query(100, le=10000),
    offset: int = 0,
):
    """List positions (proxied from Agent 1, synthetic fallback)."""
    params = {"limit": limit, "offset": offset}
    if asset_class:
        params["asset_class"] = asset_class
    if exception_status:
        params["exception_status"] = exception_status
    try:
        result = await agent1_get("/positions/", params=params)
        if result:  # Agent 1 returned real data
            return result
    except Exception:
        pass

    log.info("agent1_unavailable_positions_fallback")
    return _generate_synthetic_positions(
        asset_class=asset_class,
        exception_status=exception_status,
    )


@router.get("/{position_id}")
async def get_position(position_id: int):
    """Get enriched position detail with reserves and comparison history."""
    return await get_position_detail(position_id)

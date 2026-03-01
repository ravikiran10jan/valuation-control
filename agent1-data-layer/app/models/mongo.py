"""MongoDB helper layer for time-series market data."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from app.core.database import get_mongo


MARKET_DATA_HISTORY = "market_data_history"
VOL_SURFACE_HISTORY = "vol_surface_history"


async def ensure_indexes() -> None:
    """Create MongoDB indexes (idempotent)."""
    db = get_mongo()
    await db[MARKET_DATA_HISTORY].create_index(
        [("field", 1), ("date", -1)], background=True
    )
    await db[VOL_SURFACE_HISTORY].create_index(
        [("currency_pair", 1), ("date", -1), ("tenor", 1)], background=True
    )


# ── Inserts ───────────────────────────────────────────────────────
async def insert_market_data_point(
    field: str,
    value: float,
    as_of: date,
    source: str,
) -> str:
    db = get_mongo()
    result = await db[MARKET_DATA_HISTORY].insert_one(
        {
            "field": field,
            "date": datetime.combine(as_of, datetime.min.time()),
            "value": value,
            "source": source,
            "timestamp": datetime.utcnow(),
        }
    )
    return str(result.inserted_id)


async def insert_vol_surface_point(
    currency_pair: str,
    tenor: str,
    delta: str,
    volatility: float,
    as_of: date,
    source: str,
) -> str:
    db = get_mongo()
    result = await db[VOL_SURFACE_HISTORY].insert_one(
        {
            "currency_pair": currency_pair,
            "date": datetime.combine(as_of, datetime.min.time()),
            "tenor": tenor,
            "delta": delta,
            "volatility": volatility,
            "source": source,
            "timestamp": datetime.utcnow(),
        }
    )
    return str(result.inserted_id)


# ── Queries ───────────────────────────────────────────────────────
async def get_market_data_series(
    field: str,
    start_date: date,
    end_date: date,
    source: Optional[str] = None,
) -> list[dict]:
    db = get_mongo()
    query: dict = {
        "field": field,
        "date": {
            "$gte": datetime.combine(start_date, datetime.min.time()),
            "$lte": datetime.combine(end_date, datetime.min.time()),
        },
    }
    if source:
        query["source"] = source

    cursor = db[MARKET_DATA_HISTORY].find(query).sort("date", -1)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


async def get_latest_market_data(field: str) -> dict | None:
    db = get_mongo()
    doc = await db[MARKET_DATA_HISTORY].find_one(
        {"field": field}, sort=[("date", -1)]
    )
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def get_vol_surface(
    currency_pair: str,
    tenor: str,
    as_of: date,
    source: Optional[str] = None,
) -> list[dict]:
    db = get_mongo()
    query: dict = {
        "currency_pair": currency_pair,
        "tenor": tenor,
        "date": datetime.combine(as_of, datetime.min.time()),
    }
    if source:
        query["source"] = source

    cursor = db[VOL_SURFACE_HISTORY].find(query)
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


async def get_vol_surface_history(
    currency_pair: str,
    tenor: str,
    delta: str,
    start_date: date,
    end_date: date,
) -> list[dict]:
    db = get_mongo()
    cursor = (
        db[VOL_SURFACE_HISTORY]
        .find(
            {
                "currency_pair": currency_pair,
                "tenor": tenor,
                "delta": delta,
                "date": {
                    "$gte": datetime.combine(start_date, datetime.min.time()),
                    "$lte": datetime.combine(end_date, datetime.min.time()),
                },
            }
        )
        .sort("date", -1)
    )
    results = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results

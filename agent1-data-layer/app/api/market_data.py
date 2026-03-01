"""Market data API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.services.market_data import MarketDataService

router = APIRouter(prefix="/market-data", tags=["Market Data"])
_svc = MarketDataService()


@router.get("/spot/{currency_pair}")
async def get_spot(currency_pair: str, date: Optional[str] = None):
    """Return spot rate for a currency pair.

    Example: GET /market-data/spot/EUR/USD
    """
    # currency_pair comes as "EUR/USD" via path
    as_of = _parse_date(date)
    try:
        return await _svc.get_spot(currency_pair, as_of)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/vol-surface/{currency_pair}")
async def get_vol_surface(currency_pair: str, tenor: str = "1Y", date: Optional[str] = None):
    """Return vol surface deltas for a currency pair / tenor.

    Example: GET /market-data/vol-surface/EUR/USD?tenor=1Y
    """
    as_of = _parse_date(date)
    try:
        return await _svc.get_vol_surface(currency_pair, tenor, as_of)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/yield-curve/{curve_name}")
async def get_yield_curve(curve_name: str, date: Optional[str] = None):
    """Return yield curve tenors.

    Example: GET /market-data/yield-curve/USD_SOFR
    """
    as_of = _parse_date(date)
    try:
        return await _svc.get_yield_curve(curve_name, as_of)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/cds-spread/{reference_entity}")
async def get_cds_spread(
    reference_entity: str, tenor: str = "5Y", date: Optional[str] = None
):
    """Return CDS spread in bps.

    Example: GET /market-data/cds-spread/ITRAXX?tenor=5Y
    """
    as_of = _parse_date(date)
    try:
        return await _svc.get_cds_spread(reference_entity, tenor, as_of)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/forward-points/{currency_pair}")
async def get_forward_points(
    currency_pair: str, tenor: str = "1M", date: Optional[str] = None
):
    """Return FX forward points.

    Example: GET /market-data/forward-points/EUR/USD?tenor=1M
    """
    as_of = _parse_date(date)
    try:
        return await _svc.get_forward_points(currency_pair, tenor, as_of)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/health")
async def health():
    return await _svc.health()


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)

"""Internal trading system connectors (Murex, Calypso, Summit).

Each adapter normalises positions into the common PositionCreate schema so
they can be stored uniformly in PostgreSQL.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import structlog

from app.models.schemas import PositionCreate

log = structlog.get_logger()


class MurexConnector:
    """Connects to the Murex MxML Gateway REST API."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def fetch_positions(self, valuation_date: Optional[date] = None) -> list[PositionCreate]:
        import httpx

        params = {}
        if valuation_date:
            params["valuationDate"] = valuation_date.isoformat()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/api/v1/positions",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            rows = resp.json().get("positions", [])

        positions = []
        for row in rows:
            positions.append(
                PositionCreate(
                    trade_id=row["tradeId"],
                    product_type=row.get("productType"),
                    asset_class=row.get("assetClass"),
                    notional=Decimal(str(row.get("notional", 0))),
                    currency=row.get("currency"),
                    trade_date=_parse_date(row.get("tradeDate")),
                    maturity_date=_parse_date(row.get("maturityDate")),
                    counterparty=row.get("counterparty"),
                    desk_mark=Decimal(str(row.get("deskMark", 0))),
                    valuation_date=_parse_date(row.get("valuationDate")),
                )
            )
        log.info("murex_positions_fetched", count=len(positions))
        return positions


class CalypsoConnector:
    """Connects to the Calypso REST API."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def fetch_positions(self, valuation_date: Optional[date] = None) -> list[PositionCreate]:
        import httpx

        params = {}
        if valuation_date:
            params["valDate"] = valuation_date.isoformat()

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/calypso/api/v2/trades",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            rows = resp.json().get("trades", [])

        positions = []
        for row in rows:
            positions.append(
                PositionCreate(
                    trade_id=row["externalReference"],
                    product_type=_map_calypso_product(row.get("type")),
                    asset_class=row.get("family"),
                    notional=Decimal(str(row.get("principal", 0))),
                    currency=row.get("settlementCurrency"),
                    trade_date=_parse_date(row.get("tradeDate")),
                    maturity_date=_parse_date(row.get("endDate")),
                    counterparty=row.get("legalEntity"),
                    desk_mark=Decimal(str(row.get("npv", 0))),
                    valuation_date=_parse_date(row.get("valDate")),
                )
            )
        log.info("calypso_positions_fetched", count=len(positions))
        return positions


class SummitConnector:
    """Reads Summit CSV file drops (e.g., from an S3 bucket)."""

    async def parse_csv(self, csv_content: str) -> list[PositionCreate]:
        reader = csv.DictReader(io.StringIO(csv_content))
        positions = []
        for row in reader:
            positions.append(
                PositionCreate(
                    trade_id=row["TradeID"],
                    product_type=row.get("ProductType"),
                    asset_class=row.get("AssetClass"),
                    notional=Decimal(row.get("Notional", "0")),
                    currency=row.get("Currency"),
                    trade_date=_parse_date(row.get("TradeDate")),
                    maturity_date=_parse_date(row.get("MaturityDate")),
                    counterparty=row.get("Counterparty"),
                    desk_mark=Decimal(row.get("DeskMark", "0")),
                    valuation_date=_parse_date(row.get("ValuationDate")),
                )
            )
        log.info("summit_positions_parsed", count=len(positions))
        return positions


# ── helpers ───────────────────────────────────────────────────────
def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _map_calypso_product(calypso_type: Optional[str]) -> Optional[str]:
    """Map Calypso-specific product names to our normalised taxonomy."""
    mapping = {
        "FXBarrier": "FX_Barrier",
        "FXOption": "FX_Option",
        "IRSwap": "IRS",
        "CreditDefaultSwap": "CDS",
        "EquityOption": "Equity_Option",
    }
    return mapping.get(calypso_type or "", calypso_type)

"""Bloomberg Terminal API connector.

Requires the Bloomberg Desktop/Server API (blpapi).
When `BLOOMBERG_ENABLED=false` (the default in dev), this connector is not
instantiated -- the mock connector is used instead.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import structlog

from app.connectors.base import MarketDataConnector

log = structlog.get_logger()

# Bloomberg field mappings by asset class
FIELD_MAP = {
    "FX": {
        "spot": "PX_LAST",
        "vol_25p": "25D_PUT_IMP_VOL",
        "vol_atm": "ATM_IMP_VOL",
        "vol_25c": "25D_CALL_IMP_VOL",
        "forward": "FWD_POINTS",
    },
    "Rates": {
        "yield_curve": "YLD_YTM_MID",
        "swap_rate": "SW_RATE_MID",
        "swaption_vol": "ATM_NVOL_MID",
    },
    "Credit": {
        "cds_spread": "CDS_MID_SPREAD",
        "recovery_rate": "RECOVERY_RATE",
    },
    "Equity": {
        "spot": "PX_LAST",
        "div_yield": "EQY_DVD_YLD_IND",
        "vol_surface": "30D_IMPVOL_100.0%MNY_DF",
    },
}


class BloombergConnector(MarketDataConnector):
    """Wraps the Bloomberg blpapi for market data retrieval.

    This implementation uses httpx to talk to a local Bloomberg B-PIPE or
    Desktop API proxy service (e.g., blpapi-http).  Direct blpapi C++ bindings
    can replace httpx calls in production.
    """

    def __init__(self, host: str, port: int) -> None:
        self._base_url = f"http://{host}:{port}"
        self._source = "Bloomberg"

    async def get_spot(self, currency_pair: str, as_of: Optional[date] = None) -> dict:
        import httpx

        ticker = f"{currency_pair.replace('/', '')} Curncy"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/refdata",
                params={"securities": ticker, "fields": "PX_LAST"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        value = float(data["data"][0]["PX_LAST"])
        return {
            "value": value,
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_vol_surface(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        base_ticker = currency_pair.replace("/", "")
        fields = ["25D_PUT_IMP_VOL", "ATM_IMP_VOL", "25D_CALL_IMP_VOL"]
        ticker = f"{base_ticker} {tenor} OVML Curncy"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/refdata",
                params={"securities": ticker, "fields": ",".join(fields)},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        row = data["data"][0]
        return {
            "25P": float(row.get("25D_PUT_IMP_VOL", 0)),
            "ATM": float(row.get("ATM_IMP_VOL", 0)),
            "25C": float(row.get("25D_CALL_IMP_VOL", 0)),
            "source": f"{self._source}_OVML",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_yield_curve(
        self, curve_name: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/refdata",
                params={
                    "securities": f"{curve_name} Index",
                    "fields": "YLD_YTM_MID",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        tenors = {}
        for point in data.get("data", []):
            tenors[point.get("tenor", "unknown")] = float(
                point.get("YLD_YTM_MID", 0)
            )
        return {
            "tenors": tenors,
            "source": f"{self._source}_YCRV",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_cds_spread(
        self, reference_entity: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        ticker = f"{reference_entity} {tenor} CDSW Corp"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/refdata",
                params={
                    "securities": ticker,
                    "fields": "CDS_MID_SPREAD,RECOVERY_RATE",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        row = data["data"][0]
        return {
            "spread_bps": float(row.get("CDS_MID_SPREAD", 0)),
            "recovery_rate": float(row.get("RECOVERY_RATE", 0.4)),
            "source": f"{self._source}_CDSW",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_forward_points(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        ticker = f"{currency_pair.replace('/', '')} {tenor} FXFA Curncy"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/refdata",
                params={"securities": ticker, "fields": "FWD_POINTS"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "points": float(data["data"][0].get("FWD_POINTS", 0)),
            "source": f"{self._source}_FXFA",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self._base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            log.warning("bloomberg_health_check_failed")
            return False

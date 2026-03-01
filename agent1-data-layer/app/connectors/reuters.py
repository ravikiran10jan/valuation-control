"""Refinitiv Eikon / Workspace API connector.

Used as a backup/cross-validation source alongside Bloomberg.
When `REUTERS_ENABLED=false` (the default in dev), this connector is not
instantiated -- the mock connector is used instead.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import structlog

from app.connectors.base import MarketDataConnector

log = structlog.get_logger()


class ReutersConnector(MarketDataConnector):
    """Talks to the Refinitiv Data Platform REST API."""

    def __init__(self, app_key: str) -> None:
        self._app_key = app_key
        self._base_url = "https://api.refinitiv.com/data"
        self._source = "Reuters"

    async def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._app_key}",
            "Content-Type": "application/json",
        }

    async def get_spot(self, currency_pair: str, as_of: Optional[date] = None) -> dict:
        import httpx

        ric = f"{currency_pair.replace('/', '')}=R"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/pricing/snapshots/v1",
                params={"universe": ric, "fields": "BID,ASK,MID"},
                headers=await self._get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        row = data.get("data", [{}])[0]
        mid = (float(row.get("BID", 0)) + float(row.get("ASK", 0))) / 2
        return {
            "value": mid,
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_vol_surface(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        ric = f"{currency_pair.replace('/', '')}={tenor}V"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/pricing/snapshots/v1",
                params={
                    "universe": ric,
                    "fields": "25D_P_IMP_VOL,ATM_IMP_VOL,25D_C_IMP_VOL",
                },
                headers=await self._get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        row = data.get("data", [{}])[0]
        return {
            "25P": float(row.get("25D_P_IMP_VOL", 0)),
            "ATM": float(row.get("ATM_IMP_VOL", 0)),
            "25C": float(row.get("25D_C_IMP_VOL", 0)),
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_yield_curve(
        self, curve_name: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/pricing/snapshots/v1",
                params={"universe": curve_name, "fields": "YLD_MID"},
                headers=await self._get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        tenors = {}
        for point in data.get("data", []):
            tenors[point.get("tenor", "unknown")] = float(
                point.get("YLD_MID", 0)
            )
        return {
            "tenors": tenors,
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_cds_spread(
        self, reference_entity: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        ric = f"{reference_entity}{tenor}CDS=R"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/pricing/snapshots/v1",
                params={"universe": ric, "fields": "CDS_MID,RECOVERY_RATE"},
                headers=await self._get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        row = data.get("data", [{}])[0]
        return {
            "spread_bps": float(row.get("CDS_MID", 0)),
            "recovery_rate": float(row.get("RECOVERY_RATE", 0.4)),
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_forward_points(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        import httpx

        ric = f"{currency_pair.replace('/', '')}FWD{tenor}=R"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url}/pricing/snapshots/v1",
                params={"universe": ric, "fields": "FWD_POINTS"},
                headers=await self._get_headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

        return {
            "points": float(data.get("data", [{}])[0].get("FWD_POINTS", 0)),
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def health_check(self) -> bool:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.refinitiv.com/ping",
                    headers=await self._get_headers(),
                    timeout=5,
                )
            return resp.status_code == 200
        except Exception:
            log.warning("reuters_health_check_failed")
            return False

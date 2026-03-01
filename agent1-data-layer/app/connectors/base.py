"""Abstract base class for all market data connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional


class MarketDataConnector(ABC):
    """Common interface implemented by Bloomberg, Reuters, and mock connectors."""

    @abstractmethod
    async def get_spot(self, currency_pair: str, as_of: Optional[date] = None) -> dict:
        """Return spot rate for a currency pair.

        Returns dict: {"value": float, "source": str, "timestamp": str}
        """

    @abstractmethod
    async def get_vol_surface(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        """Return vol surface deltas for a currency pair / tenor.

        Returns dict: {"25P": float, "ATM": float, "25C": float, "source": str, ...}
        """

    @abstractmethod
    async def get_yield_curve(
        self, curve_name: str, as_of: Optional[date] = None
    ) -> dict:
        """Return yield curve tenors.

        Returns dict: {"tenors": {"1M": float, "3M": float, ...}, "source": str, ...}
        """

    @abstractmethod
    async def get_cds_spread(
        self, reference_entity: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        """Return CDS spread in basis points.

        Returns dict: {"spread_bps": float, "recovery_rate": float, "source": str, ...}
        """

    @abstractmethod
    async def get_forward_points(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        """Return FX forward points.

        Returns dict: {"points": float, "source": str, ...}
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the data source is reachable."""

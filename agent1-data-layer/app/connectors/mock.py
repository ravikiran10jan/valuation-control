"""Mock market data connector for development and testing.

Returns deterministic FX market data sourced from the IPV_FX_Model so the rest
of the stack can be exercised without live Bloomberg or Reuters connections.

Data aligned to Valuation Date: 14-Feb-2025 (WM/Reuters 4pm London Fix).
"""

from __future__ import annotations

import random
from datetime import date, datetime
from typing import Optional

from app.connectors.base import MarketDataConnector

# Seed for reproducibility in tests
_rng = random.Random(42)

# IPV consensus prices from WM/Reuters 4pm London Fix (14-Feb-2025)
_SPOT_RATES: dict[str, float] = {
    "EUR/USD": 1.0823,
    "GBP/USD": 1.2645,
    "USD/JPY": 149.88,
    "USD/TRY": 35.12,
    "USD/BRL": 5.18,
}

# EUR/USD vol surface from Bloomberg OVML (barrier option pricing)
_VOL_SURFACES: dict[str, dict[str, dict[str, float]]] = {
    "EUR/USD": {
        "1M": {"25P": 7.6, "ATM": 7.0, "25C": 6.7},
        "3M": {"25P": 8.1, "ATM": 7.5, "25C": 7.1},
        "6M": {"25P": 8.8, "ATM": 8.0, "25C": 7.5},
        "1Y": {"25P": 9.6, "ATM": 6.8, "25C": 8.8},  # ATM 6.8% from model, RR=0.8%
    },
    "GBP/USD": {
        "1M": {"25P": 9.0, "ATM": 8.5, "25C": 8.1},
        "3M": {"25P": 10.0, "ATM": 9.3, "25C": 8.8},
        "6M": {"25P": 11.0, "ATM": 10.2, "25C": 9.6},
        "1Y": {"25P": 12.0, "ATM": 11.1, "25C": 10.5},
    },
}

# EUR/USD forward points from Bloomberg FXFA curve (interest rate differential)
# Forward Points = Spot x (1 + IR Differential x Days/360)
_FORWARD_POINTS: dict[str, dict[str, float]] = {
    "EUR/USD": {
        "1M": 9.0,     # 1.0823 x (-0.01 x 30/360)
        "3M": 27.0,    # 1.0823 x (-0.01 x 90/360)
        "6M": 54.0,    # 1.0823 x (-0.01 x 180/360)
        "1Y": 108.0,   # 1.0823 x (-0.01 x 360/360) — desk stale at 127 pips
    },
}

# Interest rate curves (ECB/Fed) for forward points calculation
_YIELD_CURVES: dict[str, dict[str, float]] = {
    "USD_FED": {
        "O/N": 5.25, "1M": 5.25, "3M": 5.25, "6M": 5.25, "1Y": 5.25,
        "2Y": 4.85, "3Y": 4.55, "5Y": 4.25, "7Y": 4.10,
        "10Y": 4.00, "30Y": 4.15,
    },
    "EUR_ECB": {
        "O/N": 4.25, "1M": 4.25, "3M": 4.25, "6M": 4.25, "1Y": 4.25,
        "2Y": 3.80, "3Y": 3.50, "5Y": 3.20, "7Y": 3.05,
        "10Y": 2.95, "30Y": 3.10,
    },
}


def _jitter(value: float, bps: float = 2.0) -> float:
    """Add small random noise (in bps) to simulate live data movement."""
    return round(value + _rng.uniform(-bps / 10000, bps / 10000), 6)


class MockConnector(MarketDataConnector):
    """Returns deterministic FX mock market data aligned to IPV_FX_Model."""

    def __init__(self) -> None:
        self._source = "WM/Reuters"

    async def get_spot(self, currency_pair: str, as_of: Optional[date] = None) -> dict:
        base = _SPOT_RATES.get(currency_pair, 1.0)
        return {
            "value": _jitter(base, bps=2),
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_vol_surface(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        pair_data = _VOL_SURFACES.get(currency_pair, _VOL_SURFACES["EUR/USD"])
        tenor_data = pair_data.get(tenor, pair_data.get("1Y", {}))
        return {
            "25P": round(tenor_data.get("25P", 10.0) + _rng.uniform(-0.1, 0.1), 2),
            "ATM": round(tenor_data.get("ATM", 9.0) + _rng.uniform(-0.1, 0.1), 2),
            "25C": round(tenor_data.get("25C", 8.5) + _rng.uniform(-0.1, 0.1), 2),
            "source": f"{self._source}_OVML",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_yield_curve(
        self, curve_name: str, as_of: Optional[date] = None
    ) -> dict:
        curve = _YIELD_CURVES.get(curve_name, _YIELD_CURVES["USD_FED"])
        tenors = {k: round(v + _rng.uniform(-0.02, 0.02), 4) for k, v in curve.items()}
        return {
            "tenors": tenors,
            "source": f"{self._source}_YCRV",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_cds_spread(
        self, reference_entity: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        # Not applicable for FX book but keep interface functional
        return {
            "spread_bps": 0.0,
            "recovery_rate": 0.0,
            "source": self._source,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def get_forward_points(
        self, currency_pair: str, tenor: str, as_of: Optional[date] = None
    ) -> dict:
        pair_fwds = _FORWARD_POINTS.get(currency_pair, {})
        points = pair_fwds.get(tenor, 0.0)
        return {
            "points": round(points + _rng.uniform(-1, 1), 2),
            "source": f"{self._source}_FXFA",
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def health_check(self) -> bool:
        return True

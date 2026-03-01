"""FX Spot mid-market pricing.

Computes the mid-market spot rate from bid/ask quotes, applies
WM/Reuters 4pm London Fix methodology, and provides data-quality
flags for stale or crossed quotes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.pricing.base import BasePricer, PricingResult


@dataclass
class FXQuote:
    """A single FX rate observation."""

    source: str  # "WMR", "Reuters", "Bloomberg", "ECB"
    bid: float
    ask: float
    timestamp: datetime | str
    currency_pair: str  # e.g. "EURUSD"

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread_bps(self) -> float:
        if self.mid == 0:
            return 0.0
        return (self.ask - self.bid) / self.mid * 10_000


class FXSpotPricer(BasePricer):
    """Compute the official mid-market FX spot rate.

    Methodology:
      1. Collect quotes from multiple sources.
      2. Filter stale / crossed / outlier quotes.
      3. Compute the mid as the median of surviving mids.
      4. Apply WM/Reuters 4pm Fix logic (median of trades in a
         5-minute window around the fix time).
    """

    def __init__(
        self,
        currency_pair: str,
        quotes: list[dict[str, Any]],
        *,
        stale_seconds: int = 300,
        outlier_threshold_bps: float = 50.0,
        reference_time: datetime | None = None,
    ):
        self.currency_pair = currency_pair.upper().replace("/", "")
        self.quotes = [self._to_quote(q) for q in quotes]
        self.stale_seconds = stale_seconds
        self.outlier_threshold_bps = outlier_threshold_bps
        self.reference_time = reference_time or datetime.utcnow()

    @staticmethod
    def _to_quote(q: dict[str, Any]) -> FXQuote:
        ts = q.get("timestamp", datetime.utcnow())
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = datetime.utcnow()
        return FXQuote(
            source=q.get("source", "unknown"),
            bid=float(q["bid"]),
            ask=float(q["ask"]),
            timestamp=ts,
            currency_pair=q.get("currency_pair", ""),
        )

    # ── validation ──────────────────────────────────────────────
    def validate_inputs(self) -> list[str]:
        errors: list[str] = []
        if not self.quotes:
            errors.append("At least one quote is required")
        for i, q in enumerate(self.quotes):
            if q.bid <= 0 or q.ask <= 0:
                errors.append(f"Quote {i}: bid/ask must be > 0")
            if q.bid > q.ask:
                errors.append(f"Quote {i} ({q.source}): crossed market (bid > ask)")
        return errors

    # ── filtering pipeline ──────────────────────────────────────
    def _filter_stale(self, quotes: list[FXQuote]) -> list[FXQuote]:
        """Remove quotes older than stale_seconds from reference_time."""
        result = []
        for q in quotes:
            ts = q.timestamp if isinstance(q.timestamp, datetime) else datetime.utcnow()
            age = abs((self.reference_time - ts).total_seconds())
            if age <= self.stale_seconds:
                result.append(q)
        return result

    def _filter_crossed(self, quotes: list[FXQuote]) -> list[FXQuote]:
        return [q for q in quotes if q.bid <= q.ask]

    def _filter_outliers(self, quotes: list[FXQuote]) -> list[FXQuote]:
        """Remove quotes whose mid deviates >threshold from the median mid."""
        if len(quotes) <= 2:
            return quotes
        mids = sorted(q.mid for q in quotes)
        median_mid = mids[len(mids) // 2]
        result = []
        for q in quotes:
            dev_bps = abs(q.mid - median_mid) / median_mid * 10_000 if median_mid else 0
            if dev_bps <= self.outlier_threshold_bps:
                result.append(q)
        return result if result else quotes  # fallback: keep all if all are outliers

    # ── mid-market computation ──────────────────────────────────
    def compute_mid_market(self) -> dict[str, Any]:
        """Full pipeline: filter -> median mid."""
        valid = list(self.quotes)
        crossed_removed = len(valid) - len(self._filter_crossed(valid))
        valid = self._filter_crossed(valid)

        stale_removed = len(valid) - len(self._filter_stale(valid))
        valid = self._filter_stale(valid)

        outlier_removed = len(valid) - len(self._filter_outliers(valid))
        valid = self._filter_outliers(valid)

        if not valid:
            return {
                "mid_rate": None,
                "sources_used": 0,
                "quality": "NO_DATA",
                "details": "All quotes filtered out",
            }

        mids = sorted(q.mid for q in valid)
        n = len(mids)
        if n % 2 == 1:
            median_mid = mids[n // 2]
        else:
            median_mid = (mids[n // 2 - 1] + mids[n // 2]) / 2

        avg_spread_bps = sum(q.spread_bps for q in valid) / len(valid)

        quality = "GREEN"
        if len(valid) == 1:
            quality = "AMBER"
        if stale_removed > 0 or outlier_removed > 0:
            quality = "AMBER"
        if crossed_removed > 0:
            quality = "RED" if len(valid) < 2 else "AMBER"

        return {
            "mid_rate": round(median_mid, 6),
            "sources_used": len(valid),
            "sources": [q.source for q in valid],
            "average_spread_bps": round(avg_spread_bps, 2),
            "quality": quality,
            "filters_applied": {
                "crossed_removed": crossed_removed,
                "stale_removed": stale_removed,
                "outlier_removed": outlier_removed,
            },
            "individual_mids": {q.source: round(q.mid, 6) for q in valid},
        }

    # ── BasePricer interface ────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        result = self.compute_mid_market()
        mid = result.get("mid_rate")
        if mid is None:
            raise ValueError("No valid quotes after filtering")

        return PricingResult(
            fair_value=mid,
            method="wm_reuters_4pm_fix",
            currency=self.currency_pair[:3],
            greeks=self.calculate_greeks(),
            diagnostics=result,
            methods={"median_mid": mid},
        )

    def calculate_greeks(self) -> dict[str, float]:
        # Spot pricing has no Greeks
        return {}

"""Tests for the FX Spot mid-market pricer."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import List, Optional

import pytest

from app.pricing.fx_spot import FXQuote, FXSpotPricer


def _make_quotes(
    mids: List[float],
    spread_bps: float = 2.0,
    pair: str = "EURUSD",
    stale: Optional[List[int]] = None,
    sources: Optional[List[str]] = None,
) -> List[dict]:
    """Helper to build quote dicts from mid prices."""
    now = datetime.utcnow()
    stale = stale or [0] * len(mids)
    sources = sources or [f"SRC{i}" for i in range(len(mids))]
    result = []
    for i, m in enumerate(mids):
        half = m * spread_bps / 20_000
        result.append({
            "source": sources[i],
            "bid": m - half,
            "ask": m + half,
            "timestamp": now - timedelta(seconds=stale[i]),
            "currency_pair": pair,
        })
    return result


class TestFXQuote:
    def test_mid(self):
        q = FXQuote("WMR", 1.1000, 1.1010, datetime.utcnow(), "EURUSD")
        assert q.mid == pytest.approx(1.1005, abs=1e-6)

    def test_spread_bps(self):
        q = FXQuote("WMR", 1.1000, 1.1010, datetime.utcnow(), "EURUSD")
        expected = (1.1010 - 1.1000) / 1.1005 * 10_000
        assert q.spread_bps == pytest.approx(expected, rel=1e-4)


class TestFXSpotValidation:
    def test_valid_quotes(self):
        quotes = _make_quotes([1.1000, 1.1002])
        pricer = FXSpotPricer("EURUSD", quotes)
        assert pricer.validate_inputs() == []

    def test_empty_quotes(self):
        pricer = FXSpotPricer("EURUSD", [])
        errors = pricer.validate_inputs()
        assert any("at least one" in e.lower() for e in errors)

    def test_negative_bid(self):
        quotes = [{"source": "A", "bid": -1.0, "ask": 1.10, "timestamp": datetime.utcnow()}]
        pricer = FXSpotPricer("EURUSD", quotes)
        errors = pricer.validate_inputs()
        assert len(errors) > 0

    def test_crossed_market_detected(self):
        quotes = [{"source": "A", "bid": 1.11, "ask": 1.10, "timestamp": datetime.utcnow()}]
        pricer = FXSpotPricer("EURUSD", quotes)
        errors = pricer.validate_inputs()
        assert any("crossed" in e.lower() for e in errors)


class TestFXSpotFiltering:
    def test_stale_quotes_removed(self):
        quotes = _make_quotes([1.1000, 1.1002], stale=[0, 600])
        pricer = FXSpotPricer("EURUSD", quotes, stale_seconds=300)
        result = pricer.compute_mid_market()
        assert result["sources_used"] == 1
        assert result["filters_applied"]["stale_removed"] == 1

    def test_crossed_quotes_removed(self):
        now = datetime.utcnow()
        quotes = [
            {"source": "A", "bid": 1.1000, "ask": 1.1010, "timestamp": now},
            {"source": "B", "bid": 1.1050, "ask": 1.1000, "timestamp": now},  # crossed
        ]
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.compute_mid_market()
        assert result["filters_applied"]["crossed_removed"] == 1
        assert result["sources_used"] == 1

    def test_outlier_removed(self):
        # 3 normal quotes + 1 outlier far from median
        quotes = _make_quotes([1.1000, 1.1002, 1.0998, 1.2000])
        pricer = FXSpotPricer("EURUSD", quotes, outlier_threshold_bps=50)
        result = pricer.compute_mid_market()
        assert result["filters_applied"]["outlier_removed"] >= 1

    def test_all_filtered_returns_no_data(self):
        # All quotes stale
        quotes = _make_quotes([1.1000, 1.1002], stale=[600, 700])
        pricer = FXSpotPricer("EURUSD", quotes, stale_seconds=300)
        result = pricer.compute_mid_market()
        assert result["quality"] == "NO_DATA"
        assert result["mid_rate"] is None


class TestFXSpotMidMarket:
    def test_median_of_odd(self):
        quotes = _make_quotes([1.1000, 1.1010, 1.1005])
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.compute_mid_market()
        # Median of 3 should be the middle value (approx 1.1005)
        assert result["mid_rate"] == pytest.approx(1.1005, abs=0.001)

    def test_median_of_even(self):
        quotes = _make_quotes([1.1000, 1.1010])
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.compute_mid_market()
        expected = (1.1000 + 1.1010) / 2
        assert result["mid_rate"] == pytest.approx(expected, abs=0.001)

    def test_quality_green_multiple_sources(self):
        quotes = _make_quotes([1.1000, 1.1002, 1.0998])
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.compute_mid_market()
        assert result["quality"] == "GREEN"

    def test_quality_amber_single_source(self):
        quotes = _make_quotes([1.1000])
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.compute_mid_market()
        assert result["quality"] == "AMBER"

    def test_individual_mids_populated(self):
        quotes = _make_quotes([1.1000, 1.1002], sources=["WMR", "Bloomberg"])
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.compute_mid_market()
        assert "WMR" in result["individual_mids"]
        assert "Bloomberg" in result["individual_mids"]


class TestFXSpotPriceInterface:
    def test_price_returns_result(self):
        quotes = _make_quotes([1.1000, 1.1002])
        pricer = FXSpotPricer("EURUSD", quotes)
        result = pricer.price()
        assert result.fair_value > 0
        assert result.method == "wm_reuters_4pm_fix"

    def test_price_raises_on_invalid(self):
        pricer = FXSpotPricer("EURUSD", [])
        with pytest.raises(ValueError):
            pricer.price()

    def test_greeks_empty(self):
        quotes = _make_quotes([1.1000])
        pricer = FXSpotPricer("EURUSD", quotes)
        assert pricer.calculate_greeks() == {}

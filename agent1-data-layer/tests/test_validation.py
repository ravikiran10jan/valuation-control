"""Tests for the data validation engine."""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services.validation import DataValidator, Severity


@pytest.fixture
def validator():
    return DataValidator(stale_threshold_hours=24, cross_val_threshold_bps=5.0)


# ── Market data validation ────────────────────────────────────────
class TestMarketDataValidation:
    def test_positive_value_passes(self, validator):
        report = validator.validate_market_data(
            "EUR/USD_Spot", 1.0823, datetime.utcnow()
        )
        assert report.passed

    def test_negative_value_fails(self, validator):
        report = validator.validate_market_data(
            "EUR/USD_Spot", -1.0, datetime.utcnow()
        )
        assert not report.passed
        assert any(r.rule == "positive_value" for r in report.failures)

    def test_stale_data_fails(self, validator):
        old_time = datetime.utcnow() - timedelta(hours=25)
        report = validator.validate_market_data(
            "EUR/USD_Spot", 1.0823, old_time
        )
        assert not report.passed
        assert any(r.rule == "stale_data" for r in report.failures)

    def test_cross_validation_within_threshold(self, validator):
        report = validator.validate_market_data(
            "EUR/USD_Spot", 1.0823, datetime.utcnow(), secondary_value=1.0824
        )
        assert report.passed

    def test_cross_validation_exceeds_threshold(self, validator):
        report = validator.validate_market_data(
            "EUR/USD_Spot", 1.0823, datetime.utcnow(), secondary_value=1.0900
        )
        assert not report.passed
        assert any(r.rule == "cross_validation" for r in report.failures)


# ── Vol surface validation ────────────────────────────────────────
class TestVolSurfaceValidation:
    def test_valid_surface(self, validator):
        report = validator.validate_vol_surface(
            "EUR/USD", "1Y", {"25P": 11.5, "ATM": 10.8, "25C": 10.2}
        )
        assert report.passed

    def test_negative_vol_fails(self, validator):
        report = validator.validate_vol_surface(
            "EUR/USD", "1Y", {"25P": -1.0, "ATM": 10.8, "25C": 10.2}
        )
        assert not report.passed
        assert any(r.severity == Severity.CRITICAL for r in report.failures)

    def test_butterfly_arbitrage_detected(self, validator):
        # butterfly = (25P + 25C)/2 - ATM = (5 + 5)/2 - 10 = -5 -> arbitrage
        report = validator.validate_vol_surface(
            "EUR/USD", "1Y", {"25P": 5.0, "ATM": 10.0, "25C": 5.0}
        )
        assert not report.passed
        assert any(r.rule == "vol_butterfly_arbitrage" for r in report.failures)


# ── Yield curve validation ────────────────────────────────────────
class TestYieldCurveValidation:
    def test_valid_curve(self, validator):
        report = validator.validate_yield_curve(
            "USD_SOFR", {"1M": 5.31, "3M": 5.28, "1Y": 4.89, "10Y": 3.85}
        )
        assert report.passed

    def test_out_of_range_rate(self, validator):
        report = validator.validate_yield_curve(
            "USD_SOFR", {"1M": 25.0}
        )
        assert not report.passed


# ── Position validation ───────────────────────────────────────────
class TestPositionValidation:
    def test_valid_position(self, validator):
        report = validator.validate_position(
            trade_id="T001",
            notional=Decimal("1000000"),
            trade_date=date(2024, 1, 1),
            maturity_date=date(2025, 1, 1),
            product_type="IRS",
            asset_class="Rates",
        )
        assert report.passed

    def test_negative_notional(self, validator):
        report = validator.validate_position(
            trade_id="T002",
            notional=Decimal("-500"),
            trade_date=date(2024, 1, 1),
            maturity_date=date(2025, 1, 1),
            product_type="IRS",
            asset_class="Rates",
        )
        assert not report.passed

    def test_maturity_before_trade_date(self, validator):
        report = validator.validate_position(
            trade_id="T003",
            notional=Decimal("1000000"),
            trade_date=date(2025, 1, 1),
            maturity_date=date(2024, 1, 1),
            product_type="IRS",
            asset_class="Rates",
        )
        assert not report.passed

    def test_mismatched_product_asset_class(self, validator):
        report = validator.validate_position(
            trade_id="T004",
            notional=Decimal("1000000"),
            trade_date=date(2024, 1, 1),
            maturity_date=date(2025, 1, 1),
            product_type="IRS",
            asset_class="FX",  # IRS is not an FX product
        )
        failures = [r for r in report.results if not r.passed]
        assert any(r.rule == "product_asset_class_match" for r in failures)

"""Tests for the Distressed Loan pricer."""

import math

import pytest

from app.pricing.credit_loan import DistressedLoanPricer


@pytest.fixture
def loan_pricer() -> DistressedLoanPricer:
    return DistressedLoanPricer(
        notional=500_000_000,
        collateral={"inventory": 300_000_000, "ppe": 200_000_000},
        financials={"ebitda": 80_000_000, "total_debt": 600_000_000},
        time_horizon=1.5,
    )


class TestCreditInputValidation:
    def test_valid_inputs(self, loan_pricer: DistressedLoanPricer):
        assert loan_pricer.validate_inputs() == []

    def test_invalid_notional(self):
        p = DistressedLoanPricer(
            notional=0, collateral={}, financials={"ebitda": 100},
        )
        assert len(p.validate_inputs()) > 0

    def test_missing_ebitda(self):
        p = DistressedLoanPricer(
            notional=100, collateral={}, financials={"revenue": 200},
        )
        assert any("ebitda" in e for e in p.validate_inputs())


class TestCreditScenarios:
    def test_restructuring_positive(self, loan_pricer: DistressedLoanPricer):
        val = loan_pricer.restructuring_scenario()
        assert val > 0

    def test_liquidation_bounded(self, loan_pricer: DistressedLoanPricer):
        val = loan_pricer.liquidation_scenario()
        assert 0 < val <= loan_pricer.notional

    def test_comps_positive(self, loan_pricer: DistressedLoanPricer):
        val = loan_pricer.market_comps_scenario()
        assert val > 0

    def test_comps_with_explicit_recovery(self):
        p = DistressedLoanPricer(
            notional=100_000_000,
            collateral={"cash": 10_000_000},
            financials={"ebitda": 20_000_000},
            comps_recovery_rate=0.45,
        )
        assert p.market_comps_scenario() == pytest.approx(45_000_000)


class TestCreditPricing:
    def test_price_positive(self, loan_pricer: DistressedLoanPricer):
        result = loan_pricer.price()
        assert result.fair_value > 0

    def test_recovery_rate_in_range(self, loan_pricer: DistressedLoanPricer):
        result = loan_pricer.price()
        rr = result.diagnostics["recovery_rate"]
        assert 0 < rr <= 1.0

    def test_scenarios_in_diagnostics(self, loan_pricer: DistressedLoanPricer):
        result = loan_pricer.price()
        for key in ("restructuring", "liquidation", "comps"):
            assert key in result.diagnostics["scenario_values"]


class TestCreditGreeks:
    def test_greeks_keys(self, loan_pricer: DistressedLoanPricer):
        greeks = loan_pricer.calculate_greeks()
        assert "discount_rate_sensitivity" in greeks
        assert "ebitda_sensitivity_10pct" in greeks

    def test_discount_rate_sens_negative(self, loan_pricer: DistressedLoanPricer):
        """Higher discount rate -> lower PV -> negative sensitivity."""
        greeks = loan_pricer.calculate_greeks()
        assert greeks["discount_rate_sensitivity"] < 0

    def test_ebitda_sens_positive(self, loan_pricer: DistressedLoanPricer):
        """Higher EBITDA -> higher recovery."""
        greeks = loan_pricer.calculate_greeks()
        assert greeks["ebitda_sensitivity_10pct"] > 0

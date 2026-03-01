"""Tests for the FX Forward pricer (covered interest rate parity)."""

import math

import pytest

from app.pricing.fx_forward import FXForwardPricer


@pytest.fixture
def eurusd_fwd() -> FXForwardPricer:
    """EUR/USD forward with typical market parameters."""
    return FXForwardPricer(
        spot=1.0850,
        r_dom=0.05,
        r_for=0.03,
        maturity=1.0,
        notional=1_000_000,
        currency_pair="EURUSD",
    )


@pytest.fixture
def eurusd_fwd_simple() -> FXForwardPricer:
    """Simple compounding variant."""
    return FXForwardPricer(
        spot=1.0850,
        r_dom=0.05,
        r_for=0.03,
        maturity=1.0,
        notional=1_000_000,
        currency_pair="EURUSD",
        compounding="simple",
    )


class TestFXForwardValidation:
    def test_valid_inputs(self, eurusd_fwd: FXForwardPricer):
        assert eurusd_fwd.validate_inputs() == []

    def test_negative_spot(self):
        p = FXForwardPricer(spot=-1.0, r_dom=0.05, r_for=0.03, maturity=1.0)
        errors = p.validate_inputs()
        assert any("spot" in e for e in errors)

    def test_negative_maturity(self):
        p = FXForwardPricer(spot=1.10, r_dom=0.05, r_for=0.03, maturity=-0.5)
        errors = p.validate_inputs()
        assert any("maturity" in e for e in errors)


class TestForwardRate:
    def test_continuous_formula(self, eurusd_fwd: FXForwardPricer):
        """F = S * exp((r_d - r_f) * T)."""
        expected = 1.0850 * math.exp((0.05 - 0.03) * 1.0)
        assert eurusd_fwd.forward_rate() == pytest.approx(expected, rel=1e-10)

    def test_simple_formula(self, eurusd_fwd_simple: FXForwardPricer):
        """F = S * (1 + r_d*T) / (1 + r_f*T)."""
        expected = 1.0850 * (1 + 0.05) / (1 + 0.03)
        assert eurusd_fwd_simple.forward_rate() == pytest.approx(expected, rel=1e-10)

    def test_zero_maturity_equals_spot(self):
        p = FXForwardPricer(spot=1.10, r_dom=0.05, r_for=0.03, maturity=0.0)
        assert p.forward_rate() == pytest.approx(1.10, rel=1e-10)

    def test_higher_domestic_rate_increases_forward(self):
        """r_dom > r_for -> F > S (forward premium for base currency)."""
        p = FXForwardPricer(spot=1.10, r_dom=0.10, r_for=0.02, maturity=1.0)
        assert p.forward_rate() > 1.10

    def test_higher_foreign_rate_decreases_forward(self):
        """r_dom < r_for -> F < S."""
        p = FXForwardPricer(spot=1.10, r_dom=0.02, r_for=0.10, maturity=1.0)
        assert p.forward_rate() < 1.10


class TestForwardPoints:
    def test_points_sign(self, eurusd_fwd: FXForwardPricer):
        """r_dom > r_for -> forward points positive."""
        assert eurusd_fwd.forward_points() > 0

    def test_points_pips_scaling(self, eurusd_fwd: FXForwardPricer):
        pts = eurusd_fwd.forward_points()
        pips = eurusd_fwd.forward_points_pips()
        assert pips == pytest.approx(pts * 10_000, rel=1e-10)


class TestMarkToMarket:
    def test_mtm_zero_when_no_strike(self, eurusd_fwd: FXForwardPricer):
        assert eurusd_fwd.mark_to_market() == 0.0

    def test_mtm_positive_when_strike_below_forward(self):
        """Long position gains if current forward > contracted strike."""
        p = FXForwardPricer(
            spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0,
            notional=1_000_000, strike=1.08,
        )
        assert p.mark_to_market() > 0

    def test_mtm_negative_when_strike_above_forward(self):
        p = FXForwardPricer(
            spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0,
            notional=1_000_000, strike=1.20,
        )
        assert p.mark_to_market() < 0

    def test_mtm_at_forward_strike_is_zero(self):
        p = FXForwardPricer(
            spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0,
            notional=1_000_000,
        )
        fwd = p.forward_rate()
        p2 = FXForwardPricer(
            spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0,
            notional=1_000_000, strike=fwd,
        )
        assert p2.mark_to_market() == pytest.approx(0.0, abs=0.01)


class TestTermStructure:
    def test_default_tenors(self, eurusd_fwd: FXForwardPricer):
        ts = eurusd_fwd.term_structure()
        assert len(ts) >= 5
        assert all("forward_rate" in row for row in ts)
        assert all("forward_points_pips" in row for row in ts)

    def test_custom_tenors(self, eurusd_fwd: FXForwardPricer):
        ts = eurusd_fwd.term_structure([0.25, 0.5, 1.0])
        assert len(ts) == 3

    def test_term_structure_monotonic_for_positive_spread(self):
        """With r_dom > r_for, forward rate should increase with tenor."""
        p = FXForwardPricer(spot=1.10, r_dom=0.06, r_for=0.02, maturity=1.0)
        ts = p.term_structure([0.25, 0.5, 1.0, 2.0])
        rates = [row["forward_rate"] for row in ts]
        for i in range(1, len(rates)):
            assert rates[i] > rates[i - 1]


class TestFXForwardGreeks:
    def test_delta_positive(self, eurusd_fwd: FXForwardPricer):
        greeks = eurusd_fwd.calculate_greeks()
        assert greeks["delta"] > 0

    def test_rho_domestic_positive(self, eurusd_fwd: FXForwardPricer):
        """Higher r_dom increases forward -> positive rho_domestic."""
        greeks = eurusd_fwd.calculate_greeks()
        assert greeks["rho_domestic"] > 0

    def test_rho_foreign_negative(self, eurusd_fwd: FXForwardPricer):
        """Higher r_for decreases forward -> negative rho_foreign."""
        greeks = eurusd_fwd.calculate_greeks()
        assert greeks["rho_foreign"] < 0

    def test_mtm_delta_present_when_strike(self):
        p = FXForwardPricer(spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0, strike=1.08)
        greeks = p.calculate_greeks()
        assert "mtm_delta" in greeks


class TestFXForwardPriceInterface:
    def test_price_returns_result(self, eurusd_fwd: FXForwardPricer):
        result = eurusd_fwd.price()
        assert result.method == "interest_rate_parity"
        assert result.fair_value > 0

    def test_price_with_strike_returns_mtm(self):
        p = FXForwardPricer(
            spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0,
            notional=1_000_000, strike=1.08,
        )
        result = p.price()
        assert result.fair_value != 0  # MTM should be non-zero

    def test_diagnostics_populated(self, eurusd_fwd: FXForwardPricer):
        result = eurusd_fwd.price()
        assert "forward_rate" in result.diagnostics
        assert "forward_points_pips" in result.diagnostics

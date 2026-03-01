"""Tests for the Equity Option pricer."""

import math

import pytest

from app.pricing.equity_option import EquityOptionPricer


@pytest.fixture
def call_pricer() -> EquityOptionPricer:
    return EquityOptionPricer(
        spot=100.0,
        strike=100.0,
        maturity=1.0,
        vol=0.20,
        r_dom=0.05,
        dividend_yield=0.02,
        option_type="call",
        exercise_style="european",
        notional=1.0,
    )


@pytest.fixture
def put_pricer() -> EquityOptionPricer:
    return EquityOptionPricer(
        spot=100.0,
        strike=100.0,
        maturity=1.0,
        vol=0.20,
        r_dom=0.05,
        dividend_yield=0.02,
        option_type="put",
        exercise_style="european",
        notional=1.0,
    )


class TestEquityValidation:
    def test_valid(self, call_pricer: EquityOptionPricer):
        assert call_pricer.validate_inputs() == []

    def test_negative_spot(self):
        p = EquityOptionPricer(spot=-1, strike=100, maturity=1, vol=0.2, r_dom=0.05)
        assert len(p.validate_inputs()) > 0


class TestBlackScholes:
    def test_call_positive(self, call_pricer: EquityOptionPricer):
        assert call_pricer.price_black_scholes() > 0

    def test_put_positive(self, put_pricer: EquityOptionPricer):
        assert put_pricer.price_black_scholes() > 0

    def test_put_call_parity(self, call_pricer: EquityOptionPricer, put_pricer: EquityOptionPricer):
        """C - P = S*e^{-qT} - K*e^{-rT}."""
        C = call_pricer.price_black_scholes()
        P = put_pricer.price_black_scholes()
        S, K, r, q, T = 100, 100, 0.05, 0.02, 1.0
        parity_rhs = S * math.exp(-q * T) - K * math.exp(-r * T)
        assert abs((C - P) - parity_rhs) < 1e-8

    def test_deep_itm_call(self):
        """Deep ITM call ≈ S*e^{-qT} - K*e^{-rT}."""
        p = EquityOptionPricer(spot=200, strike=100, maturity=1, vol=0.20, r_dom=0.05, dividend_yield=0.02)
        intrinsic = 200 * math.exp(-0.02) - 100 * math.exp(-0.05)
        assert p.price_black_scholes() > intrinsic * 0.99


class TestBinomialTree:
    def test_european_close_to_bs(self, call_pricer: EquityOptionPricer):
        bs = call_pricer.price_black_scholes()
        binom = call_pricer.price_binomial(n_steps=500)
        assert abs(binom - bs) / bs < 0.005  # within 0.5%

    def test_american_put_geq_european(self):
        """American put >= European put (early exercise premium)."""
        kwargs = dict(spot=100, strike=100, maturity=1, vol=0.30, r_dom=0.05, dividend_yield=0.0, option_type="put")
        euro = EquityOptionPricer(exercise_style="european", **kwargs).price_binomial()
        amer = EquityOptionPricer(exercise_style="american", **kwargs).price_binomial()
        assert amer >= euro - 1e-6


class TestEquityGreeks:
    def test_call_delta_positive(self, call_pricer: EquityOptionPricer):
        greeks = call_pricer.bs_greeks()
        assert greeks["delta"] > 0

    def test_put_delta_negative(self, put_pricer: EquityOptionPricer):
        greeks = put_pricer.bs_greeks()
        assert greeks["delta"] < 0

    def test_gamma_positive(self, call_pricer: EquityOptionPricer):
        greeks = call_pricer.bs_greeks()
        assert greeks["gamma"] > 0

    def test_vega_positive(self, call_pricer: EquityOptionPricer):
        greeks = call_pricer.bs_greeks()
        assert greeks["vega"] > 0

    def test_atm_call_delta_near_half(self):
        """ATM call delta ≈ 0.5 (approximately, with dividend adjustment)."""
        p = EquityOptionPricer(spot=100, strike=100, maturity=1, vol=0.20, r_dom=0.05, dividend_yield=0.0)
        greeks = p.bs_greeks()
        assert 0.4 < greeks["delta"] < 0.7


class TestEquityPriceResult:
    def test_full_result(self, call_pricer: EquityOptionPricer):
        result = call_pricer.price()
        assert result.fair_value > 0
        assert "black_scholes" in result.methods
        assert "binomial_tree" in result.methods
        assert result.diagnostics["option_type"] == "call"

"""Tests for the FX Vanilla option pricer (Garman-Kohlhagen)."""

import math

import pytest
from scipy.stats import norm

from app.pricing.fx_vanilla import FXVanillaOptionPricer


@pytest.fixture
def call_pricer() -> FXVanillaOptionPricer:
    return FXVanillaOptionPricer(
        spot=1.10,
        strike=1.10,
        maturity=1.0,
        vol=0.10,
        r_dom=0.05,
        r_for=0.03,
        notional=1_000_000,
        option_type="call",
        currency_pair="EURUSD",
    )


@pytest.fixture
def put_pricer() -> FXVanillaOptionPricer:
    return FXVanillaOptionPricer(
        spot=1.10,
        strike=1.10,
        maturity=1.0,
        vol=0.10,
        r_dom=0.05,
        r_for=0.03,
        notional=1_000_000,
        option_type="put",
        currency_pair="EURUSD",
    )


class TestFXVanillaValidation:
    def test_valid(self, call_pricer: FXVanillaOptionPricer):
        assert call_pricer.validate_inputs() == []

    def test_negative_spot(self):
        p = FXVanillaOptionPricer(spot=-1, strike=1.10, maturity=1, vol=0.1, r_dom=0.05, r_for=0.03)
        assert len(p.validate_inputs()) > 0

    def test_zero_vol(self):
        p = FXVanillaOptionPricer(spot=1.1, strike=1.1, maturity=1, vol=0.0, r_dom=0.05, r_for=0.03)
        assert any("vol" in e for e in p.validate_inputs())

    def test_invalid_option_type(self):
        p = FXVanillaOptionPricer(spot=1.1, strike=1.1, maturity=1, vol=0.1, r_dom=0.05, r_for=0.03, option_type="straddle")
        assert any("option_type" in e for e in p.validate_inputs())


class TestGarmanKohlhagen:
    def test_call_positive(self, call_pricer: FXVanillaOptionPricer):
        px = call_pricer.price_garman_kohlhagen()
        assert px > 0

    def test_put_positive(self, put_pricer: FXVanillaOptionPricer):
        px = put_pricer.price_garman_kohlhagen()
        assert px > 0

    def test_put_call_parity(self, call_pricer: FXVanillaOptionPricer, put_pricer: FXVanillaOptionPricer):
        """C - P = S*e^{-r_f*T} - K*e^{-r_d*T} (per unit notional, then multiply)."""
        C = call_pricer.price_garman_kohlhagen()
        P = put_pricer.price_garman_kohlhagen()
        S, K, r_d, r_f, T, N = 1.10, 1.10, 0.05, 0.03, 1.0, 1_000_000
        parity_rhs = (S * math.exp(-r_f * T) - K * math.exp(-r_d * T)) * N
        assert abs((C - P) - parity_rhs) < 1e-4

    def test_deep_itm_call_approx_intrinsic(self):
        """Deep ITM call -> price ≈ notional * (S*e^{-r_f*T} - K*e^{-r_d*T})."""
        p = FXVanillaOptionPricer(
            spot=1.50, strike=1.00, maturity=1.0, vol=0.10,
            r_dom=0.05, r_for=0.03, notional=1_000_000,
        )
        intrinsic = (1.50 * math.exp(-0.03) - 1.00 * math.exp(-0.05)) * 1_000_000
        px = p.price_garman_kohlhagen()
        assert px > intrinsic * 0.99

    def test_higher_vol_higher_price(self):
        low_vol = FXVanillaOptionPricer(spot=1.1, strike=1.1, maturity=1, vol=0.05, r_dom=0.05, r_for=0.03)
        high_vol = FXVanillaOptionPricer(spot=1.1, strike=1.1, maturity=1, vol=0.30, r_dom=0.05, r_for=0.03)
        assert high_vol.price_garman_kohlhagen() > low_vol.price_garman_kohlhagen()

    def test_longer_maturity_higher_call_price(self):
        short = FXVanillaOptionPricer(spot=1.1, strike=1.1, maturity=0.25, vol=0.10, r_dom=0.05, r_for=0.03)
        long = FXVanillaOptionPricer(spot=1.1, strike=1.1, maturity=2.0, vol=0.10, r_dom=0.05, r_for=0.03)
        assert long.price_garman_kohlhagen() > short.price_garman_kohlhagen()


class TestGKGreeks:
    def test_call_delta_positive(self, call_pricer: FXVanillaOptionPricer):
        greeks = call_pricer.gk_greeks()
        assert greeks["delta"] > 0

    def test_put_delta_negative(self, put_pricer: FXVanillaOptionPricer):
        greeks = put_pricer.gk_greeks()
        assert greeks["delta"] < 0

    def test_gamma_positive(self, call_pricer: FXVanillaOptionPricer):
        greeks = call_pricer.gk_greeks()
        assert greeks["gamma"] > 0

    def test_vega_positive(self, call_pricer: FXVanillaOptionPricer):
        greeks = call_pricer.gk_greeks()
        assert greeks["vega"] > 0

    def test_greeks_keys(self, call_pricer: FXVanillaOptionPricer):
        greeks = call_pricer.gk_greeks()
        expected_keys = {"delta", "gamma", "vega", "theta", "rho_domestic", "rho_foreign", "vanna", "volga"}
        assert expected_keys == set(greeks.keys())

    def test_greeks_finite(self, call_pricer: FXVanillaOptionPricer):
        greeks = call_pricer.gk_greeks()
        for k, v in greeks.items():
            assert math.isfinite(v), f"{k} is not finite: {v}"

    def test_atm_call_delta_near_half(self):
        """ATM call delta ≈ 0.5*e^{-r_f*T} * N ≈ N/2 (roughly)."""
        p = FXVanillaOptionPricer(
            spot=1.10, strike=1.10, maturity=1.0, vol=0.10,
            r_dom=0.05, r_for=0.03, notional=1,
        )
        greeks = p.gk_greeks()
        assert 0.3 < greeks["delta"] < 0.7


class TestFXVanillaPriceInterface:
    def test_price_returns_result(self, call_pricer: FXVanillaOptionPricer):
        result = call_pricer.price()
        assert result.fair_value > 0
        assert result.method == "garman_kohlhagen"
        assert "garman_kohlhagen" in result.methods

    def test_diagnostics_populated(self, call_pricer: FXVanillaOptionPricer):
        result = call_pricer.price()
        assert "moneyness" in result.diagnostics
        assert "forward" in result.diagnostics
        assert result.diagnostics["option_type"] == "call"

    def test_price_raises_on_invalid(self):
        p = FXVanillaOptionPricer(spot=-1, strike=1.1, maturity=1, vol=0.1, r_dom=0.05, r_for=0.03)
        with pytest.raises(ValueError):
            p.price()

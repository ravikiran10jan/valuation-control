"""Tests for the FX Barrier option pricer."""

import math

import pytest

from app.pricing.fx_barrier import FXBarrierPricer


@pytest.fixture
def eurusd_dnt_pricer() -> FXBarrierPricer:
    """EUR/USD Double-No-Touch option."""
    return FXBarrierPricer(
        spot=1.0850,
        lower_barrier=1.0500,
        upper_barrier=1.1200,
        maturity=0.5,
        notional=10_000_000,
        vol=0.08,
        r_dom=0.05,
        r_for=0.03,
        barrier_type="DNT",
    )


class TestFXBarrierInputValidation:
    def test_valid_inputs(self, eurusd_dnt_pricer: FXBarrierPricer):
        assert eurusd_dnt_pricer.validate_inputs() == []

    def test_barriers_inverted(self):
        pricer = FXBarrierPricer(
            spot=1.10, lower_barrier=1.15, upper_barrier=1.05,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
        )
        errors = pricer.validate_inputs()
        assert any("lower_barrier" in e for e in errors)

    def test_spot_outside_barriers(self):
        pricer = FXBarrierPricer(
            spot=1.20, lower_barrier=1.05, upper_barrier=1.12,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
        )
        errors = pricer.validate_inputs()
        assert any("spot" in e for e in errors)


class TestFXBarrierAnalytical:
    def test_price_positive(self, eurusd_dnt_pricer: FXBarrierPricer):
        value = eurusd_dnt_pricer.price_analytical()
        assert value > 0

    def test_price_bounded_by_notional(self, eurusd_dnt_pricer: FXBarrierPricer):
        value = eurusd_dnt_pricer.price_analytical()
        assert value <= eurusd_dnt_pricer.notional

    def test_survival_probability_in_range(self, eurusd_dnt_pricer: FXBarrierPricer):
        sp = eurusd_dnt_pricer._survival_probability_series()
        assert 0 <= sp <= 1

    def test_wider_barriers_higher_price(self):
        """Wider barriers -> higher survival probability -> higher DNT value."""
        narrow = FXBarrierPricer(
            spot=1.10, lower_barrier=1.08, upper_barrier=1.12,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
        )
        wide = FXBarrierPricer(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
        )
        assert wide.price_analytical() > narrow.price_analytical()

    def test_higher_vol_lower_price(self):
        """Higher vol -> more likely to hit barrier -> lower DNT price."""
        low_vol = FXBarrierPricer(
            spot=1.10, lower_barrier=1.05, upper_barrier=1.15,
            maturity=0.5, notional=1e6, vol=0.05, r_dom=0.05, r_for=0.03,
        )
        high_vol = FXBarrierPricer(
            spot=1.10, lower_barrier=1.05, upper_barrier=1.15,
            maturity=0.5, notional=1e6, vol=0.20, r_dom=0.05, r_for=0.03,
        )
        assert low_vol.price_analytical() > high_vol.price_analytical()


class TestFXBarrierMonteCarlo:
    def test_mc_close_to_analytical(self):
        """Use wide barriers where discrete-monitoring MC converges to continuous analytical."""
        pricer = FXBarrierPricer(
            spot=1.10,
            lower_barrier=0.90,
            upper_barrier=1.30,
            maturity=0.5,
            notional=1_000_000,
            vol=0.10,
            r_dom=0.05,
            r_for=0.03,
            barrier_type="DNT",
            mc_paths=100_000,
        )
        analytical = pricer.price_analytical()
        mc = pricer.price_monte_carlo()
        # With wide barriers, discrete MC should be within 5% of continuous analytical
        assert abs(mc - analytical) / analytical < 0.05

    def test_dot_barrier_type(self):
        pricer = FXBarrierPricer(
            spot=1.10, lower_barrier=1.05, upper_barrier=1.15,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
            barrier_type="DOT",
        )
        dnt_val = FXBarrierPricer(
            spot=1.10, lower_barrier=1.05, upper_barrier=1.15,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
            barrier_type="DNT",
        ).price_analytical()
        dot_val = pricer.price_analytical()
        discount = math.exp(-0.05 * 0.5)
        # DOT + DNT ≈ PV of notional
        assert abs(dot_val + dnt_val - 1e6 * discount) / (1e6 * discount) < 0.01


class TestFXBarrierGreeks:
    def test_greeks_dict_keys(self, eurusd_dnt_pricer: FXBarrierPricer):
        greeks = eurusd_dnt_pricer.calculate_greeks()
        for key in ("delta", "gamma", "vega", "theta", "rho"):
            assert key in greeks

    def test_greeks_finite(self, eurusd_dnt_pricer: FXBarrierPricer):
        greeks = eurusd_dnt_pricer.calculate_greeks()
        for v in greeks.values():
            assert math.isfinite(v)

    def test_dnt_negative_vega(self, eurusd_dnt_pricer: FXBarrierPricer):
        """DNT value decreases with higher vol -> vega should be negative."""
        greeks = eurusd_dnt_pricer.calculate_greeks()
        assert greeks["vega"] < 0


class TestFXBarrierPriceResult:
    def test_price_returns_result(self, eurusd_dnt_pricer: FXBarrierPricer):
        result = eurusd_dnt_pricer.price()
        assert result.fair_value > 0
        assert result.method == "analytical"
        assert "analytical" in result.methods
        assert "monte_carlo" in result.methods
        assert "survival_probability" in result.diagnostics

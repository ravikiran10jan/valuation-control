"""Tests for the Hull-White Bermudan Swaption pricer."""

import math

import pytest

from app.pricing.rates_swaption import HullWhitePricer


@pytest.fixture
def bermudan_pricer() -> HullWhitePricer:
    """10-into-10 Bermudan swaption."""
    yield_curve = [
        (0.5, 0.04),
        (1.0, 0.042),
        (2.0, 0.044),
        (3.0, 0.045),
        (5.0, 0.046),
        (7.0, 0.047),
        (10.0, 0.048),
        (15.0, 0.049),
        (20.0, 0.050),
    ]
    return HullWhitePricer(
        notional=50_000_000,
        fixed_rate=0.047,
        exercise_dates_years=[1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        swap_tenor=10.0,
        yield_curve=yield_curve,
        kappa=0.03,
        sigma=0.01,
        pay_frequency=0.5,
    )


class TestHullWhiteInputs:
    def test_constructs_ok(self, bermudan_pricer: HullWhitePricer):
        assert bermudan_pricer.notional == 50_000_000

    def test_zero_rate_interpolation(self, bermudan_pricer: HullWhitePricer):
        r = bermudan_pricer._zero_rate(2.5)
        # Should be between the 2Y and 3Y rates
        assert 0.044 <= r <= 0.045

    def test_discount_positive(self, bermudan_pricer: HullWhitePricer):
        df = bermudan_pricer._discount(5.0)
        assert 0 < df < 1


class TestHullWhitePricing:
    def test_tree_price_non_negative(self, bermudan_pricer: HullWhitePricer):
        value = bermudan_pricer._price_tree(n_steps=50)
        assert value >= 0

    def test_tree_price_finite(self, bermudan_pricer: HullWhitePricer):
        value = bermudan_pricer._price_tree(n_steps=50)
        assert math.isfinite(value)

    def test_higher_vol_higher_price(self):
        """Higher sigma -> higher option value."""
        curve = [(1.0, 0.04), (5.0, 0.045), (10.0, 0.05), (20.0, 0.052)]
        kwargs = dict(
            notional=10_000_000,
            fixed_rate=0.047,
            exercise_dates_years=[1.0, 2.0, 3.0],
            swap_tenor=5.0,
            yield_curve=curve,
            kappa=0.03,
            pay_frequency=0.5,
        )
        low = HullWhitePricer(sigma=0.005, **kwargs)._price_tree(n_steps=50)
        high = HullWhitePricer(sigma=0.02, **kwargs)._price_tree(n_steps=50)
        assert high >= low


class TestHullWhiteGreeks:
    def test_greeks_keys(self, bermudan_pricer: HullWhitePricer):
        greeks = bermudan_pricer.calculate_greeks()
        assert "dv01" in greeks
        assert "vega" in greeks

    def test_greeks_finite(self, bermudan_pricer: HullWhitePricer):
        greeks = bermudan_pricer.calculate_greeks()
        for v in greeks.values():
            assert math.isfinite(v)


class TestHullWhitePriceResult:
    def test_full_price_result(self, bermudan_pricer: HullWhitePricer):
        result = bermudan_pricer.price()
        assert result.fair_value >= 0
        assert "trinomial_tree" in result.methods
        assert result.method == "hull_white_trinomial_tree"

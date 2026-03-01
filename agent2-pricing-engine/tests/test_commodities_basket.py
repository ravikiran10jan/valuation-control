"""Tests for the Commodities Basket pricer."""

import math

import numpy as np
import pytest

from app.pricing.commodities_basket import CommoditiesBasketPricer


@pytest.fixture
def basket_pricer() -> CommoditiesBasketPricer:
    return CommoditiesBasketPricer(
        asset_names=["WTI", "Gold", "Copper"],
        spots=[73.50, 2065.0, 3.82],
        vols=[0.285, 0.162, 0.224],
        drifts=[0.03, 0.02, 0.04],
        correlation_matrix=[
            [1.0, 0.15, 0.35],
            [0.15, 1.0, 0.20],
            [0.35, 0.20, 1.0],
        ],
        barriers=[55.0, 1800.0, 2.80],
        maturity=1.0,
        notional=5_000_000,
        mc_paths=10_000,  # fewer paths for speed in tests
    )


class TestCommoditiesInputValidation:
    def test_valid_inputs(self, basket_pricer: CommoditiesBasketPricer):
        assert basket_pricer.validate_inputs() == []

    def test_bad_corr_shape(self):
        p = CommoditiesBasketPricer(
            asset_names=["A", "B"],
            spots=[100, 200],
            vols=[0.2, 0.3],
            drifts=[0.02, 0.03],
            correlation_matrix=[[1.0, 0.5, 0.3], [0.5, 1.0, 0.2], [0.3, 0.2, 1.0]],
            barriers=[80, 150],
            maturity=1.0,
            notional=1e6,
        )
        errors = p.validate_inputs()
        assert any("correlation" in e for e in errors)

    def test_non_psd_corr(self):
        p = CommoditiesBasketPricer(
            asset_names=["A", "B"],
            spots=[100, 200],
            vols=[0.2, 0.3],
            drifts=[0.02, 0.03],
            correlation_matrix=[[1.0, 1.5], [1.5, 1.0]],
            barriers=[80, 150],
            maturity=1.0,
            notional=1e6,
        )
        errors = p.validate_inputs()
        assert any("positive semi-definite" in e for e in errors)


class TestCommoditiesPricing:
    def test_mc_price_non_negative(self, basket_pricer: CommoditiesBasketPricer):
        val = basket_pricer.price_monte_carlo()
        assert val >= 0

    def test_price_result_has_diagnostics(self, basket_pricer: CommoditiesBasketPricer):
        result = basket_pricer.price()
        assert "survival_rate" in result.diagnostics
        assert "mc_convergence" in result.diagnostics

    def test_survival_rate_in_range(self, basket_pricer: CommoditiesBasketPricer):
        result = basket_pricer.price()
        assert 0 <= result.diagnostics["survival_rate"] <= 1


class TestCommoditiesGreeks:
    def test_per_asset_greeks(self, basket_pricer: CommoditiesBasketPricer):
        greeks = basket_pricer.calculate_greeks()
        for name in ["WTI", "Gold", "Copper"]:
            assert f"delta_{name}" in greeks
            assert f"vega_{name}" in greeks

    def test_greeks_finite(self, basket_pricer: CommoditiesBasketPricer):
        greeks = basket_pricer.calculate_greeks()
        for v in greeks.values():
            assert math.isfinite(v)

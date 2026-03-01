"""Tests for FX Barrier PDE and Local Vol Dupire pricers."""

import math

import pytest

from app.pricing.fx_barrier import FXBarrierPricer
from app.pricing.fx_pde import FXBarrierPDE, LocalVolDupirePricer


# ── Crank-Nicolson PDE tests ─────────────────────────────────────────


class TestFXBarrierPDE:
    def test_price_positive(self):
        pde = FXBarrierPDE(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03,
        )
        value = pde.price()
        assert value > 0

    def test_price_bounded_by_notional(self):
        pde = FXBarrierPDE(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03,
        )
        assert pde.price() <= 1_000_000

    def test_pde_close_to_analytical(self):
        """PDE should converge to analytical for reasonable grid sizes."""
        pricer = FXBarrierPricer(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03,
        )
        analytical = pricer.price_analytical()
        pde_price = pricer.price_pde()
        rel_diff = abs(pde_price - analytical) / analytical
        assert rel_diff < 0.03, f"PDE={pde_price:.2f}, Analytical={analytical:.2f}, diff={rel_diff:.4f}"

    def test_wider_barriers_higher_price(self):
        narrow = FXBarrierPDE(
            spot=1.10, lower_barrier=1.08, upper_barrier=1.12,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
        )
        wide = FXBarrierPDE(
            spot=1.10, lower_barrier=0.95, upper_barrier=1.25,
            maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
        )
        assert wide.price() > narrow.price()

    def test_higher_vol_lower_dnt_price(self):
        low_vol = FXBarrierPDE(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1e6, vol=0.05, r_dom=0.05, r_for=0.03,
        )
        high_vol = FXBarrierPDE(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1e6, vol=0.25, r_dom=0.05, r_for=0.03,
        )
        assert low_vol.price() > high_vol.price()

    def test_dot_zero_terminal(self):
        """DOT terminal condition is 0 inside, so PDE value should be small for wide barriers."""
        pde = FXBarrierPDE(
            spot=1.10, lower_barrier=0.50, upper_barrier=1.70,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03, barrier_type="DOT",
        )
        value = pde.price()
        # For very wide barriers with low vol, DOT value should be very small
        assert value < 500_000


# ── Local Vol Dupire tests ───────────────────────────────────────────


class TestLocalVolDupire:
    def test_flat_vol_close_to_constant_vol_pde(self):
        """With flat local vol, LocalVolDupire should match FXBarrierPDE."""
        params = dict(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, r_dom=0.05, r_for=0.03,
        )
        pde = FXBarrierPDE(vol=0.10, **params)
        lv = LocalVolDupirePricer(flat_vol=0.10, **params)
        pde_val = pde.price()
        lv_val = lv.price()
        rel_diff = abs(pde_val - lv_val) / pde_val
        assert rel_diff < 0.02, f"PDE={pde_val:.2f}, LV={lv_val:.2f}, diff={rel_diff:.4f}"

    def test_local_vol_with_surface(self):
        """Providing a vol surface should still produce a valid price."""
        vol_surface = [
            {"spot": 1.05, "time": 0.25, "vol": 0.12},
            {"spot": 1.10, "time": 0.25, "vol": 0.10},
            {"spot": 1.15, "time": 0.25, "vol": 0.11},
            {"spot": 1.05, "time": 0.50, "vol": 0.13},
            {"spot": 1.10, "time": 0.50, "vol": 0.10},
            {"spot": 1.15, "time": 0.50, "vol": 0.12},
        ]
        lv = LocalVolDupirePricer(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, r_dom=0.05, r_for=0.03,
            vol_surface=vol_surface,
        )
        value = lv.price()
        assert value > 0
        assert value <= 1_000_000

    def test_price_positive(self):
        lv = LocalVolDupirePricer(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, r_dom=0.05, r_for=0.03,
            flat_vol=0.10,
        )
        assert lv.price() > 0


# ── Integration: barrier pricer calls all methods ────────────────────


class TestFXBarrierAllMethods:
    def test_price_result_has_all_methods(self):
        pricer = FXBarrierPricer(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03,
        )
        result = pricer.price()
        assert "analytical" in result.methods
        assert "monte_carlo" in result.methods
        assert "pde_finite_difference" in result.methods
        assert "local_vol_dupire" in result.methods

    def test_all_methods_positive(self):
        pricer = FXBarrierPricer(
            spot=1.10, lower_barrier=1.00, upper_barrier=1.20,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03,
        )
        result = pricer.price()
        for method, value in result.methods.items():
            assert value > 0, f"{method} returned non-positive: {value}"

    def test_methods_within_reasonable_range(self):
        """All 4+ methods should be within 10% of analytical for wide barriers."""
        pricer = FXBarrierPricer(
            spot=1.10, lower_barrier=0.95, upper_barrier=1.25,
            maturity=0.5, notional=1_000_000, vol=0.10,
            r_dom=0.05, r_for=0.03, mc_paths=50_000,
        )
        result = pricer.price()
        analytical = result.methods["analytical"]
        for method, value in result.methods.items():
            if method == "quantlib":
                continue  # may not be installed
            rel_diff = abs(value - analytical) / analytical
            assert rel_diff < 0.10, f"{method}={value:.2f} vs analytical={analytical:.2f}, diff={rel_diff:.4f}"

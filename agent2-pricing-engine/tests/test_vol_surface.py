"""Tests for the Vol Surface interpolator."""

import math

import pytest

from app.pricing.vol_surface import VolSurfaceInterpolator


@pytest.fixture
def vol_interp() -> VolSurfaceInterpolator:
    return VolSurfaceInterpolator(
        deltas=[0.10, 0.25, 0.50, 0.75, 0.90],
        vols=[0.195, 0.185, 0.178, 0.172, 0.168],
        forward=1.10,
        maturity=0.5,
    )


class TestCubicSpline:
    def test_interpolates_at_known_point(self, vol_interp: VolSurfaceInterpolator):
        """At a known delta, should return approximately the input vol."""
        vol = vol_interp.interpolate_cubic_spline(0.25)
        assert abs(vol - 0.185) < 1e-6

    def test_interpolates_between_points(self, vol_interp: VolSurfaceInterpolator):
        vol = vol_interp.interpolate_cubic_spline(0.35)
        assert 0.170 < vol < 0.190

    def test_monotonic_skew(self, vol_interp: VolSurfaceInterpolator):
        """For FX smile, put wing should have higher vol than call wing."""
        v_10p = vol_interp.interpolate_cubic_spline(0.10)
        v_50 = vol_interp.interpolate_cubic_spline(0.50)
        v_90c = vol_interp.interpolate_cubic_spline(0.90)
        assert v_10p > v_50 > v_90c


class TestSABR:
    def test_calibration_runs(self, vol_interp: VolSurfaceInterpolator):
        params = vol_interp.calibrate_sabr()
        assert "alpha" in params
        assert "rho" in params
        assert "nu" in params
        assert params["alpha"] > 0
        assert abs(params["rho"]) < 1
        assert params["nu"] > 0

    def test_sabr_at_atm(self, vol_interp: VolSurfaceInterpolator):
        vol = vol_interp.interpolate_sabr(0.50)
        # Should be close to ATM input vol
        assert abs(vol - 0.178) < 0.02

    def test_sabr_finite(self, vol_interp: VolSurfaceInterpolator):
        for d in [0.15, 0.30, 0.50, 0.70, 0.85]:
            vol = vol_interp.interpolate_sabr(d)
            assert math.isfinite(vol)
            assert vol > 0


class TestBuildSurface:
    def test_returns_both_methods(self, vol_interp: VolSurfaceInterpolator):
        surface = vol_interp.build_surface()
        assert "cubic_spline" in surface
        assert "sabr" in surface
        assert "sabr_params" in surface

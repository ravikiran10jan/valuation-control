"""Tests for the Monte Carlo engine."""

import math

import numpy as np
import pytest

from app.monte_carlo.engine import MCConfig, MonteCarloEngine


class TestMonteCarloSingleAsset:
    def test_path_shape(self):
        engine = MonteCarloEngine(MCConfig(num_paths=1000, time_steps=50, seed=42))
        paths = engine.generate_paths(spot=100, drift=0.05, vol=0.20, maturity=1.0)
        assert paths.shape == (1000, 51)  # 50 steps + initial

    def test_initial_spot(self):
        engine = MonteCarloEngine(MCConfig(num_paths=100, time_steps=10, seed=42))
        paths = engine.generate_paths(spot=42.0, drift=0.05, vol=0.20, maturity=1.0)
        np.testing.assert_allclose(paths[:, 0], 42.0)

    def test_positive_prices(self):
        engine = MonteCarloEngine(MCConfig(num_paths=5000, time_steps=100, seed=42))
        paths = engine.generate_paths(spot=100, drift=0.05, vol=0.30, maturity=2.0)
        assert np.all(paths > 0)

    def test_mean_matches_drift(self):
        """Terminal mean should be close to S*exp(drift*T)."""
        engine = MonteCarloEngine(MCConfig(num_paths=100_000, time_steps=252, seed=42))
        paths = engine.generate_paths(spot=100, drift=0.05, vol=0.20, maturity=1.0)
        terminal_mean = np.mean(paths[:, -1])
        expected = 100 * math.exp(0.05)
        assert abs(terminal_mean - expected) / expected < 0.02


class TestMonteCarloCorrelated:
    def test_correlated_shape(self):
        engine = MonteCarloEngine(MCConfig(num_paths=500, time_steps=50, seed=42))
        corr = np.eye(3)
        paths = engine.generate_correlated_paths(
            spots=[100, 200, 50],
            drifts=[0.03, 0.04, 0.05],
            vols=[0.2, 0.3, 0.25],
            correlation_matrix=corr,
            maturity=1.0,
        )
        assert paths.shape == (3, 500, 51)

    def test_initial_spots_correct(self):
        engine = MonteCarloEngine(MCConfig(num_paths=100, time_steps=10, seed=42))
        spots = [10.0, 20.0, 30.0]
        paths = engine.generate_correlated_paths(
            spots=spots,
            drifts=[0.02, 0.03, 0.04],
            vols=[0.1, 0.2, 0.15],
            correlation_matrix=np.eye(3),
            maturity=1.0,
        )
        for i, s in enumerate(spots):
            np.testing.assert_allclose(paths[i, :, 0], s)


class TestConvergenceCheck:
    def test_check_convergence(self):
        payoffs = np.random.default_rng(42).normal(100, 10, size=10000)
        stats = MonteCarloEngine.check_convergence(payoffs)
        assert "mean" in stats
        assert "stderr" in stats
        assert "ci_half_width" in stats
        assert stats["stderr"] > 0

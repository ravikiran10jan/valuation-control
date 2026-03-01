"""Generic Monte Carlo simulation engine used by multiple pricers."""

from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class MCConfig:
    num_paths: int = 50_000
    time_steps: int = 252
    seed: int | None = 42
    antithetic: bool = True


class MonteCarloEngine:
    """Correlated GBM path generator with optional antithetic variates."""

    def __init__(self, config: MCConfig | None = None):
        self.config = config or MCConfig()
        self.rng = np.random.default_rng(self.config.seed)

    # ── single-asset paths ──────────────────────────────────────
    def generate_paths(
        self,
        spot: float,
        drift: float,
        vol: float,
        maturity: float,
    ) -> np.ndarray:
        """Return array of shape (num_paths, time_steps+1)."""
        dt = maturity / self.config.time_steps
        n = self.config.num_paths
        steps = self.config.time_steps

        if self.config.antithetic:
            half = n // 2
            z = self.rng.standard_normal((half, steps))
            z = np.concatenate([z, -z], axis=0)
        else:
            z = self.rng.standard_normal((n, steps))

        log_increments = (drift - 0.5 * vol**2) * dt + vol * np.sqrt(dt) * z
        log_prices = np.cumsum(log_increments, axis=1)
        log_prices = np.insert(log_prices, 0, 0.0, axis=1)  # prepend t=0

        return spot * np.exp(log_prices)

    # ── multi-asset correlated paths ────────────────────────────
    def generate_correlated_paths(
        self,
        spots: list[float],
        drifts: list[float],
        vols: list[float],
        correlation_matrix: np.ndarray,
        maturity: float,
    ) -> np.ndarray:
        """
        Return array of shape (num_assets, num_paths, time_steps+1).
        Uses Cholesky decomposition to correlate Brownian increments.
        """
        n_assets = len(spots)
        dt = maturity / self.config.time_steps
        n = self.config.num_paths
        steps = self.config.time_steps

        L = np.linalg.cholesky(correlation_matrix)

        if self.config.antithetic:
            half = n // 2
            z_raw = self.rng.standard_normal((half, steps, n_assets))
            z_raw = np.concatenate([z_raw, -z_raw], axis=0)
        else:
            z_raw = self.rng.standard_normal((n, steps, n_assets))

        # correlate: (paths, steps, assets) @ L^T -> correlated
        z_corr = z_raw @ L.T  # broadcast over paths & steps

        all_paths = np.zeros((n_assets, n, steps + 1))
        for i in range(n_assets):
            increments = (
                (drifts[i] - 0.5 * vols[i] ** 2) * dt
                + vols[i] * np.sqrt(dt) * z_corr[:, :, i]
            )
            log_prices = np.cumsum(increments, axis=1)
            log_prices = np.insert(log_prices, 0, 0.0, axis=1)
            all_paths[i] = spots[i] * np.exp(log_prices)

        return all_paths

    # ── convergence check ───────────────────────────────────────
    @staticmethod
    def check_convergence(
        payoffs: np.ndarray, confidence: float = 0.95
    ) -> dict[str, float]:
        """Return mean, stderr, and confidence interval half-width."""
        from scipy import stats

        n = len(payoffs)
        mean = float(np.mean(payoffs))
        stderr = float(np.std(payoffs, ddof=1) / np.sqrt(n))
        z = stats.norm.ppf(0.5 + confidence / 2)
        hw = z * stderr
        return {"mean": mean, "stderr": stderr, "ci_half_width": hw}

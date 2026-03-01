"""Commodities basket pricer using Gaussian-Copula Monte Carlo.

Supports:
  - Multi-asset worst-of barrier notes
  - Correlated path generation via Cholesky decomposition
  - Convergence diagnostics
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.greeks.calculator import GreeksCalculator
from app.monte_carlo.engine import MCConfig, MonteCarloEngine
from app.pricing.base import BasePricer, PricingResult


class CommoditiesBasketPricer(BasePricer):
    """Price a worst-of barrier note on a basket of commodities."""

    def __init__(
        self,
        asset_names: list[str],
        spots: list[float],
        vols: list[float],
        drifts: list[float],
        correlation_matrix: list[list[float]],
        barriers: list[float],
        maturity: float,
        notional: float,
        risk_free_rate: float = 0.05,
        currency: str = "USD",
        mc_paths: int = 50_000,
        mc_time_steps: int = 252,
    ):
        if not (len(asset_names) == len(spots) == len(vols) == len(drifts) == len(barriers)):
            raise ValueError("All per-asset lists must have the same length")

        self.asset_names = asset_names
        self.spots = list(spots)
        self.vols = list(vols)
        self.drifts = list(drifts)
        self.corr = np.array(correlation_matrix, dtype=float)
        self.barriers = list(barriers)
        self.maturity = maturity
        self.notional = notional
        self.risk_free_rate = risk_free_rate
        self.currency = currency
        self.mc_paths = mc_paths
        self.mc_time_steps = mc_time_steps

        # alias for Greeks calculator
        self.spot = spots[0] if spots else 0.0
        self.vol = vols[0] if vols else 0.0

    # ── validation ──────────────────────────────────────────────
    def validate_inputs(self) -> list[str]:
        errors: list[str] = []
        n = len(self.asset_names)
        if self.corr.shape != (n, n):
            errors.append(f"correlation_matrix must be {n}x{n}")
        else:
            eigenvalues = np.linalg.eigvalsh(self.corr)
            if np.any(eigenvalues < -1e-8):
                errors.append("correlation_matrix is not positive semi-definite")
        if self.maturity <= 0:
            errors.append("maturity must be > 0")
        return errors

    # ── Monte Carlo ─────────────────────────────────────────────
    def _run_mc(self, mc_config: MCConfig | None = None) -> dict[str, Any]:
        cfg = mc_config or MCConfig(
            num_paths=self.mc_paths,
            time_steps=self.mc_time_steps,
        )
        engine = MonteCarloEngine(cfg)

        # (n_assets, n_paths, n_steps+1)
        all_paths = engine.generate_correlated_paths(
            self.spots, self.drifts, self.vols, self.corr, self.maturity
        )

        n_assets = len(self.asset_names)
        n_paths = cfg.num_paths

        survived = np.ones(n_paths, dtype=bool)
        for i in range(n_assets):
            min_along_path = np.min(all_paths[i], axis=1)
            survived &= min_along_path >= self.barriers[i]

        survival_rate = float(np.mean(survived))

        # Payoff: if all survive, pay notional; worst-of return if positive
        final_prices = all_paths[:, :, -1]  # (n_assets, n_paths)
        returns = (final_prices - np.array(self.spots)[:, None]) / np.array(self.spots)[:, None]
        worst_return = np.min(returns, axis=0)  # (n_paths,)

        # Worst-of payoff for survived paths
        payoffs = np.where(survived, np.maximum(worst_return, 0.0), 0.0)

        discount = math.exp(-self.risk_free_rate * self.maturity)
        fair_value = float(np.mean(payoffs)) * self.notional * discount

        convergence = MonteCarloEngine.check_convergence(payoffs * self.notional * discount)

        return {
            "fair_value": fair_value,
            "survival_rate": survival_rate,
            "convergence": convergence,
        }

    def price_monte_carlo(self) -> float:
        return self._run_mc()["fair_value"]

    # ── primary interface ───────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        mc_result = self._run_mc()

        return PricingResult(
            fair_value=mc_result["fair_value"],
            method="gaussian_copula_mc",
            currency=self.currency,
            greeks=self.calculate_greeks(),
            diagnostics={
                "survival_rate": round(mc_result["survival_rate"], 6),
                "mc_convergence": {
                    k: round(v, 4) for k, v in mc_result["convergence"].items()
                },
                "assets": self.asset_names,
            },
            methods={"monte_carlo": mc_result["fair_value"]},
        )

    # ── Greeks ──────────────────────────────────────────────────
    def calculate_greeks(self) -> dict[str, float]:
        """Per-asset delta and vega via finite differences."""
        base = self.price_monte_carlo()
        greeks: dict[str, float] = {}

        for i, name in enumerate(self.asset_names):
            # Delta: bump spot[i] by 1%
            orig_spot = self.spots[i]
            bump = orig_spot * 0.01
            self.spots[i] = orig_spot + bump
            v_up = self.price_monte_carlo()
            self.spots[i] = orig_spot
            greeks[f"delta_{name}"] = (v_up - base) / bump

            # Vega: bump vol[i] by 1 pt
            orig_vol = self.vols[i]
            self.vols[i] = orig_vol + 0.01
            v_up_v = self.price_monte_carlo()
            self.vols[i] = orig_vol
            greeks[f"vega_{name}"] = v_up_v - base

        return greeks

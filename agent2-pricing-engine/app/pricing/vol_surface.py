"""Volatility surface interpolation (Cubic Spline + SABR)."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import minimize


class VolSurfaceInterpolator:
    """Interpolate implied-vol from market delta/vol quotes.

    Supports:
      - Cubic spline (desk method)
      - SABR model calibration (VC method, arbitrage-free)
    """

    def __init__(
        self,
        deltas: list[float],
        vols: list[float],
        forward: float,
        maturity: float,
        *,
        beta: float = 0.5,
    ):
        """
        Args:
            deltas: e.g. [0.10, 0.25, 0.50, 0.75, 0.90]
            vols:   corresponding implied vols
            forward: forward price/rate
            maturity: time to expiry in years
            beta: SABR beta (usually fixed at 0.5 for FX)
        """
        if len(deltas) != len(vols):
            raise ValueError("deltas and vols must have the same length")
        self.deltas = np.array(deltas)
        self.vols = np.array(vols)
        self.forward = forward
        self.maturity = maturity
        self.beta = beta

        # pre-build cubic spline
        order = np.argsort(self.deltas)
        self._cs = CubicSpline(self.deltas[order], self.vols[order])

        # SABR params (calibrated lazily)
        self._sabr_params: dict[str, float] | None = None

    # ── Cubic Spline interpolation ──────────────────────────────
    def interpolate_cubic_spline(self, target_delta: float) -> float:
        return float(self._cs(target_delta))

    # ── SABR model ──────────────────────────────────────────────
    @staticmethod
    def _sabr_implied_vol(
        F: float,
        K: float,
        T: float,
        alpha: float,
        beta: float,
        rho: float,
        nu: float,
    ) -> float:
        """Hagan et al. (2002) SABR implied volatility formula."""
        if abs(F - K) < 1e-12:
            # ATM limit
            FK_mid = F ** (1 - beta)
            vol = (
                alpha
                / FK_mid
                * (
                    1
                    + (
                        ((1 - beta) ** 2 / 24) * alpha**2 / FK_mid**2
                        + 0.25 * rho * beta * nu * alpha / FK_mid
                        + (2 - 3 * rho**2) / 24 * nu**2
                    )
                    * T
                )
            )
            return vol

        FK = F * K
        FK_beta = FK ** ((1 - beta) / 2)
        log_FK = math.log(F / K)

        z = (nu / alpha) * FK_beta * log_FK
        x_z = math.log((math.sqrt(1 - 2 * rho * z + z**2) + z - rho) / (1 - rho))

        if abs(x_z) < 1e-12:
            x_z = 1.0

        prefix = alpha / (
            FK_beta
            * (1 + (1 - beta) ** 2 / 24 * log_FK**2 + (1 - beta) ** 4 / 1920 * log_FK**4)
        )
        correction = 1 + (
            (1 - beta) ** 2 / 24 * alpha**2 / FK_beta**2
            + 0.25 * rho * beta * nu * alpha / FK_beta
            + (2 - 3 * rho**2) / 24 * nu**2
        ) * T

        return prefix * (z / x_z) * correction

    def _delta_to_strike(self, delta: float, vol: float) -> float:
        """Convert BS delta to strike (simple approximation)."""
        from scipy.stats import norm as sp_norm

        d1 = sp_norm.ppf(delta)
        return self.forward * math.exp(
            -d1 * vol * math.sqrt(self.maturity)
            + 0.5 * vol**2 * self.maturity
        )

    def calibrate_sabr(self) -> dict[str, float]:
        """Calibrate SABR (alpha, rho, nu) to market quotes."""
        if self._sabr_params is not None:
            return self._sabr_params

        strikes = np.array(
            [self._delta_to_strike(d, v) for d, v in zip(self.deltas, self.vols)]
        )

        def objective(params: np.ndarray) -> float:
            alpha, rho, nu = params
            if alpha <= 0 or nu <= 0 or abs(rho) >= 1:
                return 1e10
            err = 0.0
            for K, market_vol in zip(strikes, self.vols):
                try:
                    model_vol = self._sabr_implied_vol(
                        self.forward, K, self.maturity, alpha, self.beta, rho, nu
                    )
                    err += (model_vol - market_vol) ** 2
                except (ValueError, ZeroDivisionError):
                    err += 1e6
            return err

        # initial guess
        x0 = np.array([float(self.vols.mean()), -0.1, 0.3])
        bounds = [(1e-6, 5.0), (-0.999, 0.999), (1e-6, 5.0)]
        result = minimize(objective, x0, method="L-BFGS-B", bounds=bounds)

        self._sabr_params = {
            "alpha": result.x[0],
            "rho": result.x[1],
            "nu": result.x[2],
            "beta": self.beta,
        }
        return self._sabr_params

    def interpolate_sabr(self, target_delta: float) -> float:
        """Interpolate using calibrated SABR model."""
        params = self.calibrate_sabr()
        # estimate vol at target delta for strike conversion
        approx_vol = self.interpolate_cubic_spline(target_delta)
        K = self._delta_to_strike(target_delta, approx_vol)

        return self._sabr_implied_vol(
            self.forward,
            K,
            self.maturity,
            params["alpha"],
            params["beta"],
            params["rho"],
            params["nu"],
        )

    # ── full surface dict ───────────────────────────────────────
    def build_surface(
        self, target_deltas: list[float] | None = None
    ) -> dict[str, Any]:
        targets = target_deltas or [0.10, 0.25, 0.50, 0.75, 0.90]
        return {
            "cubic_spline": {
                str(d): round(self.interpolate_cubic_spline(d), 6) for d in targets
            },
            "sabr": {
                str(d): round(self.interpolate_sabr(d), 6) for d in targets
            },
            "sabr_params": self.calibrate_sabr(),
        }

"""Heston Stochastic Volatility — Implied Vol Surface Generator.

Generates the implied volatility surface produced by the Heston (1993)
stochastic volatility model using Monte Carlo simulation.

Dynamics:
    dS/S = (r - q)dt + √v dW_S
    dv   = κ(θ - v)dt + ξ√v dW_v
    corr(dW_S, dW_v) = ρ

Parameters:
    v₀    - Initial instantaneous variance
    κ     - Mean reversion speed (kappa)
    θ     - Long-run variance level (theta)
    ξ     - Vol-of-vol (xi / nu)
    ρ     - Spot-vol correlation

The model produces a volatility smile endogenously. This simulator
computes option prices across a grid of strikes and tenors, then
inverts them to extract the Heston-implied vol surface.

Feller condition: 2κθ > ξ² ensures variance stays positive.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _bsm_call(S: float, K: float, T: float, sigma: float, r: float, q: float) -> float:
    """Black-Scholes call price."""
    if T <= 1e-12 or sigma <= 1e-12:
        return max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def _implied_vol_from_price(
    price: float, S: float, K: float, T: float, r: float, q: float,
) -> float:
    """Invert BSM call price to get implied vol via Brent's method."""
    intrinsic = max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0)
    if price <= intrinsic + 1e-10:
        return 0.001

    def objective(sigma: float) -> float:
        return _bsm_call(S, K, T, sigma, r, q) - price

    try:
        return brentq(objective, 0.001, 5.0, xtol=1e-8, maxiter=200)
    except (ValueError, RuntimeError):
        return 0.0


def _heston_mc_price(
    S0: float, K: float, T: float, r: float, q: float,
    v0: float, kappa: float, theta: float, xi: float, rho: float,
    n_paths: int = 20000, n_steps: int = 100, seed: int = 42,
) -> float:
    """Heston MC call price using Euler full truncation."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps

    Z1 = rng.standard_normal((n_paths, n_steps))
    Z2 = rng.standard_normal((n_paths, n_steps))
    W_S = Z1
    W_v = rho * Z1 + math.sqrt(1.0 - rho ** 2) * Z2

    log_S = np.full(n_paths, math.log(S0))
    v = np.full(n_paths, v0)

    for t in range(n_steps):
        v_pos = np.maximum(v, 0.0)
        sqrt_v = np.sqrt(v_pos)
        sqrt_dt = math.sqrt(dt)
        log_S += (r - q - 0.5 * v_pos) * dt + sqrt_v * sqrt_dt * W_S[:, t]
        v += kappa * (theta - v_pos) * dt + xi * sqrt_v * sqrt_dt * W_v[:, t]

    S_final = np.exp(log_S)
    payoffs = np.maximum(S_final - K, 0.0)
    return math.exp(-r * T) * float(np.mean(payoffs))


@ModelRegistry.register
class HestonVolSurfaceModel(BaseSimulatorModel):

    model_id = "heston_vol_surface"
    model_name = "Heston Implied Volatility Surface"
    product_type = "Volatility Surface"
    asset_class = "volsurface"

    short_description = (
        "Generate the implied vol surface from Heston stochastic vol model "
        "with Kappa, Theta, Xi (vol-of-vol), and Rho parameters"
    )
    long_description = (
        "The Heston (1993) model produces an implied volatility smile "
        "endogenously through correlated stochastic variance dynamics. "
        "This simulator prices European calls via Monte Carlo across a "
        "grid of strikes and tenors, then inverts the prices to extract "
        "the model-implied vol surface.\n\n"
        "Key parameters and their effects:\n"
        "  - v₀ (initial variance): sets the current ATM vol level\n"
        "  - κ (kappa, mean reversion): controls how fast vol reverts\n"
        "  - θ (theta, long-run variance): determines long-term vol level\n"
        "  - ξ (xi / vol-of-vol): controls smile curvature (wider wings)\n"
        "  - ρ (rho, correlation): drives the skew direction\n\n"
        "The Feller condition 2κθ > ξ² ensures variance never reaches zero."
    )

    when_to_use = [
        "Understanding how Heston parameters shape the vol surface",
        "Calibrating Heston to market-observed smile",
        "Comparing Heston vol surface vs SABR or local vol",
        "Long-dated equity options where stochastic vol matters",
        "Studying the interaction between skew (ρ) and curvature (ξ)",
    ]
    when_not_to_use = [
        "Quick indicative pricing (too slow for real-time use)",
        "When you only need ATM vol (overkill — use BSM)",
        "Short-dated options where MC convergence is poor",
        "If the surface is needed for production PDE pricing (use calibrated params directly)",
    ]
    assumptions = [
        "dS/S = (r-q)dt + √v dW_S  (geometric Brownian with stochastic vol)",
        "dv = κ(θ - v)dt + ξ√v dW_v  (CIR-type variance process)",
        "corr(dW_S, dW_v) = ρ  (constant correlation)",
        "Euler full truncation scheme for MC discretisation",
        "Implied vol extracted by BSM inversion of MC prices",
    ]
    limitations = [
        "MC convergence: surface accuracy depends on number of paths",
        "Slow for dense grids (many strike/tenor combinations)",
        "Feller condition violations require truncation (discretisation bias)",
        "5 parameters can overfit noisy market data",
        "Forward smile dynamics may not match market",
    ]

    formula_latex = (
        r"dS = (r-q)S\,dt + \sqrt{v}\,S\,dW_S \quad "
        r"dv = \kappa(\theta - v)\,dt + \xi\sqrt{v}\,dW_v \quad "
        r"\rho = \text{corr}(dW_S, dW_v)"
    )
    formula_plain = (
        "dS/S = (r-q)dt + √v dW_S,  dv = κ(θ-v)dt + ξ√v dW_v,  "
        "corr(dW_S, dW_v) = ρ"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Price (S)", "Current underlying price",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Continuous rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield", "Continuous yield",
                "float", 0.0, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "v0", "Initial Variance (v₀)", "Current instantaneous variance (σ₀² = v₀)",
                "float", 0.04, 0.001, 4.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "kappa", "Mean Reversion Speed (κ)", "Speed of variance mean reversion",
                "float", 2.0, 0.01, 20.0, 0.1,
            ),
            ParameterSpec(
                "theta", "Long-Run Variance (θ)", "Long-term variance target (σ_∞² = θ)",
                "float", 0.04, 0.001, 4.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "xi", "Vol-of-Vol (ξ)", "Volatility of variance process (also called Nu in some texts)",
                "float", 0.3, 0.01, 5.0, 0.01,
            ),
            ParameterSpec(
                "rho", "Correlation (ρ)", "Spot-vol correlation. Negative = equity skew",
                "float", -0.7, -0.999, 0.999, 0.01,
            ),
            ParameterSpec(
                "n_strikes", "Number of Strikes", "Strike grid points",
                "int", 11, 5, 31, 2,
            ),
            ParameterSpec(
                "n_tenors", "Number of Tenors", "Tenor grid points",
                "int", 5, 3, 10, 1,
            ),
            ParameterSpec(
                "max_tenor", "Max Tenor", "Maximum expiry in years",
                "float", 2.0, 0.25, 5.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "n_paths", "MC Paths", "Monte Carlo paths per point",
                "int", 20000, 5000, 200000, 5000,
            ),
            ParameterSpec(
                "seed", "Random Seed", "For reproducibility (0 = random)",
                "int", 42, 0, 999999, 1,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Equity skew (standard)": {
                "spot": 100, "r": 0.05, "q": 0.0,
                "v0": 0.04, "kappa": 2.0, "theta": 0.04,
                "xi": 0.3, "rho": -0.7,
                "n_strikes": 11, "n_tenors": 5, "max_tenor": 2.0,
                "n_paths": 20000, "seed": 42,
            },
            "High vol-of-vol (wide smile)": {
                "spot": 100, "r": 0.05, "q": 0.0,
                "v0": 0.04, "kappa": 1.5, "theta": 0.06,
                "xi": 0.6, "rho": -0.5,
                "n_strikes": 11, "n_tenors": 5, "max_tenor": 2.0,
                "n_paths": 20000, "seed": 42,
            },
            "Symmetric smile (ρ=0)": {
                "spot": 100, "r": 0.05, "q": 0.0,
                "v0": 0.04, "kappa": 2.0, "theta": 0.04,
                "xi": 0.4, "rho": 0.0,
                "n_strikes": 11, "n_tenors": 5, "max_tenor": 2.0,
                "n_paths": 20000, "seed": 42,
            },
            "Fast mean reversion": {
                "spot": 100, "r": 0.05, "q": 0.0,
                "v0": 0.09, "kappa": 5.0, "theta": 0.04,
                "xi": 0.3, "rho": -0.6,
                "n_strikes": 11, "n_tenors": 5, "max_tenor": 2.0,
                "n_paths": 20000, "seed": 42,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        p = self.params_with_defaults(params)

        S0 = float(p["spot"])
        r = float(p["r"])
        q = float(p.get("q", 0.0))
        v0 = float(p["v0"])
        kappa = float(p["kappa"])
        theta = float(p["theta"])
        xi = float(p["xi"])
        rho = float(p["rho"])
        n_K = int(p["n_strikes"])
        n_T = int(p["n_tenors"])
        max_T = float(p["max_tenor"])
        n_paths = int(p["n_paths"])
        seed = int(p.get("seed", 42))

        steps: list[CalculationStep] = []

        # Step 1: Model parameters and Feller check
        sigma0 = math.sqrt(v0)
        sigma_inf = math.sqrt(theta)
        feller = 2.0 * kappa * theta / (xi ** 2)

        steps.append(CalculationStep(
            step_number=1,
            label="Heston parameters & Feller condition",
            formula="Feller ratio = 2κθ / ξ² (must be ≥ 1)",
            substitution=(
                f"v₀ = {v0:.4f} (σ₀ = {sigma0:.4f})\n"
                f"κ (kappa) = {kappa} — mean reversion speed\n"
                f"θ (theta) = {theta:.4f} (σ_∞ = {sigma_inf:.4f}) — long-run variance\n"
                f"ξ (xi/nu) = {xi} — vol-of-vol\n"
                f"ρ (rho) = {rho} — spot-vol correlation\n"
                f"Feller = 2×{kappa}×{theta}/{xi}² = {feller:.3f} "
                f"{'≥ 1 (SATISFIED)' if feller >= 1 else '< 1 (VIOLATED — using truncation)'}\n"
                f"Half-life of mean reversion: {math.log(2)/kappa:.2f} years"
            ),
            result=round(feller, 3),
            explanation=(
                "The Feller condition ensures variance stays positive. When violated, "
                "the Euler scheme uses full truncation (v_pos = max(v, 0))."
            ),
        ))

        # Step 2: Build strike/tenor grid
        moneyness_range = [0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15, 1.20]
        if n_K <= len(moneyness_range):
            # Use symmetric moneyness grid
            step = max(1, len(moneyness_range) // n_K)
            moneyness = moneyness_range[::step][:n_K]
            # Ensure 1.0 is included
            if 1.0 not in moneyness:
                moneyness[len(moneyness) // 2] = 1.0
        else:
            moneyness = np.linspace(0.70, 1.30, n_K).tolist()

        strikes = [round(S0 * m, 2) for m in moneyness]
        tenors = np.linspace(max(0.1, max_T / n_T), max_T, n_T).tolist()

        steps.append(CalculationStep(
            step_number=2,
            label="Strike/tenor grid",
            formula="K = S × moneyness, T ∈ [T_min, T_max]",
            substitution=(
                f"Strikes ({len(strikes)}): {[f'{k:.1f}' for k in strikes]}\n"
                f"Moneyness: {[f'{m:.0%}' for m in moneyness]}\n"
                f"Tenors ({len(tenors)}): {[f'{t:.2f}y' for t in tenors]}\n"
                f"MC paths per point: {n_paths:,}\n"
                f"Total MC runs: {len(strikes) * len(tenors)}"
            ),
            result=len(strikes) * len(tenors),
            explanation="Surface grid covers ITM to OTM across multiple expiries.",
        ))

        # Step 3: Price options and extract implied vols
        surface: dict[str, dict[str, Any]] = {}
        iv_grid = np.zeros((len(tenors), len(strikes)))

        for i, T_val in enumerate(tenors):
            n_steps_mc = max(int(T_val * 100), 50)
            for j, K_val in enumerate(strikes):
                mc_price = _heston_mc_price(
                    S0, K_val, T_val, r, q,
                    v0, kappa, theta, xi, rho,
                    n_paths=n_paths, n_steps=n_steps_mc, seed=seed,
                )
                iv = _implied_vol_from_price(mc_price, S0, K_val, T_val, r, q)
                iv_grid[i, j] = iv

                key = f"T={T_val:.2f}_K={K_val:.1f}"
                surface[key] = {
                    "tenor": round(T_val, 2),
                    "strike": K_val,
                    "moneyness": round(K_val / S0, 4),
                    "mc_price": round(mc_price, 4),
                    "implied_vol": round(iv, 6),
                    "implied_vol_pct": round(iv * 100, 2),
                }

        # Extract ATM term structure
        atm_idx = len(strikes) // 2
        atm_vols = iv_grid[:, atm_idx].tolist()

        iv_valid = iv_grid[iv_grid > 0.001]
        iv_min = float(np.min(iv_valid)) if len(iv_valid) > 0 else 0.0
        iv_max = float(np.max(iv_valid)) if len(iv_valid) > 0 else 0.0
        iv_mean = float(np.mean(iv_valid)) if len(iv_valid) > 0 else 0.0

        steps.append(CalculationStep(
            step_number=3,
            label="Heston implied vol surface",
            formula="σ_impl(K,T) = BSM⁻¹(C_Heston(K,T))",
            substitution=(
                f"Computed {len(surface)} (strike, tenor) points\n"
                f"IV range: [{iv_min*100:.2f}%, {iv_max*100:.2f}%]\n"
                f"IV mean: {iv_mean*100:.2f}%\n"
                f"ATM vol at shortest tenor: {atm_vols[0]*100:.2f}%\n"
                f"ATM vol at longest tenor: {atm_vols[-1]*100:.2f}%\n"
                f"Smile width at 1Y: {(iv_grid[len(tenors)//2, 0] - iv_grid[len(tenors)//2, -1])*100:.2f}%"
                if len(tenors) > 1 else ""
            ),
            result=round(iv_mean, 6),
            explanation=(
                "Heston prices are computed via MC, then inverted through BSM "
                "to get implied vols. The resulting surface shows the smile "
                "generated by stochastic vol dynamics."
            ),
        ))

        # Step 4: Smile analysis per tenor
        smile_analytics: dict[str, dict[str, float]] = {}
        for i, T_val in enumerate(tenors):
            row = iv_grid[i, :]
            valid = row[row > 0.001]
            if len(valid) < 3:
                continue
            atm_v = row[atm_idx]
            # Risk reversal: low strike vol - high strike vol
            rr = float(row[0] - row[-1]) if len(row) >= 2 else 0.0
            # Butterfly: average wings - ATM
            bf = 0.5 * (float(row[0]) + float(row[-1])) - atm_v
            smile_analytics[f"{T_val:.2f}y"] = {
                "atm_vol": round(float(atm_v), 4),
                "risk_reversal": round(rr, 4),
                "butterfly": round(bf, 4),
                "smile_width": round(float(np.max(valid) - np.min(valid)), 4),
            }

        analytics_lines = [
            f"  T={k}  ATM={v['atm_vol']:.4f}  RR={v['risk_reversal']:+.4f}  "
            f"BF={v['butterfly']:+.4f}  Width={v['smile_width']:.4f}"
            for k, v in smile_analytics.items()
        ]

        steps.append(CalculationStep(
            step_number=4,
            label="Smile analytics per tenor",
            formula="RR = σ(K_low) - σ(K_high),  BF = 0.5*(σ_low + σ_high) - σ_ATM",
            substitution="\n".join(analytics_lines) if analytics_lines else "Insufficient data",
            result=round(float(atm_vols[0]), 6),
            explanation=(
                "Risk Reversal (RR) measures skew; positive = downside skew. "
                "Butterfly (BF) measures curvature; positive = smile convexity. "
                "Both should decrease with tenor under Heston."
            ),
        ))

        # Step 5: Parameter impact summary
        steps.append(CalculationStep(
            step_number=5,
            label="Parameter impact guide",
            formula="How each Heston parameter affects the surface",
            substitution=(
                f"κ = {kappa}: Higher κ => faster mean reversion => smile flattens at long tenors\n"
                f"θ = {theta}: Higher θ => higher long-run vol => ATM term structure slopes up\n"
                f"ξ = {xi}: Higher ξ => wider smile wings (more curvature)\n"
                f"ρ = {rho}: Negative ρ => equity-like downside skew; ρ=0 => symmetric smile\n"
                f"v₀ = {v0}: Sets the short-term vol level (σ₀ = {sigma0:.3f})"
            ),
            result=round(sigma0, 4),
            explanation=(
                "This guide helps interpret how changing each parameter "
                "will reshape the implied vol surface."
            ),
        ))

        greeks = {
            "atm_vol_short": round(atm_vols[0], 6) if atm_vols else 0.0,
            "atm_vol_long": round(atm_vols[-1], 6) if atm_vols else 0.0,
            "iv_surface_mean": round(iv_mean, 6),
            "feller_ratio": round(feller, 3),
            "sigma_0": round(sigma0, 4),
            "sigma_infinity": round(sigma_inf, 4),
        }

        return SimulatorResult(
            fair_value=round(iv_mean, 6),
            method=f"Heston MC ({n_paths:,} paths) + BSM Inversion",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "heston_params": {
                    "v0": v0, "kappa": kappa, "theta": theta,
                    "xi": xi, "rho": rho,
                },
                "feller_ratio": round(feller, 3),
                "feller_satisfied": feller >= 1,
                "iv_surface_stats": {
                    "min": round(iv_min, 6),
                    "max": round(iv_max, 6),
                    "mean": round(iv_mean, 6),
                },
                "atm_term_structure": {
                    f"{t:.2f}y": round(v, 6)
                    for t, v in zip(tenors, atm_vols)
                },
                "smile_analytics": smile_analytics,
                "surface": surface,
            },
        )

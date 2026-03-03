"""Local Volatility Surface — Dupire (1994) extraction and visualization.

Extracts the unique deterministic local volatility surface σ_local(K, T)
from market-observed European option prices using the Dupire equation:

    σ_local²(K, T) = [ ∂C/∂T + (r-q)K·∂C/∂K + qC ] / [ ½K²·∂²C/∂K² ]

This simulator focuses on the *surface itself* — constructing, visualizing,
and analyzing the local vol surface rather than pricing a single option.

The synthetic implied vol surface is parametrised as:
    σ_impl(K, T) = σ_ATM + skew * ln(K/F)/√T + curvature * [ln(K/F)]²/T

This captures equity-like skew, smile curvature, and term structure.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import norm

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _bsm_call(S: float, K: float, T: float, sigma: float, r: float, q: float) -> float:
    """Black-Scholes-Merton call price."""
    if T <= 1e-12 or sigma <= 1e-12:
        return max(S * math.exp(-q * T) - K * math.exp(-r * T), 0.0)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)


def _synthetic_implied_vol(
    K: float, T: float, S: float, r: float, q: float,
    atm_vol: float, skew: float, curvature: float,
) -> float:
    """Generate synthetic implied vol from skew parametrisation."""
    F = S * math.exp((r - q) * T)
    m = math.log(K / F) if F > 0 and K > 0 else 0.0
    sqrt_T = math.sqrt(max(T, 1e-6))
    return max(atm_vol + skew * m / sqrt_T + curvature * m ** 2 / max(T, 1e-6), 0.005)


@ModelRegistry.register
class LocalVolSurfaceModel(BaseSimulatorModel):

    model_id = "local_vol_surface"
    model_name = "Local Volatility Surface (Dupire)"
    product_type = "Volatility Surface"
    asset_class = "volsurface"

    short_description = (
        "Extract and visualize the Dupire local volatility surface from "
        "implied vol parametrisation with full surface analytics"
    )
    long_description = (
        "The Dupire (1994) local volatility model extracts a unique "
        "deterministic volatility surface σ_local(S, t) that is consistent "
        "with all observed European option prices. Unlike implied vol (which "
        "is a per-option number), local vol is the instantaneous diffusion "
        "coefficient at each (S, t) point.\n\n"
        "This simulator constructs a synthetic implied vol surface from "
        "ATM vol, skew, and curvature parameters, then applies the Dupire "
        "formula to extract σ_local(K, T) on a grid. Surface analytics "
        "include: term structure, skew profile, surface statistics, and "
        "comparison between local vol and implied vol at key points."
    )

    when_to_use = [
        "Understanding the shape of the local vol surface",
        "Comparing local vol vs implied vol across strikes and tenors",
        "As input to local vol PDE pricing of exotic options",
        "Investigating how skew and curvature translate to local vol",
        "Model validation: does the local vol surface look reasonable?",
    ]
    when_not_to_use = [
        "If you only need a single implied vol (use SABR or direct interpolation)",
        "Forward-starting options (local vol has unrealistic forward smile)",
        "When market data is too sparse for a smooth surface",
    ]
    assumptions = [
        "Implied vol surface is smooth and arbitrage-free",
        "Synthetic parametrisation: σ = σ_ATM + skew*ln(K/F)/√T + curvature*[ln(K/F)]²/T",
        "Dupire formula applied numerically with central differences",
        "No calendar arbitrage in the synthetic surface",
    ]
    limitations = [
        "Numerical derivatives amplify noise — requires smooth input",
        "Local vol surface is only as good as the implied vol input",
        "Forward smile dynamics are unrealistic under local vol",
        "Boundary effects at grid edges may produce artefacts",
    ]

    formula_latex = (
        r"\sigma_{loc}^2(K,T) = \frac{\partial C/\partial T + (r-q)K \cdot "
        r"\partial C/\partial K + qC}{\frac{1}{2}K^2 \cdot \partial^2 C / \partial K^2}"
    )
    formula_plain = (
        "σ_local²(K,T) = [∂C/∂T + (r-q)K·∂C/∂K + qC] / [½K²·∂²C/∂K²]"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Price (S)", "Current underlying price",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "atm_vol", "ATM Volatility", "At-the-money implied volatility",
                "float", 0.20, 0.01, 1.5, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "skew_slope", "Skew Slope", "Slope of vol vs log-moneyness (negative = equity skew)",
                "float", -0.10, -1.0, 1.0, 0.01,
            ),
            ParameterSpec(
                "smile_curvature", "Smile Curvature", "Quadratic curvature of the smile",
                "float", 0.05, 0.0, 1.0, 0.01,
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Continuous compounding rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield", "Continuous dividend yield",
                "float", 0.01, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "n_strikes", "Strike Grid Points", "Number of strike grid points",
                "int", 40, 10, 100, 5,
            ),
            ParameterSpec(
                "n_tenors", "Tenor Grid Points", "Number of tenor grid points",
                "int", 20, 5, 50, 5,
            ),
            ParameterSpec(
                "max_tenor", "Max Tenor", "Maximum tenor in years",
                "float", 2.0, 0.1, 10.0, 0.1, unit="years",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Equity — moderate skew": {
                "spot": 100, "atm_vol": 0.20, "skew_slope": -0.10,
                "smile_curvature": 0.05, "r": 0.05, "q": 0.01,
                "n_strikes": 40, "n_tenors": 20, "max_tenor": 2.0,
            },
            "Equity — steep skew": {
                "spot": 100, "atm_vol": 0.25, "skew_slope": -0.25,
                "smile_curvature": 0.10, "r": 0.05, "q": 0.02,
                "n_strikes": 50, "n_tenors": 25, "max_tenor": 2.0,
            },
            "Flat vol surface (BSM world)": {
                "spot": 100, "atm_vol": 0.20, "skew_slope": 0.0,
                "smile_curvature": 0.0, "r": 0.05, "q": 0.0,
                "n_strikes": 30, "n_tenors": 15, "max_tenor": 2.0,
            },
            "FX-style smile": {
                "spot": 1.0850, "atm_vol": 0.068, "skew_slope": -0.02,
                "smile_curvature": 0.08, "r": 0.05, "q": 0.03,
                "n_strikes": 40, "n_tenors": 20, "max_tenor": 1.0,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        p = self.params_with_defaults(params)

        S = float(p["spot"])
        atm_vol = float(p["atm_vol"])
        skew = float(p["skew_slope"])
        curv = float(p["smile_curvature"])
        r = float(p["r"])
        q = float(p.get("q", 0.0))
        n_K = int(p["n_strikes"])
        n_T = int(p["n_tenors"])
        max_T = float(p["max_tenor"])

        steps: list[CalculationStep] = []

        # Step 1: Build implied vol surface
        K_grid = np.linspace(S * 0.5, S * 1.5, n_K)
        T_grid = np.linspace(0.05, max_T, n_T)

        iv_matrix = np.zeros((n_T, n_K))
        for i, T_val in enumerate(T_grid):
            for j, K_val in enumerate(K_grid):
                iv_matrix[i, j] = _synthetic_implied_vol(
                    float(K_val), float(T_val), S, r, q, atm_vol, skew, curv
                )

        steps.append(CalculationStep(
            step_number=1,
            label="Synthetic implied vol surface",
            formula="σ_impl(K,T) = σ_ATM + skew·ln(K/F)/√T + curv·[ln(K/F)]²/T",
            substitution=(
                f"Grid: {n_K} strikes × {n_T} tenors\n"
                f"K range: [{float(K_grid[0]):.2f}, {float(K_grid[-1]):.2f}]\n"
                f"T range: [{float(T_grid[0]):.2f}, {float(T_grid[-1]):.2f}] years\n"
                f"σ_ATM = {atm_vol:.4f}, skew = {skew}, curvature = {curv}\n"
                f"IV range: [{float(np.min(iv_matrix)):.4f}, {float(np.max(iv_matrix)):.4f}]"
            ),
            result=round(atm_vol, 6),
            explanation=(
                "A parametric implied vol surface is constructed first. "
                "The Dupire formula will then extract local vol from this surface."
            ),
        ))

        # Step 2: Compute call price surface
        C = np.zeros((n_T, n_K))
        for i, T_val in enumerate(T_grid):
            for j, K_val in enumerate(K_grid):
                C[i, j] = _bsm_call(S, float(K_val), float(T_val), iv_matrix[i, j], r, q)

        steps.append(CalculationStep(
            step_number=2,
            label="Call price surface",
            formula="C(K,T) = BSM(S, K, T, σ_impl(K,T), r, q)",
            substitution=(
                f"Computed {n_K * n_T} call prices\n"
                f"C range: [{float(np.min(C)):.4f}, {float(np.max(C)):.4f}]"
            ),
            result=round(float(np.mean(C)), 4),
            explanation="Call prices computed from BSM with the synthetic implied vol.",
        ))

        # Step 3: Apply Dupire formula
        dK = float(K_grid[1] - K_grid[0]) if n_K > 1 else 1.0
        dT = float(T_grid[1] - T_grid[0]) if n_T > 1 else 0.01

        lv_matrix = np.zeros((n_T, n_K))
        for i in range(1, n_T - 1):
            for j in range(1, n_K - 1):
                dC_dT = (C[i + 1, j] - C[i - 1, j]) / (2.0 * dT)
                dC_dK = (C[i, j + 1] - C[i, j - 1]) / (2.0 * dK)
                d2C_dK2 = (C[i, j + 1] - 2.0 * C[i, j] + C[i, j - 1]) / (dK ** 2)

                K_val = float(K_grid[j])
                numer = dC_dT + (r - q) * K_val * dC_dK + q * C[i, j]
                denom = 0.5 * K_val ** 2 * d2C_dK2

                if denom > 1e-12 and numer > 0:
                    lv_matrix[i, j] = math.sqrt(numer / denom)
                else:
                    lv_matrix[i, j] = iv_matrix[i, j]  # fallback

        # Fill boundaries
        lv_matrix[0, :] = lv_matrix[1, :]
        lv_matrix[-1, :] = lv_matrix[-2, :]
        lv_matrix[:, 0] = lv_matrix[:, 1]
        lv_matrix[:, -1] = lv_matrix[:, -2]

        lv_valid = lv_matrix[lv_matrix > 0.005]
        lv_min = float(np.min(lv_valid)) if len(lv_valid) > 0 else 0.0
        lv_max = float(np.max(lv_valid)) if len(lv_valid) > 0 else 0.0
        lv_mean = float(np.mean(lv_valid)) if len(lv_valid) > 0 else 0.0

        steps.append(CalculationStep(
            step_number=3,
            label="Dupire local vol extraction",
            formula=self.formula_plain,
            substitution=(
                f"Computed {(n_T - 2) * (n_K - 2)} interior local vol points\n"
                f"Local vol range: [{lv_min:.4f}, {lv_max:.4f}]\n"
                f"Local vol mean: {lv_mean:.4f}\n"
                f"ATM implied vol: {atm_vol:.4f}\n"
                f"Ratio (mean LV / ATM IV): {lv_mean / atm_vol:.4f}" if atm_vol > 0 else ""
            ),
            result=round(lv_mean, 6),
            explanation=(
                "The Dupire formula extracts local vol via numerical derivatives "
                "of the call price surface. Local vol ≈ implied vol when the "
                "surface is flat; with skew, local vol is higher on the downside."
            ),
        ))

        # Step 4: Surface comparison at key points
        key_moneyness = [0.80, 0.90, 0.95, 1.00, 1.05, 1.10, 1.20]
        # Pick a mid-tenor for the comparison
        T_mid_idx = n_T // 2
        T_mid = float(T_grid[T_mid_idx])

        comparison_table = {}
        for m in key_moneyness:
            K_val = S * m
            K_idx = int(np.searchsorted(K_grid, K_val))
            K_idx = min(max(K_idx, 1), n_K - 2)

            iv_val = iv_matrix[T_mid_idx, K_idx]
            lv_val = lv_matrix[T_mid_idx, K_idx]
            ratio = lv_val / iv_val if iv_val > 0 else 0.0

            comparison_table[f"{m:.0%}"] = {
                "strike": round(float(K_grid[K_idx]), 2),
                "implied_vol": round(float(iv_val), 4),
                "local_vol": round(float(lv_val), 4),
                "ratio_lv_iv": round(ratio, 4),
            }

        comp_lines = [
            f"  {k:>6s}  K={v['strike']:>8.2f}  IV={v['implied_vol']:.4f}  "
            f"LV={v['local_vol']:.4f}  LV/IV={v['ratio_lv_iv']:.4f}"
            for k, v in comparison_table.items()
        ]

        steps.append(CalculationStep(
            step_number=4,
            label=f"Surface comparison at T={T_mid:.2f}y",
            formula="Local Vol vs Implied Vol at key moneyness levels",
            substitution="\n".join(comp_lines),
            result=round(lv_mean, 6),
            explanation=(
                "Under negative skew, local vol exceeds implied vol for low strikes "
                "(downside) and is lower for high strikes. The ratio LV/IV reveals "
                "how the Dupire surface amplifies the skew structure."
            ),
        ))

        # Step 5: Term structure of ATM local vol
        atm_K_idx = int(np.searchsorted(K_grid, S))
        atm_K_idx = min(max(atm_K_idx, 1), n_K - 2)

        term_structure = {}
        for i, T_val in enumerate(T_grid):
            term_structure[f"{float(T_val):.2f}y"] = {
                "tenor": round(float(T_val), 2),
                "atm_local_vol": round(float(lv_matrix[i, atm_K_idx]), 4),
                "atm_implied_vol": round(float(iv_matrix[i, atm_K_idx]), 4),
            }

        ts_lines = [
            f"  T={v['tenor']:.2f}y  ATM_LV={v['atm_local_vol']:.4f}  "
            f"ATM_IV={v['atm_implied_vol']:.4f}"
            for v in list(term_structure.values())[::max(n_T // 5, 1)]
        ]

        steps.append(CalculationStep(
            step_number=5,
            label="ATM local vol term structure",
            formula="σ_local(ATM, T) across tenors",
            substitution="\n".join(ts_lines),
            result=round(float(lv_matrix[n_T // 2, atm_K_idx]), 4),
            explanation=(
                "The ATM local vol term structure shows how instantaneous "
                "vol varies with expiry. Under local vol, this is driven entirely "
                "by the implied vol term structure input."
            ),
        ))

        greeks = {
            "atm_local_vol": round(float(lv_matrix[T_mid_idx, atm_K_idx]), 6),
            "atm_implied_vol": round(atm_vol, 6),
            "local_vol_min": round(lv_min, 6),
            "local_vol_max": round(lv_max, 6),
            "local_vol_mean": round(lv_mean, 6),
        }

        return SimulatorResult(
            fair_value=round(lv_mean, 6),
            method="Dupire Local Volatility Surface Extraction",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "surface_params": {
                    "spot": S, "atm_vol": atm_vol,
                    "skew": skew, "curvature": curv,
                    "r": r, "q": q,
                },
                "grid_size": {"n_strikes": n_K, "n_tenors": n_T},
                "local_vol_stats": {
                    "min": round(lv_min, 6),
                    "max": round(lv_max, 6),
                    "mean": round(lv_mean, 6),
                },
                "comparison_at_mid_tenor": comparison_table,
                "term_structure": term_structure,
            },
        )

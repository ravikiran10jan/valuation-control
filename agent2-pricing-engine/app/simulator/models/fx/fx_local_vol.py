"""FX Local Volatility — Dupire model for FX options.

Adapts the Dupire local vol framework for FX markets.  The local vol surface
σ_local(S, t) is extracted from FX implied vols using the Dupire equation
with domestic/foreign rates replacing r and q.

This is the industry standard for pricing FX barrier options, TARFs, and
other path-dependent FX exotics consistently with the vanilla smile.
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


def _gk_call(S, K, T, sigma, r_d, r_f):
    """Garman-Kohlhagen call price."""
    if T <= 1e-12 or sigma <= 1e-12:
        return max(S * math.exp(-r_f * T) - K * math.exp(-r_d * T), 0)
    d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * math.exp(-r_f * T) * norm.cdf(d1) - K * math.exp(-r_d * T) * norm.cdf(d2)


def _fx_implied_vol(K, T, atm_vol, rr_25d, bf_25d, S, r_d, r_f):
    """Synthetic FX implied vol from ATM, 25-delta risk reversal, and butterfly.

    Standard FX vol quoting:
      σ(Δ) = ATM + 0.5·BF + RR·(Δ - 0.5)    (simplified 2-param smile)

    Mapped to moneyness:
      σ(K, T) = atm + rr_25d·m/√T + bf_25d·m²/T
    where m = ln(K/F), F = S·exp((r_d - r_f)·T)
    """
    F = S * math.exp((r_d - r_f) * T)
    m = math.log(K / F)
    sqrt_T = math.sqrt(max(T, 1e-6))
    return max(atm_vol + rr_25d * m / sqrt_T + bf_25d * m**2 / max(T, 1e-6), 0.01)


def _fx_dupire_local_vol(S, K_grid, T_grid, atm_vol, rr_25d, bf_25d, r_d, r_f):
    """Compute FX Dupire local vol surface."""
    nT = len(T_grid)
    nK = len(K_grid)
    local_vol = np.zeros((nT, nK))

    dK = K_grid[1] - K_grid[0] if nK > 1 else S * 0.01
    dT = T_grid[1] - T_grid[0] if nT > 1 else 0.01

    C = np.zeros((nT, nK))
    for i, T_val in enumerate(T_grid):
        for j, K_val in enumerate(K_grid):
            iv = _fx_implied_vol(K_val, T_val, atm_vol, rr_25d, bf_25d, S, r_d, r_f)
            C[i, j] = _gk_call(S, K_val, max(T_val, 1e-6), iv, r_d, r_f)

    for i in range(1, nT - 1):
        for j in range(1, nK - 1):
            dC_dT = (C[i + 1, j] - C[i - 1, j]) / (2 * dT)
            dC_dK = (C[i, j + 1] - C[i, j - 1]) / (2 * dK)
            d2C_dK2 = (C[i, j + 1] - 2 * C[i, j] + C[i, j - 1]) / (dK**2)

            K_val = K_grid[j]
            numerator = dC_dT + (r_d - r_f) * K_val * dC_dK + r_f * C[i, j]
            denominator = 0.5 * K_val**2 * d2C_dK2

            if denominator > 1e-12 and numerator > 0:
                local_vol[i, j] = math.sqrt(numerator / denominator)
            else:
                local_vol[i, j] = _fx_implied_vol(K_val, T_grid[i], atm_vol, rr_25d, bf_25d, S, r_d, r_f)

    local_vol[0, :] = local_vol[1, :]
    local_vol[-1, :] = local_vol[-2, :]
    local_vol[:, 0] = local_vol[:, 1]
    local_vol[:, -1] = local_vol[:, -2]

    return K_grid, T_grid, local_vol


@ModelRegistry.register
class FXLocalVolModel(BaseSimulatorModel):

    model_id = "fx_local_vol"
    model_name = "FX Local Volatility (Dupire)"
    product_type = "European FX Option (Smile-Consistent)"
    asset_class = "fx"

    short_description = (
        "FX Dupire local vol surface for smile-consistent exotic pricing"
    )
    long_description = (
        "The Dupire local volatility model adapted for FX markets.  Extracts "
        "σ_local(S, t) from the FX implied vol surface parametrised by ATM vol, "
        "25-delta risk reversal (skew), and 25-delta butterfly (curvature) — "
        "the standard FX vol quoting convention.  The local vol surface is then "
        "used for pricing FX exotics (barriers, TARFs, accumulators) consistently "
        "with the vanilla market.  This is the industry standard approach for "
        "FX exotic pricing at major banks."
    )

    when_to_use = [
        "FX barrier options — local vol at the barrier drives the price",
        "TARF / accumulator pricing (with MC on top of local vol)",
        "Ensuring exotic prices are consistent with the vanilla FX smile",
        "FX smile analysis: extracting and visualising the local vol surface",
        "As the local component in FX LSV (Local-Stochastic Vol) hybrids",
    ]
    when_not_to_use = [
        "When only ATM vol is available (need a full smile for Dupire)",
        "Forward-starting FX options (Dupire forward smile is unrealistic)",
        "When stochastic rates matter (long-dated cross-currency swaps)",
        "G10 vanillas where GK is sufficient",
    ]
    assumptions = [
        "FX rate follows dS = (r_d - r_f)S dt + σ_local(S,t)S dW",
        "σ_local is deterministic — extracted via the Dupire equation",
        "FX vol surface parametrised by ATM, 25Δ RR, and 25Δ BF",
        "Constant domestic and foreign rates",
    ]
    limitations = [
        "Forward smile dynamics are unrealistic (same as equity local vol)",
        "Sensitive to noise in the input vol surface",
        "No vol-of-vol — cannot capture FX vol clustering",
        "Simplified vol parametrisation (full surface needs SABR or SVI)",
    ]

    formula_latex = (
        r"\sigma_{loc}^2(K,T) = \frac{\partial C/\partial T + (r_d-r_f)K \cdot \partial C/\partial K + r_f C}"
        r"{\frac{1}{2}K^2 \cdot \partial^2 C / \partial K^2}"
    )
    formula_plain = (
        "σ_local²(K,T) = [∂C/∂T + (r_d-r_f)K·∂C/∂K + r_f·C] / [½K²·∂²C/∂K²]"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec("spot", "Spot FX Rate (S)", "DOM/FOR", "float", 1.0850, 0.0001, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("strike", "Strike (K)", "Option strike", "float", 1.0850, 0.0001, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("maturity", "Time to Expiry (T)", "Years", "float", 0.25, 0.01, 10.0, 0.01, unit="years"),
            ParameterSpec("atm_vol", "ATM Volatility", "At-the-money FX implied vol", "float", 0.078, 0.01, 1.0, 0.001, unit="decimal"),
            ParameterSpec("rr_25d", "25Δ Risk Reversal", "Call vol - Put vol at 25Δ (negative = put skew)", "float", -0.005, -0.2, 0.2, 0.001),
            ParameterSpec("bf_25d", "25Δ Butterfly", "Curvature: (Call vol + Put vol)/2 - ATM vol", "float", 0.003, 0.0, 0.2, 0.001),
            ParameterSpec("r_d", "Domestic Rate (r_d)", "Domestic risk-free rate", "float", 0.053, -0.1, 0.5, 0.001, unit="decimal"),
            ParameterSpec("r_f", "Foreign Rate (r_f)", "Foreign risk-free rate", "float", 0.035, -0.1, 0.5, 0.001, unit="decimal"),
            ParameterSpec("option_type", "Option Type", "Call or Put", "select", "call", options=["call", "put"]),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "EUR/USD ATM with smile": {
                "spot": 1.0850, "strike": 1.0850, "maturity": 0.25,
                "atm_vol": 0.078, "rr_25d": -0.005, "bf_25d": 0.003,
                "r_d": 0.053, "r_f": 0.035, "option_type": "call",
            },
            "EUR/USD OTM Put (steep skew)": {
                "spot": 1.0850, "strike": 1.0500, "maturity": 0.25,
                "atm_vol": 0.078, "rr_25d": -0.010, "bf_25d": 0.005,
                "r_d": 0.053, "r_f": 0.035, "option_type": "put",
            },
            "USD/BRL EM smile": {
                "spot": 5.10, "strike": 5.30, "maturity": 0.25,
                "atm_vol": 0.15, "rr_25d": -0.030, "bf_25d": 0.015,
                "r_d": 0.125, "r_f": 0.053, "option_type": "put",
            },
            "Flat vol (GK equivalent)": {
                "spot": 1.0850, "strike": 1.0850, "maturity": 0.25,
                "atm_vol": 0.078, "rr_25d": 0.0, "bf_25d": 0.0,
                "r_d": 0.053, "r_f": 0.035, "option_type": "call",
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        atm_vol = float(params["atm_vol"])
        rr_25d = float(params["rr_25d"])
        bf_25d = float(params["bf_25d"])
        r_d = float(params["r_d"])
        r_f = float(params["r_f"])
        opt_type = params.get("option_type", "call").lower()
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []

        # Step 1: implied vol at strike
        iv_at_K = _fx_implied_vol(K, T, atm_vol, rr_25d, bf_25d, S, r_d, r_f)
        F = S * math.exp((r_d - r_f) * T)
        m = math.log(K / F)

        steps.append(CalculationStep(
            step_number=1,
            label="FX implied vol at strike",
            formula=r"\sigma(K,T) = \sigma_{ATM} + RR_{25} \cdot \frac{m}{\sqrt{T}} + BF_{25} \cdot \frac{m^2}{T}",
            substitution=(
                f"F = {S}·e^({r_d}-{r_f})×{T} = {F:.6f}\n"
                f"m = ln({K}/{F:.6f}) = {m:.6f}\n"
                f"σ({K},{T}) = {iv_at_K:.6f}"
            ),
            result=round(iv_at_K, 6),
            explanation=(
                "FX vol parametrised by ATM, 25Δ risk reversal (skew), and "
                "25Δ butterfly (curvature) — the standard FX vol quoting convention."
            ),
        ))

        # Step 2: local vol surface
        K_grid = np.linspace(S * 0.7, S * 1.3, 50)
        T_grid = np.linspace(0.05, max(T * 1.5, 0.5), 30)

        K_arr, T_arr, lv_matrix = _fx_dupire_local_vol(
            S, K_grid, T_grid, atm_vol, rr_25d, bf_25d, r_d, r_f
        )

        T_idx = min(max(np.searchsorted(T_arr, T), 1), len(T_arr) - 2)
        K_idx = min(max(np.searchsorted(K_arr, K), 1), len(K_arr) - 2)
        lv_at_KT = lv_matrix[T_idx, K_idx]

        steps.append(CalculationStep(
            step_number=2,
            label="FX Dupire local vol extraction",
            formula=self.formula_plain,
            substitution=(
                f"Grid: {len(K_arr)}×{len(T_arr)} (K×T)\n"
                f"σ_local({K}, {T}) = {lv_at_KT:.6f}\n"
                f"σ_implied({K}, {T}) = {iv_at_K:.6f}"
            ),
            result=round(lv_at_KT, 6),
            explanation="Dupire formula with FX rates: r_d replaces r, r_f replaces q.",
        ))

        # Step 3: price with implied vol at strike
        price_smile = _gk_call(S, K, T, iv_at_K, r_d, r_f)
        price_flat = _gk_call(S, K, T, atm_vol, r_d, r_f)
        if not is_call:
            parity = K * math.exp(-r_d * T) - S * math.exp(-r_f * T)
            price_smile += parity
            price_flat += parity

        price = price_smile

        steps.append(CalculationStep(
            step_number=3,
            label="Price with FX smile",
            formula=r"C = GK(S, K, T, \sigma(K,T), r_d, r_f)",
            substitution=(
                f"With smile σ({K},{T}) = {iv_at_K:.4f}: {price:.6f}\n"
                f"With flat ATM σ = {atm_vol}: {price_flat:.6f}\n"
                f"Smile effect: {price - price_flat:+.6f}"
            ),
            result=round(price, 6),
            explanation="For vanillas, pricing with the smile-adjusted vol equals local vol PDE pricing.",
        ))

        # Step 4: Greeks
        ds = S * 0.001
        def _prc(s):
            iv = _fx_implied_vol(K, T, atm_vol, rr_25d, bf_25d, s, r_d, r_f)
            c = _gk_call(s, K, T, iv, r_d, r_f)
            if not is_call:
                c += K * math.exp(-r_d * T) - s * math.exp(-r_f * T)
            return c

        delta = (_prc(S + ds) - _prc(S - ds)) / (2 * ds)
        gamma = (_prc(S + ds) - 2 * price + _prc(S - ds)) / ds**2

        greeks = {"delta": round(delta, 6), "gamma": round(gamma, 6)}

        steps.append(CalculationStep(
            step_number=4,
            label="FX Greeks (with smile)",
            formula=r"\Delta_{smile} \text{ includes skew delta contribution}",
            substitution=f"Delta = {delta:.6f}, Gamma = {gamma:.6f}",
            result=round(delta, 6),
            explanation="FX delta under local vol includes the 'skew delta' from the smile.",
        ))

        # Surface snippet for diagnostics
        sample_strikes = [S * m for m in [0.85, 0.925, 1.0, 1.075, 1.15]]
        surface_snippet = {}
        for k in sample_strikes:
            iv = _fx_implied_vol(k, T, atm_vol, rr_25d, bf_25d, S, r_d, r_f)
            lv_k_idx = min(max(np.searchsorted(K_arr, k), 1), len(K_arr) - 2)
            lv_val = lv_matrix[T_idx, lv_k_idx]
            surface_snippet[f"K={k:.4f}"] = {
                "implied_vol": round(iv, 4),
                "local_vol": round(float(lv_val), 4),
            }

        return SimulatorResult(
            fair_value=round(price, 6),
            method="FX Dupire Local Vol (smile-consistent)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "implied_vol_at_strike": round(iv_at_K, 6),
                "local_vol_at_strike": round(lv_at_KT, 6),
                "atm_vol": round(atm_vol, 4),
                "forward_rate": round(F, 6),
                "log_moneyness": round(m, 6),
                "smile_effect": round(price - price_flat, 6),
                "gk_flat_price": round(price_flat, 6),
                "vol_surface_snippet": surface_snippet,
            },
        )

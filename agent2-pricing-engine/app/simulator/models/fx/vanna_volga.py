"""Vanna-Volga method for FX option smile pricing.

The market-standard FX smile adjustment: uses three quoted volatilities
(25Δ put, ATM, 25Δ call) to compute smile-consistent option prices as
a correction to the flat-vol Garman-Kohlhagen value.
"""

from __future__ import annotations

import math
from typing import Any

from scipy.stats import norm
from scipy.optimize import brentq

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _gk_price(S: float, K: float, T: float, sigma: float,
              rd: float, rf: float, opt: str) -> float:
    """Garman-Kohlhagen closed-form price."""
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (rd - rf + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    df_f = math.exp(-rf * T)
    df_d = math.exp(-rd * T)
    if opt == "call":
        return S * df_f * norm.cdf(d1) - K * df_d * norm.cdf(d2)
    else:
        return K * df_d * norm.cdf(-d2) - S * df_f * norm.cdf(-d1)


def _gk_vega(S: float, K: float, T: float, sigma: float,
             rd: float, rf: float) -> float:
    """GK vega (dPrice/dSigma)."""
    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (rd - rf + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    return S * math.exp(-rf * T) * norm.pdf(d1) * sqrt_T


def _strike_from_delta(S: float, T: float, sigma: float, rd: float,
                       rf: float, delta_target: float, opt: str) -> float:
    """Invert GK delta to find strike for a given delta (spot delta)."""
    df_f = math.exp(-rf * T)
    sqrt_T = math.sqrt(T)

    def obj(K: float) -> float:
        d1 = (math.log(S / K) + (rd - rf + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        if opt == "call":
            return df_f * norm.cdf(d1) - delta_target
        else:
            return -df_f * norm.cdf(-d1) - delta_target

    # Search range for strike
    lo = S * 0.3
    hi = S * 3.0
    try:
        return brentq(obj, lo, hi, xtol=1e-10)
    except ValueError:
        # Fallback: wider range
        return brentq(obj, S * 0.01, S * 10.0, xtol=1e-10)


@ModelRegistry.register
class VannaVolgaModel(BaseSimulatorModel):

    model_id = "vanna_volga"
    model_name = "Vanna-Volga"
    product_type = "FX Vanilla Option (Smile-Adjusted)"
    asset_class = "fx"

    short_description = (
        "FX smile pricing from 25Δ risk reversal, butterfly, and ATM volatility"
    )
    long_description = (
        "The Vanna-Volga method is the industry-standard approach for pricing "
        "FX options consistently with the volatility smile. It starts with "
        "three market-quoted volatilities: ATM (σ_ATM), 25-delta risk reversal "
        "(RR = σ_25ΔC - σ_25ΔP), and 25-delta butterfly (BF = (σ_25ΔC + σ_25ΔP)/2 "
        "- σ_ATM). From these, the 25Δ call and put vols are derived, and a "
        "smile correction is computed as the cost of hedging the Vanna and Volga "
        "risk of the target option using the three benchmark options. The correction "
        "is added to the flat-vol GK price."
    )

    when_to_use = [
        "FX vanilla options where smile/skew matters",
        "When you have ATM, 25Δ RR, and 25Δ BF quotes (standard FX market data)",
        "First-order smile adjustment that is fast and transparent",
        "Liquid G10 pairs where market quotes are reliable",
    ]
    when_not_to_use = [
        "Exotic or barrier options — need full local/stochastic vol model",
        "When you need an arbitrage-free vol surface (VV can violate in wings)",
        "EM pairs with sparse or unreliable smile quotes",
        "Very short-dated options where smile extrapolation is unreliable",
        "When 10Δ quotes are also needed — VV is a 3-point method",
    ]
    assumptions = [
        "Three liquid market quotes: ATM, 25Δ RR, 25Δ BF",
        "Hedging cost interpretation: smile correction = cost of Vanna/Volga replication",
        "GK model as the base (log-normal dynamics, constant rates)",
        "Spot delta convention (can be adapted to forward delta)",
        "Linear interpolation of the smile in delta space",
    ]
    limitations = [
        "Only uses three vol points — cannot capture complex smile shapes",
        "Can produce negative implied vols in extreme wings",
        "Not arbitrage-free — possible butterfly spread violations far OTM",
        "Smile dynamics are not modeled (static snapshot)",
        "Less accurate for very long-dated or very short-dated options",
    ]

    formula_latex = (
        r"C_{VV}(K) = C_{GK}(K, \sigma_{ATM}) + "
        r"\sum_{i=1}^{3} x_i \left[C_{MKT}(K_i) - C_{GK}(K_i, \sigma_{ATM})\right]"
    )
    formula_plain = (
        "C_vv(K) = C_gk(K, σ_ATM) + x1·[C_mkt(K1) - C_gk(K1)] "
        "+ x2·[C_mkt(K2) - C_gk(K2)] + x3·[C_mkt(K3) - C_gk(K3)],  "
        "where x_i are weights from Vanna/Volga hedging ratios."
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Rate (S)", "Spot FX rate (domestic per foreign)",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "strike", "Strike (K)", "Target option strike",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Time to expiration in years",
                "float", 0.25, 0.001, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "r_dom", "Domestic Rate (r_d)", "Domestic risk-free rate",
                "float", 0.053, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_for", "Foreign Rate (r_f)", "Foreign risk-free rate",
                "float", 0.035, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "vol_atm", "ATM Vol (σ_ATM)", "At-the-money implied volatility",
                "float", 0.08, 0.001, 5.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "rr_25d", "25Δ Risk Reversal", "σ_25ΔC - σ_25ΔP (positive = call skew)",
                "float", -0.005, -0.5, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "bf_25d", "25Δ Butterfly", "(σ_25ΔC + σ_25ΔP)/2 - σ_ATM (smile curvature)",
                "float", 0.003, 0.0, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call or Put",
                "select", "call", options=["call", "put"],
            ),
            ParameterSpec(
                "notional", "Notional", "Foreign currency notional",
                "float", 1_000_000.0, 1.0, None, 1000.0, unit="FOR",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "EURUSD 3M ATM Call": {
                "spot": 1.0800, "strike": 1.0800, "maturity": 0.25,
                "r_dom": 0.053, "r_for": 0.035,
                "vol_atm": 0.08, "rr_25d": -0.005, "bf_25d": 0.003,
                "option_type": "call", "notional": 1_000_000.0,
            },
            "EURUSD 3M 25Δ Put": {
                "spot": 1.0800, "strike": 1.0650, "maturity": 0.25,
                "r_dom": 0.053, "r_for": 0.035,
                "vol_atm": 0.08, "rr_25d": -0.005, "bf_25d": 0.003,
                "option_type": "put", "notional": 1_000_000.0,
            },
            "USDJPY 6M OTM Call": {
                "spot": 155.50, "strike": 160.00, "maturity": 0.5,
                "r_dom": 0.001, "r_for": 0.053,
                "vol_atm": 0.10, "rr_25d": 0.01, "bf_25d": 0.004,
                "option_type": "call", "notional": 10_000_000.0,
            },
            "GBPUSD 1Y ATM Put": {
                "spot": 1.2700, "strike": 1.2700, "maturity": 1.0,
                "r_dom": 0.053, "r_for": 0.05,
                "vol_atm": 0.09, "rr_25d": -0.008, "bf_25d": 0.005,
                "option_type": "put", "notional": 5_000_000.0,
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        rd = float(params["r_dom"])
        rf = float(params["r_for"])
        sigma_atm = float(params["vol_atm"])
        rr = float(params["rr_25d"])
        bf = float(params["bf_25d"])
        opt_type = params.get("option_type", "call").lower()
        notional = float(params.get("notional", 1_000_000.0))

        steps: list[CalculationStep] = []
        sqrt_T = math.sqrt(T)

        # Step 1: derive 25Δ call and put vols
        sigma_25c = sigma_atm + bf + 0.5 * rr
        sigma_25p = sigma_atm + bf - 0.5 * rr
        steps.append(CalculationStep(
            step_number=1,
            label="Derive 25Δ vols from RR and BF",
            formula=(
                r"\sigma_{25\Delta C} = \sigma_{ATM} + BF + \frac{RR}{2}"
                r",\quad \sigma_{25\Delta P} = \sigma_{ATM} + BF - \frac{RR}{2}"
            ),
            substitution=(
                f"σ_25ΔC = {sigma_atm} + {bf} + {rr}/2 = {sigma_25c:.6f},  "
                f"σ_25ΔP = {sigma_atm} + {bf} - {rr}/2 = {sigma_25p:.6f}"
            ),
            result=round(sigma_25c, 6),
            explanation=(
                "Risk reversal measures skew (call vol - put vol). Butterfly measures "
                "curvature (average wing vol - ATM vol). Together they define the "
                "3-point smile."
            ),
        ))

        # Step 2: find the 3 benchmark strikes
        K1 = _strike_from_delta(S, T, sigma_25p, rd, rf, -0.25, "put")
        K2_atm = S * math.exp((rd - rf + 0.5 * sigma_atm**2) * T)  # ATM forward delta-neutral
        K3 = _strike_from_delta(S, T, sigma_25c, rd, rf, 0.25, "call")
        steps.append(CalculationStep(
            step_number=2,
            label="Benchmark strikes (K1, K2, K3)",
            formula=(
                r"K_1 = K_{25\Delta P},\quad K_2 = K_{ATM\Delta N},"
                r"\quad K_3 = K_{25\Delta C}"
            ),
            substitution=(
                f"K1 (25ΔP) = {K1:.4f},  K2 (ATM) = {K2_atm:.4f},  "
                f"K3 (25ΔC) = {K3:.4f}"
            ),
            result=round(K2_atm, 4),
            explanation=(
                "Three benchmark strikes derived from the delta convention. "
                "ATM is delta-neutral straddle strike."
            ),
        ))

        # Step 3: GK prices and vegas at benchmark strikes
        C1_atm = _gk_price(S, K1, T, sigma_atm, rd, rf, "put")
        C1_mkt = _gk_price(S, K1, T, sigma_25p, rd, rf, "put")
        C2_atm = _gk_price(S, K2_atm, T, sigma_atm, rd, rf, "call")
        C2_mkt = C2_atm  # ATM vol = ATM vol, no correction at ATM
        C3_atm = _gk_price(S, K3, T, sigma_atm, rd, rf, "call")
        C3_mkt = _gk_price(S, K3, T, sigma_25c, rd, rf, "call")

        cost1 = C1_mkt - C1_atm
        cost2 = C2_mkt - C2_atm
        cost3 = C3_mkt - C3_atm

        steps.append(CalculationStep(
            step_number=3,
            label="Smile costs at benchmarks",
            formula=(
                r"\text{cost}_i = C_{MKT}(K_i, \sigma_i) - C_{GK}(K_i, \sigma_{ATM})"
            ),
            substitution=(
                f"cost₁ (25ΔP) = {cost1:.6f},  "
                f"cost₂ (ATM) = {cost2:.6f},  "
                f"cost₃ (25ΔC) = {cost3:.6f}"
            ),
            result=round(cost1, 6),
            explanation=(
                "The cost at each benchmark is the difference between the market "
                "price (at the smile vol) and the flat-vol GK price."
            ),
        ))

        # Step 4: Vanna and Volga of the target option
        d1_K = (math.log(S / K) + (rd - rf + 0.5 * sigma_atm**2) * T) / (sigma_atm * sqrt_T)
        d2_K = d1_K - sigma_atm * sqrt_T
        vega_K = _gk_vega(S, K, T, sigma_atm, rd, rf)
        vanna_K = vega_K / S * (1 - d1_K / (sigma_atm * sqrt_T))
        volga_K = vega_K * d1_K * d2_K / sigma_atm

        # Same for benchmarks
        d1_1 = (math.log(S / K1) + (rd - rf + 0.5 * sigma_atm**2) * T) / (sigma_atm * sqrt_T)
        d2_1 = d1_1 - sigma_atm * sqrt_T
        vega_1 = _gk_vega(S, K1, T, sigma_atm, rd, rf)
        vanna_1 = vega_1 / S * (1 - d1_1 / (sigma_atm * sqrt_T))
        volga_1 = vega_1 * d1_1 * d2_1 / sigma_atm

        d1_2 = (math.log(S / K2_atm) + (rd - rf + 0.5 * sigma_atm**2) * T) / (sigma_atm * sqrt_T)
        d2_2 = d1_2 - sigma_atm * sqrt_T
        vega_2 = _gk_vega(S, K2_atm, T, sigma_atm, rd, rf)
        vanna_2 = vega_2 / S * (1 - d1_2 / (sigma_atm * sqrt_T))
        volga_2 = vega_2 * d1_2 * d2_2 / sigma_atm

        d1_3 = (math.log(S / K3) + (rd - rf + 0.5 * sigma_atm**2) * T) / (sigma_atm * sqrt_T)
        d2_3 = d1_3 - sigma_atm * sqrt_T
        vega_3 = _gk_vega(S, K3, T, sigma_atm, rd, rf)
        vanna_3 = vega_3 / S * (1 - d1_3 / (sigma_atm * sqrt_T))
        volga_3 = vega_3 * d1_3 * d2_3 / sigma_atm

        steps.append(CalculationStep(
            step_number=4,
            label="Vanna and Volga",
            formula=(
                r"\text{Vanna} = \frac{\partial^2 C}{\partial S \partial \sigma},"
                r"\quad \text{Volga} = \frac{\partial^2 C}{\partial \sigma^2}"
            ),
            substitution=(
                f"Target: Vanna={vanna_K:.6f}, Volga={volga_K:.6f}.  "
                f"K1: Vanna={vanna_1:.6f}, Volga={volga_1:.6f}.  "
                f"K3: Vanna={vanna_3:.6f}, Volga={volga_3:.6f}"
            ),
            result=round(volga_K, 6),
            explanation=(
                "Vanna measures sensitivity to simultaneous spot and vol moves. "
                "Volga measures sensitivity to vol-of-vol. These are the risks "
                "that the Vanna-Volga method hedges."
            ),
        ))

        # Step 5: Solve for weights x1, x2, x3
        # Using Vega, Vanna, Volga matching
        # [vega_1  vega_2  vega_3 ] [x1]   [vega_K ]
        # [vanna_1 vanna_2 vanna_3] [x2] = [vanna_K]
        # [volga_1 volga_2 volga_3] [x3]   [volga_K]
        A = [
            [vega_1, vega_2, vega_3],
            [vanna_1, vanna_2, vanna_3],
            [volga_1, volga_2, volga_3],
        ]
        b = [vega_K, vanna_K, volga_K]

        # Solve 3x3 system
        det = (A[0][0] * (A[1][1]*A[2][2] - A[1][2]*A[2][1])
             - A[0][1] * (A[1][0]*A[2][2] - A[1][2]*A[2][0])
             + A[0][2] * (A[1][0]*A[2][1] - A[1][1]*A[2][0]))

        if abs(det) < 1e-15:
            # Fallback: simplified 2-point (Vanna + Volga only, x2=0)
            x1 = vanna_K / max(vanna_1, 1e-15) if abs(vanna_1) > 1e-15 else 0.0
            x2 = 0.0
            x3 = volga_K / max(volga_3, 1e-15) if abs(volga_3) > 1e-15 else 0.0
        else:
            # Cramer's rule
            def det3(m):
                return (m[0][0]*(m[1][1]*m[2][2]-m[1][2]*m[2][1])
                      - m[0][1]*(m[1][0]*m[2][2]-m[1][2]*m[2][0])
                      + m[0][2]*(m[1][0]*m[2][1]-m[1][1]*m[2][0]))

            A1 = [[b[0], A[0][1], A[0][2]],
                   [b[1], A[1][1], A[1][2]],
                   [b[2], A[2][1], A[2][2]]]
            A2 = [[A[0][0], b[0], A[0][2]],
                   [A[1][0], b[1], A[1][2]],
                   [A[2][0], b[2], A[2][2]]]
            A3 = [[A[0][0], A[0][1], b[0]],
                   [A[1][0], A[1][1], b[1]],
                   [A[2][0], A[2][1], b[2]]]
            x1 = det3(A1) / det
            x2 = det3(A2) / det
            x3 = det3(A3) / det

        steps.append(CalculationStep(
            step_number=5,
            label="Hedge weights",
            formula=(
                r"\text{Solve } \begin{pmatrix} v_1 & v_2 & v_3 \\ "
                r"va_1 & va_2 & va_3 \\ vo_1 & vo_2 & vo_3 \end{pmatrix}"
                r"\begin{pmatrix} x_1 \\ x_2 \\ x_3 \end{pmatrix} = "
                r"\begin{pmatrix} v_K \\ va_K \\ vo_K \end{pmatrix}"
            ),
            substitution=f"x₁ = {x1:.6f},  x₂ = {x2:.6f},  x₃ = {x3:.6f}",
            result=round(x1, 6),
            explanation=(
                "Weights represent the portfolio of benchmark options that "
                "replicates the Vega, Vanna, and Volga of the target option."
            ),
        ))

        # Step 6: VV correction and final price
        correction = x1 * cost1 + x2 * cost2 + x3 * cost3
        base_price = _gk_price(S, K, T, sigma_atm, rd, rf, opt_type)
        vv_price = base_price + correction

        steps.append(CalculationStep(
            step_number=6,
            label="Vanna-Volga price",
            formula=(
                r"C_{VV} = C_{GK}(K, \sigma_{ATM}) + "
                r"\sum_{i} x_i \cdot \text{cost}_i"
            ),
            substitution=(
                f"C_VV = {base_price:.6f} + ({x1:.4f}×{cost1:.6f} + "
                f"{x2:.4f}×{cost2:.6f} + {x3:.4f}×{cost3:.6f}) "
                f"= {base_price:.6f} + {correction:.6f} = {vv_price:.6f}"
            ),
            result=round(vv_price, 6),
            explanation=(
                "The final price is the flat-vol GK price plus the VV smile "
                "correction. The correction represents the cost of hedging "
                "Vanna and Volga exposure using the three benchmark options."
            ),
        ))

        # Step 7: implied vol
        try:
            implied_vol = brentq(
                lambda sig: _gk_price(S, K, T, sig, rd, rf, opt_type) - vv_price,
                0.001, 5.0, xtol=1e-8,
            )
        except (ValueError, RuntimeError):
            implied_vol = sigma_atm

        steps.append(CalculationStep(
            step_number=7,
            label="Implied volatility (smile-adjusted)",
            formula=r"\sigma_{impl}: C_{GK}(K, \sigma_{impl}) = C_{VV}(K)",
            substitution=(
                f"Solve for σ: GK(K={K}, σ) = {vv_price:.6f} → σ = {implied_vol:.6f} "
                f"({implied_vol * 100:.3f}%),  ATM vol = {sigma_atm * 100:.3f}%,  "
                f"Smile adj = {(implied_vol - sigma_atm) * 100:.3f}%"
            ),
            result=round(implied_vol, 6),
            explanation=(
                "The implied vol that recovers the VV price via GK. This is the "
                "smile-adjusted vol at this specific strike."
            ),
        ))

        # Greeks at the VV implied vol
        d1 = (math.log(S / K) + (rd - rf + 0.5 * implied_vol**2) * T) / (implied_vol * sqrt_T)
        d2 = d1 - implied_vol * sqrt_T
        nd1 = norm.pdf(d1)
        Nd1 = norm.cdf(d1)
        Nmd1 = norm.cdf(-d1)
        Nd2 = norm.cdf(d2)
        Nmd2 = norm.cdf(-d2)
        df_f = math.exp(-rf * T)
        df_d = math.exp(-rd * T)

        if opt_type == "call":
            delta = df_f * Nd1
            rho_dom = K * T * df_d * Nd2
            rho_for = -S * T * df_f * Nd1
        else:
            delta = -df_f * Nmd1
            rho_dom = -K * T * df_d * Nmd2
            rho_for = S * T * df_f * Nmd1

        gamma = df_f * nd1 / (S * implied_vol * sqrt_T)
        vega = S * df_f * nd1 * sqrt_T

        premium = vv_price * notional

        return SimulatorResult(
            fair_value=round(vv_price, 6),
            method="Vanna-Volga (3-point smile adjustment)",
            greeks={
                "delta_spot": round(delta, 6),
                "gamma": round(gamma, 6),
                "vega": round(vega / 100, 6),
                "rho_domestic": round(rho_dom / 100, 6),
                "rho_foreign": round(rho_for / 100, 6),
            },
            calculation_steps=steps,
            diagnostics={
                "gk_flat_price": round(base_price, 6),
                "vv_correction": round(correction, 6),
                "vv_price": round(vv_price, 6),
                "implied_vol": round(implied_vol, 6),
                "implied_vol_pct": round(implied_vol * 100, 3),
                "smile_adj_bps": round((implied_vol - sigma_atm) * 10000, 1),
                "sigma_25d_call": round(sigma_25c, 6),
                "sigma_25d_put": round(sigma_25p, 6),
                "K_25d_put": round(K1, 4),
                "K_atm": round(K2_atm, 4),
                "K_25d_call": round(K3, 4),
                "weights": {"x1": round(x1, 6), "x2": round(x2, 6), "x3": round(x3, 6)},
                "total_premium": round(premium, 2),
            },
        )

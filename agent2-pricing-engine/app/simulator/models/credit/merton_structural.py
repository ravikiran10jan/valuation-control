"""Merton Structural Model — equity-to-credit linkage.

The Merton (1974) model treats a firm's equity as a call option on its
assets:  E = V·N(d₁) - D·e^{-rT}·N(d₂)

where:
  V = total firm value (assets)
  D = face value of debt (default barrier)
  σ_V = asset volatility
  T = debt maturity

Key outputs:
  - Default probability: P(V_T < D) = N(-d₂)
  - Credit spread: s = -(1/T)·ln(D·e^{-rT} / (D·e^{-rT} - Put))
  - Distance to default (DD): how many σ's away from the default barrier

The model is solved iteratively: given equity value E and equity vol σ_E,
infer the unobservable asset value V and asset vol σ_V.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import fsolve
from scipy.stats import norm

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _bsm_d1_d2(V: float, D: float, T: float, sigma_V: float, r: float):
    """Compute d1 and d2 for the Merton model."""
    d1 = (math.log(V / D) + (r + 0.5 * sigma_V**2) * T) / (sigma_V * math.sqrt(T))
    d2 = d1 - sigma_V * math.sqrt(T)
    return d1, d2


def _equity_from_assets(V: float, D: float, T: float, sigma_V: float, r: float) -> float:
    """E = V·N(d1) - D·exp(-rT)·N(d2)."""
    d1, d2 = _bsm_d1_d2(V, D, T, sigma_V, r)
    return V * norm.cdf(d1) - D * math.exp(-r * T) * norm.cdf(d2)


def _equity_vol_from_assets(V: float, D: float, T: float, sigma_V: float,
                            r: float, E: float) -> float:
    """σ_E = σ_V · (V/E) · N(d1)."""
    d1, _ = _bsm_d1_d2(V, D, T, sigma_V, r)
    return sigma_V * (V / E) * norm.cdf(d1)


def _solve_merton(E: float, sigma_E: float, D: float, T: float, r: float):
    """Solve for (V, σ_V) given (E, σ_E, D, T, r).

    Two equations:
      E = V·N(d1) - D·exp(-rT)·N(d2)
      σ_E·E = σ_V·V·N(d1)
    """
    def system(x):
        V, sigma_V = x
        if V <= 0 or sigma_V <= 0:
            return [1e10, 1e10]
        d1, d2 = _bsm_d1_d2(V, D, T, sigma_V, r)
        eq1 = V * norm.cdf(d1) - D * math.exp(-r * T) * norm.cdf(d2) - E
        eq2 = sigma_V * V * norm.cdf(d1) - sigma_E * E
        return [eq1, eq2]

    # Initial guess
    V0 = E + D * math.exp(-r * T)
    sigma_V0 = sigma_E * E / V0

    solution = fsolve(system, [V0, sigma_V0], full_output=True)
    V_sol, sigma_V_sol = solution[0]
    info = solution[1]
    converged = solution[2] == 1

    return max(V_sol, 1e-6), max(sigma_V_sol, 1e-6), converged


@ModelRegistry.register
class MertonStructuralModel(BaseSimulatorModel):

    model_id = "merton_structural"
    model_name = "Merton Structural Model"
    product_type = "Default Probability / Credit Spread"
    asset_class = "credit"

    short_description = (
        "Estimate default probability from equity price using the Merton model"
    )
    long_description = (
        "The Merton (1974) structural model treats equity as a call option "
        "on the firm's assets. Given observable equity value and equity "
        "volatility, the model infers the unobservable asset value and asset "
        "volatility, then computes the distance to default, default probability, "
        "and implied credit spread. This establishes the fundamental linkage "
        "between equity and credit markets. The KMV/Moody's EDF model is a "
        "commercial extension of this approach."
    )

    when_to_use = [
        "Estimating default probability from equity market data",
        "Understanding the equity-credit linkage (CDS vs equity vol)",
        "Quick credit assessment when CDS market is illiquid",
        "Academic/educational illustration of structural credit models",
        "Computing distance-to-default (DD) for credit screening",
    ]
    when_not_to_use = [
        "Pricing tradeable credit instruments (use reduced-form / ISDA model)",
        "When firm value is not observable (always — but we back it out from equity)",
        "Short-term default prediction (Merton underestimates short-term default)",
        "Complex capital structures (multiple debt classes, convertibles)",
        "When leverage is near zero (model becomes insensitive)",
    ]
    assumptions = [
        "Firm value follows GBM: dV = μV dt + σ_V V dW",
        "Single class of zero-coupon debt maturing at T",
        "Default can only occur at debt maturity T",
        "No taxes, no bankruptcy costs, no dividends",
        "Equity = call option on firm value with strike = debt face value",
    ]
    limitations = [
        "Default only at maturity — cannot predict early default (use first-passage models)",
        "Single debt class — real firms have complex capital structures",
        "Underestimates short-term default probabilities",
        "Asset value and vol are inferred — circular reasoning possible",
        "Constant vol assumption for firm value process",
    ]

    formula_latex = (
        r"E = V \cdot N(d_1) - D \cdot e^{-rT} \cdot N(d_2)"
        r"\qquad DD = \frac{\ln(V/D) + (\mu - \sigma_V^2/2)T}{\sigma_V\sqrt{T}}"
    )
    formula_plain = (
        "E = V·N(d1) - D·exp(-rT)·N(d2), "
        "DD = [ln(V/D) + (r - σ²_V/2)T] / (σ_V√T), "
        "PD = N(-DD)"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "equity_value", "Equity Value (E)",
                "Market cap = share price × shares outstanding", "float",
                50.0, 0.1, None, 0.1, unit="$B",
            ),
            ParameterSpec(
                "equity_vol", "Equity Volatility (σ_E)",
                "Annualized equity volatility", "float",
                0.30, 0.05, 2.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "debt_face", "Debt Face Value (D)",
                "Total debt obligations (book value)", "float",
                40.0, 0.1, None, 0.1, unit="$B",
            ),
            ParameterSpec(
                "maturity", "Debt Maturity (T)",
                "Weighted average maturity of debt", "float",
                1.0, 0.25, 10.0, 0.25, unit="years",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)", "Continuous rate", "float",
                0.05, 0.0, 0.20, 0.001, unit="decimal",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Investment Grade (low leverage)": {
                "equity_value": 80.0, "equity_vol": 0.25,
                "debt_face": 30.0, "maturity": 1.0, "r": 0.05,
            },
            "BBB (moderate leverage)": {
                "equity_value": 50.0, "equity_vol": 0.30,
                "debt_face": 40.0, "maturity": 1.0, "r": 0.05,
            },
            "High Yield (high leverage)": {
                "equity_value": 20.0, "equity_vol": 0.50,
                "debt_face": 50.0, "maturity": 1.0, "r": 0.05,
            },
            "Near Default (very high leverage)": {
                "equity_value": 5.0, "equity_vol": 0.80,
                "debt_face": 50.0, "maturity": 1.0, "r": 0.05,
            },
            "5-Year horizon": {
                "equity_value": 50.0, "equity_vol": 0.30,
                "debt_face": 40.0, "maturity": 5.0, "r": 0.05,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        E = float(params["equity_value"])
        sigma_E = float(params["equity_vol"])
        D = float(params["debt_face"])
        T = float(params["maturity"])
        r = float(params["r"])

        steps: list[CalculationStep] = []

        # Step 1: Initial observation
        leverage = D / (E + D)
        steps.append(CalculationStep(
            step_number=1,
            label="Observed data",
            formula=r"\text{Leverage} = \frac{D}{E + D}",
            substitution=(
                f"Equity (E) = ${E:.1f}B, Equity Vol = {sigma_E:.1%}\n"
                f"Debt (D) = ${D:.1f}B\n"
                f"Leverage = {D:.1f}/({E:.1f}+{D:.1f}) = {leverage:.1%}\n"
                f"Debt maturity = {T}Y, r = {r:.1%}"
            ),
            result=round(leverage, 4),
            explanation=(
                "Higher leverage and higher equity vol both increase default probability."
            ),
        ))

        # Step 2: Solve for asset value and asset vol
        V, sigma_V, converged = _solve_merton(E, sigma_E, D, T, r)

        steps.append(CalculationStep(
            step_number=2,
            label="Solve for asset value and vol",
            formula=r"E = V N(d_1) - D e^{-rT} N(d_2), \quad \sigma_E E = \sigma_V V N(d_1)",
            substitution=(
                f"Asset value (V) = ${V:.4f}B\n"
                f"Asset volatility (σ_V) = {sigma_V:.4%}\n"
                f"Converged: {converged}\n"
                f"Check: E_model = {_equity_from_assets(V, D, T, sigma_V, r):.4f}B (should ≈ {E:.1f})"
            ),
            result=round(V, 4),
            explanation=(
                "Two nonlinear equations are solved simultaneously: "
                "the BSM equity formula and the equity-asset vol relationship. "
                "Asset vol is always lower than equity vol (leverage amplifies)."
            ),
        ))

        # Step 3: Distance to Default
        d1, d2 = _bsm_d1_d2(V, D, T, sigma_V, r)
        DD = d2  # distance to default = d2 (under risk-neutral measure)
        DD_physical = (math.log(V / D) + (r - 0.5 * sigma_V**2) * T) / (sigma_V * math.sqrt(T))

        steps.append(CalculationStep(
            step_number=3,
            label="Distance to Default (DD)",
            formula=r"DD = \frac{\ln(V/D) + (r - \sigma_V^2/2)T}{\sigma_V \sqrt{T}} = d_2",
            substitution=(
                f"ln(V/D) = ln({V:.4f}/{D:.1f}) = {math.log(V / D):.6f}\n"
                f"d₁ = {d1:.4f}, d₂ = {d2:.4f}\n"
                f"DD (risk-neutral) = {DD:.4f}\n"
                f"DD (physical, same μ=r) = {DD_physical:.4f}"
            ),
            result=round(DD, 4),
            explanation=(
                "DD measures how many standard deviations the firm is from the "
                "default barrier. DD > 4 is very safe, DD < 1 is distressed."
            ),
        ))

        # Step 4: Default probability
        PD = norm.cdf(-DD)  # risk-neutral default probability

        # Rating approximation
        if PD < 0.0004:
            rating_approx = "~AAA/AA"
        elif PD < 0.002:
            rating_approx = "~A"
        elif PD < 0.005:
            rating_approx = "~BBB"
        elif PD < 0.02:
            rating_approx = "~BB"
        elif PD < 0.05:
            rating_approx = "~B"
        elif PD < 0.15:
            rating_approx = "~CCC"
        else:
            rating_approx = "~CC/D"

        steps.append(CalculationStep(
            step_number=4,
            label="Default probability",
            formula=r"PD = N(-DD) = N(-d_2)",
            substitution=(
                f"PD (risk-neutral, {T}Y) = N(-{DD:.4f}) = {PD:.6f} = {PD:.4%}\n"
                f"Approximate rating: {rating_approx}"
            ),
            result=round(PD, 6),
            explanation=(
                "The probability that V_T < D under the risk-neutral measure. "
                "This is the probability driving CDS spreads, not real-world default rates."
            ),
        ))

        # Step 5: Implied credit spread
        # Debt value = D·e^{-rT} - Put(V, D, T, σ_V, r)
        # Put = D·e^{-rT}·N(-d2) - V·N(-d1)
        put_value = D * math.exp(-r * T) * norm.cdf(-d2) - V * norm.cdf(-d1)
        debt_value = D * math.exp(-r * T) - put_value
        if debt_value > 0 and D > 0:
            ytm = -math.log(debt_value / D) / T
            credit_spread = (ytm - r) * 10000  # in bps
        else:
            credit_spread = 0
            ytm = r

        steps.append(CalculationStep(
            step_number=5,
            label="Implied credit spread",
            formula=r"s = -\frac{1}{T}\ln\!\left(\frac{D_{market}}{D}\right) - r",
            substitution=(
                f"Risk-free debt value: ${D * math.exp(-r * T):.4f}B\n"
                f"Put (default option): ${put_value:.4f}B\n"
                f"Risky debt value: ${debt_value:.4f}B\n"
                f"YTM: {ytm:.4%}, Credit spread: {credit_spread:.1f} bps"
            ),
            result=round(credit_spread, 1),
            explanation=(
                "The credit spread compensates bondholders for the embedded "
                "put option (default risk). Higher leverage → higher put value → wider spread."
            ),
        ))

        # Step 6: Sensitivity analysis
        # DV01: spread change per 1% equity move
        dE = E * 0.01
        V_up, sv_up, _ = _solve_merton(E + dE, sigma_E, D, T, r)
        V_dn, sv_dn, _ = _solve_merton(max(E - dE, 0.1), sigma_E, D, T, r)
        _, d2_up = _bsm_d1_d2(V_up, D, T, sv_up, r)
        _, d2_dn = _bsm_d1_d2(V_dn, D, T, sv_dn, r)
        PD_up = norm.cdf(-d2_up)
        PD_dn = norm.cdf(-d2_dn)
        PD_sensitivity = (PD_up - PD_dn) / (2 * dE / E)  # per 1% equity change

        steps.append(CalculationStep(
            step_number=6,
            label="Equity-credit sensitivity",
            formula=r"\frac{\partial PD}{\partial E} \cdot \frac{E}{PD}",
            substitution=(
                f"PD if equity +1%: {PD_up:.6f}\n"
                f"PD if equity -1%: {PD_dn:.6f}\n"
                f"ΔPD per 1% equity move: {PD_sensitivity:.6f}\n"
                f"(negative means equity ↑ → PD ↓, as expected)"
            ),
            result=round(PD_sensitivity, 6),
            explanation=(
                "This captures the equity-credit linkage: how much does default "
                "probability change for a 1% equity move. Used for CDS-equity basis trading."
            ),
        ))

        greeks = {
            "default_prob": round(PD, 6),
            "distance_to_default": round(DD, 4),
            "credit_spread_bps": round(credit_spread, 1),
            "pd_equity_sensitivity": round(PD_sensitivity, 6),
        }

        return SimulatorResult(
            fair_value=round(credit_spread, 1),
            method="Merton Structural Model (1974)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "asset_value": round(V, 4),
                "asset_vol": round(sigma_V, 6),
                "leverage": round(leverage, 4),
                "d1": round(d1, 4),
                "d2": round(d2, 4),
                "distance_to_default": round(DD, 4),
                "default_probability": round(PD, 6),
                "default_probability_pct": round(PD * 100, 4),
                "credit_spread_bps": round(credit_spread, 1),
                "approx_rating": rating_approx,
                "put_value": round(put_value, 4),
                "debt_value": round(debt_value, 4),
                "solver_converged": converged,
            },
        )

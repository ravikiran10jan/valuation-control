"""Constant Elasticity of Variance (CEV) model.

The CEV model (Cox, 1975) generalises BSM by allowing local volatility to
depend on the spot level:  σ_local(S) = σ₀ · S^(β-1).

    dS = (r-q) S dt + σ₀ S^β dW

β = 1  → BSM  (log-normal)
β < 1  → leverage effect  (vol rises when spot falls)
β = 0  → normal / Bachelier model

Pricing uses the non-central chi-squared distribution (Schroder, 1989).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.stats import ncx2, norm

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _bsm_price(S: float, K: float, T: float, sigma: float,
                r: float, q: float, is_call: bool) -> float:
    """BSM closed-form for internal comparison."""
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return (S * math.exp(-q * T) * norm.cdf(d1)
                - K * math.exp(-r * T) * norm.cdf(d2))
    return (K * math.exp(-r * T) * norm.cdf(-d2)
            - S * math.exp(-q * T) * norm.cdf(-d1))


def _cev_call_price(S: float, K: float, T: float, sigma: float,
                    beta: float, r: float, q: float) -> float:
    """CEV European call price via non-central chi-squared.

    Convention:  dS = (r-q)S dt + σ₀ S^β dW,  β < 1 → leverage.
    Uses Schroder (1989) formulation.
    """
    if K <= 0:
        return S * math.exp(-q * T) - K * math.exp(-r * T)

    mu = r - q
    n = 1.0 - beta          # n > 0 for β < 1

    F = S * math.exp(mu * T)

    # Effective variance parameter
    if abs(mu * n) > 1e-12:
        kappa = 2 * mu / (sigma**2 * (math.exp(2 * mu * n * T) - 1))
    else:
        kappa = 1.0 / (sigma**2 * n * T)

    x = kappa * F ** (2 * n)
    y = kappa * K ** (2 * n)

    # Degrees-of-freedom parameter
    df_c = 1.0 / n + 1     # = (1 + n) / n
    # For the call:
    # C = S exp(-qT) [1 - χ²(y; 2(df_c+1), 2x)] - K exp(-rT) χ²(x; 2 df_c - 2, 2y)
    # Simplified: df_upper = 2/n + 2,  df_lower = 2/n

    df_upper = 2.0 / n + 2.0
    df_lower = 2.0 / n

    term1 = S * math.exp(-q * T) * (1.0 - ncx2.cdf(2 * y, df_upper, 2 * x))
    term2 = K * math.exp(-r * T) * ncx2.cdf(2 * x, df_lower, 2 * y)

    return term1 - term2


@ModelRegistry.register
class CEVModel(BaseSimulatorModel):

    model_id = "cev"
    model_name = "Constant Elasticity of Variance (CEV)"
    product_type = "European Vanilla Option"
    asset_class = "equity"

    short_description = (
        "Option pricing with spot-dependent volatility (leverage effect)"
    )
    long_description = (
        "The CEV model (Cox, 1975) allows local volatility to depend on the "
        "spot price level: σ(S) = σ₀ · S^(β-1). When β < 1, volatility increases "
        "as the spot decreases — the 'leverage effect' observed in equity markets. "
        "The model nests BSM (β=1) and the normal/Bachelier model (β=0). Pricing "
        "uses the non-central chi-squared distribution (Schroder, 1989). The single "
        "extra parameter β controls the entire skew shape, making CEV a parsimonious "
        "alternative to BSM for capturing equity skew."
    )

    when_to_use = [
        "When you observe the leverage effect (vol rises when spot falls)",
        "Equity options where skew is important but stochastic vol is overkill",
        "Comparing model risk: how much does the β parameter change the price?",
        "LEAPS and long-dated options where leverage compounds",
        "As a middle ground between BSM (no skew) and Heston (stochastic vol)",
    ]
    when_not_to_use = [
        "When β = 1 — reduces to BSM with no advantage",
        "Products requiring smile dynamics (term structure of skew)",
        "Path-dependent exotics without an efficient CEV extension",
        "When vol-of-vol matters (use Heston or SABR instead)",
        "Very low spot values with β < 1 (numerical instability as S→0)",
        "FX markets where the smile is symmetric (CEV gives one-sided skew only)",
    ]
    assumptions = [
        "Local volatility is a deterministic function of spot: σ(S) = σ₀ · S^(β-1)",
        "Single parameter β controls the entire skew",
        "No jumps in the underlying",
        "Constant risk-free rate and dividend yield",
        "European exercise only (closed-form); American requires PDE/tree",
    ]
    limitations = [
        "Only generates downward-sloping skew (β<1) or upward (β>1) — no smile",
        "Cannot fit both wings of the vol surface simultaneously",
        "Forward smile dynamics are unrealistic (same criticism as local vol)",
        "No vol-of-vol — cannot price vol-sensitive products (cliquets, VIX options)",
    ]

    formula_latex = (
        r"C = S e^{-qT}\!\left[1 - \chi^2\!\left(2y;\,\tfrac{2}{n}+2,\,2x\right)\right]"
        r" - K e^{-rT} \chi^2\!\left(2x;\,\tfrac{2}{n},\,2y\right)"
    )
    formula_plain = (
        "C = S·exp(-qT)·[1 - χ²(2y; 2/n+2, 2x)] - K·exp(-rT)·χ²(2x; 2/n, 2y), "
        "where n=1-β, x=κF^(2n), y=κK^(2n), F=S·exp(μT)"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Price (S)", "Current price of the underlying",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "strike", "Strike Price (K)", "Option strike price",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Time to expiration in years",
                "float", 1.0, 0.001, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "sigma", "CEV Volatility (σ₀)",
                "Volatility parameter (units depend on β)",
                "float", 0.20, 0.001, 5.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "beta", "Elasticity (β)",
                "CEV exponent: 1=BSM, <1=leverage effect, 0=normal",
                "float", 0.5, 0.0, 2.0, 0.05,
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)", "Continuous compounding risk-free rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield (q)", "Continuous dividend yield",
                "float", 0.0, 0.0, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call or Put",
                "select", "call", options=["call", "put"],
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Equity with leverage (β=0.5)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "beta": 0.5, "r": 0.05, "q": 0.0,
                "option_type": "call",
            },
            "Mild leverage (β=0.75)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "beta": 0.75, "r": 0.05, "q": 0.0,
                "option_type": "call",
            },
            "BSM equivalent (β=1)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "beta": 1.0, "r": 0.05, "q": 0.0,
                "option_type": "call",
            },
            "Strong leverage (β=0.25)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "beta": 0.25, "r": 0.05, "q": 0.0,
                "option_type": "call",
            },
            "LEAPS with leverage": {
                "spot": 150.0, "strike": 100.0, "maturity": 2.0,
                "sigma": 0.30, "beta": 0.5, "r": 0.05, "q": 0.01,
                "option_type": "call",
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        beta = float(params["beta"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        opt_type = params.get("option_type", "call").lower()
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []
        mu = r - q

        # ── Step 1: check β and identify model regime ──
        if abs(beta - 1.0) < 1e-10:
            steps.append(CalculationStep(
                step_number=1,
                label="Model regime",
                formula=r"\beta = 1 \Rightarrow \text{BSM (log-normal)}",
                substitution=f"β = {beta} → Reduces to standard Black-Scholes",
                result=beta,
                explanation="When β=1, the CEV model is identical to BSM.",
            ))
            bsm_price = _bsm_price(S, K, T, sigma, r, q, is_call)
            return SimulatorResult(
                fair_value=round(bsm_price, 4),
                method="CEV (β=1 → BSM fallback)",
                greeks=self._finite_diff_greeks(params),
                calculation_steps=steps,
                diagnostics={"beta": beta, "regime": "BSM_equivalent"},
            )

        n = 1.0 - beta
        steps.append(CalculationStep(
            step_number=1,
            label="Model regime",
            formula=r"n = 1 - \beta",
            substitution=(
                f"β = {beta}, n = 1 - {beta} = {n:.4f}. "
                f"{'Leverage effect (vol ↑ as spot ↓)' if beta < 1 else 'Inverse leverage'}"
            ),
            result=round(n, 4),
            explanation=(
                "n determines the shape of the non-central chi-squared distribution. "
                "For β<1 (leverage), volatility increases as the stock drops."
            ),
        ))

        # ── Step 2: forward price ──
        F = S * math.exp(mu * T)
        steps.append(CalculationStep(
            step_number=2,
            label="Forward price",
            formula=r"F = S \cdot e^{(r-q)T}",
            substitution=f"F = {S} × e^({r}-{q})×{T} = {S} × {math.exp(mu * T):.6f} = {F:.4f}",
            result=round(F, 4),
            explanation="The forward price under continuous dividend yield.",
        ))

        # ── Step 3: effective variance κ ──
        if abs(mu * n) > 1e-12:
            exp_term = math.exp(2 * mu * n * T)
            kappa = 2 * mu / (sigma**2 * (exp_term - 1))
            kappa_formula = r"\kappa = \frac{2\mu}{\sigma_0^2 (e^{2\mu n T} - 1)}"
            kappa_sub = (
                f"κ = 2×{mu} / ({sigma}² × (e^(2×{mu}×{n:.4f}×{T}) - 1))"
                f" = {2 * mu:.6f} / ({sigma**2:.6f} × {exp_term - 1:.6f})"
            )
        else:
            kappa = 1.0 / (sigma**2 * n * T)
            kappa_formula = r"\kappa = \frac{1}{\sigma_0^2 \cdot n \cdot T}"
            kappa_sub = f"κ = 1 / ({sigma}² × {n:.4f} × {T}) [μ≈0 limit]"

        steps.append(CalculationStep(
            step_number=3,
            label="Effective variance parameter (κ)",
            formula=kappa_formula,
            substitution=f"{kappa_sub} = {kappa:.6f}",
            result=round(kappa, 6),
            explanation="κ scales the transformed spot and strike into chi-squared space.",
        ))

        # ── Step 4: transformed variables x, y ──
        x = kappa * F ** (2 * n)
        y = kappa * K ** (2 * n)
        steps.append(CalculationStep(
            step_number=4,
            label="Transformed variables x, y",
            formula=r"x = \kappa \cdot F^{2n}, \quad y = \kappa \cdot K^{2n}",
            substitution=(
                f"x = {kappa:.6f} × {F:.4f}^{2 * n:.4f} = {kappa:.6f} × {F ** (2 * n):.6f} = {x:.6f}\n"
                f"y = {kappa:.6f} × {K:.4f}^{2 * n:.4f} = {kappa:.6f} × {K ** (2 * n):.6f} = {y:.6f}"
            ),
            result=round(x, 6),
            explanation="x and y are the transformed forward and strike in chi-squared space.",
        ))

        # ── Step 5: degrees of freedom ──
        df_upper = 2.0 / n + 2.0
        df_lower = 2.0 / n
        steps.append(CalculationStep(
            step_number=5,
            label="Degrees of freedom",
            formula=r"df_1 = \frac{2}{n} + 2, \quad df_2 = \frac{2}{n}",
            substitution=f"df₁ = 2/{n:.4f} + 2 = {df_upper:.4f},  df₂ = 2/{n:.4f} = {df_lower:.4f}",
            result=round(df_upper, 4),
            explanation="Degrees of freedom for the two non-central chi-squared terms.",
        ))

        # ── Step 6: chi-squared CDF evaluations ──
        cdf1 = ncx2.cdf(2 * y, df_upper, 2 * x)
        cdf2 = ncx2.cdf(2 * x, df_lower, 2 * y)
        steps.append(CalculationStep(
            step_number=6,
            label="Non-central χ² CDF values",
            formula=(
                r"\chi^2(2y;\,df_1,\,2x) \text{ and } \chi^2(2x;\,df_2,\,2y)"
            ),
            substitution=(
                f"χ²({2 * y:.4f}; df={df_upper:.4f}, nc={2 * x:.4f}) = {cdf1:.6f}\n"
                f"χ²({2 * x:.4f}; df={df_lower:.4f}, nc={2 * y:.4f}) = {cdf2:.6f}"
            ),
            result=round(cdf1, 6),
            explanation=(
                "The non-central chi-squared CDF captures the probability "
                "distribution of the transformed asset price under CEV dynamics."
            ),
        ))

        # ── Step 7: call price ──
        call_price = (
            S * math.exp(-q * T) * (1.0 - cdf1)
            - K * math.exp(-r * T) * cdf2
        )
        t1 = S * math.exp(-q * T) * (1.0 - cdf1)
        t2 = K * math.exp(-r * T) * cdf2

        steps.append(CalculationStep(
            step_number=7,
            label="CEV call price",
            formula=(
                r"C = S e^{-qT}[1 - \chi^2(2y; df_1, 2x)]"
                r" - K e^{-rT} \chi^2(2x; df_2, 2y)"
            ),
            substitution=(
                f"C = {S}×{math.exp(-q * T):.6f}×(1-{cdf1:.6f})"
                f" - {K}×{math.exp(-r * T):.6f}×{cdf2:.6f}"
                f" = {t1:.4f} - {t2:.4f}"
            ),
            result=round(call_price, 4),
            explanation="The CEV call price via the Schroder (1989) non-central χ² method.",
        ))

        # ── Put via put-call parity ──
        if is_call:
            price = call_price
        else:
            parity_adjust = K * math.exp(-r * T) - S * math.exp(-q * T)
            price = call_price + parity_adjust
            steps.append(CalculationStep(
                step_number=8,
                label="Put via put-call parity",
                formula=r"P = C + K e^{-rT} - S e^{-qT}",
                substitution=(
                    f"P = {call_price:.4f} + {K}×{math.exp(-r * T):.6f}"
                    f" - {S}×{math.exp(-q * T):.6f} = {price:.4f}"
                ),
                result=round(price, 4),
                explanation="Put-call parity holds for European options under CEV.",
            ))

        # ── BSM comparison ──
        bsm_ref = _bsm_price(S, K, T, sigma, r, q, is_call)
        diff = price - bsm_ref
        step_n = 8 if is_call else 9
        steps.append(CalculationStep(
            step_number=step_n,
            label="Comparison with BSM",
            formula=r"\Delta_{model} = C_{CEV} - C_{BSM}",
            substitution=(
                f"BSM price (same σ₀): {bsm_ref:.4f},  "
                f"CEV price: {price:.4f},  "
                f"Difference: {diff:+.4f} ({diff / bsm_ref * 100:+.2f}%)"
            ),
            result=round(diff, 4),
            explanation=(
                "The model reserve is the difference between CEV and BSM. "
                "A negative diff means CEV assigns less value (β<1 shifts "
                "probability mass to lower spots)."
            ),
        ))

        greeks = self._finite_diff_greeks(params)

        return SimulatorResult(
            fair_value=round(price, 4),
            method=f"CEV (β={beta}, Schroder 1989)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "beta": beta,
                "n": round(n, 4),
                "kappa": round(kappa, 6),
                "x": round(x, 6),
                "y": round(y, 6),
                "forward": round(F, 4),
                "bsm_reference": round(bsm_ref, 4),
                "model_difference": round(diff, 4),
                "model_difference_pct": round(diff / bsm_ref * 100, 2) if bsm_ref != 0 else 0,
            },
        )

    def _finite_diff_greeks(self, params: dict[str, Any]) -> dict[str, float]:
        """Compute Greeks via central finite differences."""
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        beta = float(params["beta"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        is_call = params.get("option_type", "call").lower() == "call"

        def _price(s: float, k: float, t: float, sig: float,
                   b: float, rate: float, div: float) -> float:
            if abs(b - 1.0) < 1e-10:
                return _bsm_price(s, k, t, sig, rate, div, is_call)
            c = _cev_call_price(s, k, t, sig, b, rate, div)
            if is_call:
                return c
            return c + k * math.exp(-rate * t) - s * math.exp(-div * t)

        p0 = _price(S, K, T, sigma, beta, r, q)

        ds = S * 0.001
        delta = (_price(S + ds, K, T, sigma, beta, r, q)
                 - _price(S - ds, K, T, sigma, beta, r, q)) / (2 * ds)
        gamma = (_price(S + ds, K, T, sigma, beta, r, q)
                 - 2 * p0
                 + _price(S - ds, K, T, sigma, beta, r, q)) / (ds**2)

        dv = sigma * 0.01
        vega = (_price(S, K, T, sigma + dv, beta, r, q)
                - _price(S, K, T, sigma - dv, beta, r, q)) / (2 * dv) / 100

        dt = T * 0.001
        if T - dt > 0:
            theta = (_price(S, K, T - dt, sigma, beta, r, q) - p0) / dt / 365
        else:
            theta = 0.0

        dr = 0.0001
        rho = (_price(S, K, T, sigma, beta, r + dr, q)
               - _price(S, K, T, sigma, beta, r - dr, q)) / (2 * dr) / 100

        return {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega, 6),
            "theta": round(theta, 6),
            "rho": round(rho, 6),
        }

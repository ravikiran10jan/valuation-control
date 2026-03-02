"""FX Variance Gamma model for European FX options.

Adapts the Variance Gamma process (Madan, Carr & Chang, 1998) for FX markets.
The VG process captures jump risk, fat tails, and asymmetry that are common
in EM FX pairs and during stress events.  Uses the Carr-Madan FFT method
with FX-specific parametrisation (domestic/foreign rates).
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


def _bsm_fx_price(S: float, K: float, T: float, sigma: float,
                   r_d: float, r_f: float, is_call: bool) -> float:
    """Garman-Kohlhagen reference price."""
    d1 = (math.log(S / K) + (r_d - r_f + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return (S * math.exp(-r_f * T) * norm.cdf(d1)
                - K * math.exp(-r_d * T) * norm.cdf(d2))
    return (K * math.exp(-r_d * T) * norm.cdf(-d2)
            - S * math.exp(-r_f * T) * norm.cdf(-d1))


def _vg_char_fn(u: np.ndarray, T: float, sigma: float, theta: float,
                nu: float, r_d: float, r_f: float) -> np.ndarray:
    """Risk-neutral VG characteristic function for FX."""
    omega = (1.0 / nu) * math.log(1.0 - theta * nu - 0.5 * sigma**2 * nu)
    drift = (r_d - r_f + omega) * T
    inner = 1.0 - 1j * u * theta * nu + 0.5 * sigma**2 * nu * u**2
    return np.exp(1j * u * drift) * inner ** (-T / nu)


def _carr_madan_fft_fx(
    S: float, K: float, T: float, r_d: float, r_f: float,
    sigma: float, theta: float, nu: float,
    N: int = 4096, alpha: float = 1.5, eta: float = 0.25,
) -> float:
    """Carr-Madan FFT call price for FX."""
    lam = 2 * math.pi / (N * eta)
    b = N * lam / 2

    j = np.arange(N)
    v = eta * j

    u = v - (alpha + 1) * 1j
    phi = _vg_char_fn(u, T, sigma, theta, nu, r_d, r_f)
    denom = alpha**2 + alpha - v**2 + 1j * (2 * alpha + 1) * v

    w = eta / 3.0 * (3 + (-1) ** (j + 1))
    w[0] = eta / 3.0

    log_S = math.log(S)
    x = np.exp(-r_d * T) * phi / denom
    x *= np.exp(1j * v * (log_S + b)) * w

    fft_out = np.fft.fft(x).real
    k_grid = -b + lam * np.arange(N) + log_S
    call_grid = np.exp(-alpha * (k_grid - log_S)) / math.pi * fft_out

    log_K = math.log(K)
    call_price = float(np.interp(log_K, k_grid, call_grid))
    return max(call_price, 0.0)


@ModelRegistry.register
class FXVarianceGammaModel(BaseSimulatorModel):

    model_id = "fx_variance_gamma"
    model_name = "FX Variance Gamma"
    product_type = "European FX Vanilla Option"
    asset_class = "fx"

    short_description = (
        "FX option pricing with jumps, skew, and fat tails via VG process"
    )
    long_description = (
        "The Variance Gamma model adapted for FX markets. EM FX pairs "
        "(USD/BRL, USD/TRY, USD/ZAR) exhibit significant jump risk, fat tails, "
        "and asymmetry that the Garman-Kohlhagen model cannot capture. The VG "
        "process adds three parameters: σ (diffusion), θ (skew — negative means "
        "devaluation jumps are larger), and ν (tail heaviness). Pricing uses "
        "the Carr-Madan FFT method with FX-specific rate parametrisation."
    )

    when_to_use = [
        "EM FX options where jump risk is significant (BRL, TRY, ZAR, MXN)",
        "FX options around central bank announcements or elections",
        "When the FX smile is steep and BSM/GK underprices wings",
        "Risk management: quantifying tail risk in FX portfolios",
        "Comparing with GK to measure the impact of non-normality",
    ]
    when_not_to_use = [
        "Liquid G10 pairs where GK is sufficient (EUR/USD, USD/JPY in normal markets)",
        "When FX smile dynamics matter (forward smile, cliquets)",
        "Path-dependent FX exotics (barriers, TARFs — use local vol MC)",
        "When stochastic interest rates matter (long-dated FX hybrids)",
    ]
    assumptions = [
        "FX returns follow a Variance Gamma (pure-jump Lévy) process",
        "Three parameters: σ (diffusion), θ (skew), ν (kurtosis)",
        "Constant domestic and foreign interest rates",
        "Risk-neutral pricing via martingale correction ω",
        "European exercise only (FFT pricing)",
    ]
    limitations = [
        "Only 3 free parameters — limited flexibility for full FX surface fit",
        "No stochastic rates — matters for long-dated cross-currency products",
        "Hedging is harder (incomplete market under jumps)",
        "FFT pricing is slower than GK analytical",
    ]

    formula_latex = (
        r"\varphi(u) = e^{iu\omega T}"
        r"\left(1 - iu\theta\nu + \tfrac{1}{2}\sigma^2\nu u^2\right)^{-T/\nu}"
    )
    formula_plain = (
        "φ(u) = exp(iuωT) · (1 - iuθν + σ²νu²/2)^(-T/ν), "
        "ω = (1/ν)·ln(1 - θν - σ²ν/2). Price via Carr-Madan FFT."
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec("spot", "Spot FX Rate (S)", "Current FX rate (DOM/FOR)", "float", 5.10, 0.0001, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("strike", "Strike (K)", "Option strike FX rate", "float", 5.30, 0.0001, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("maturity", "Time to Expiry (T)", "Years", "float", 0.25, 0.001, 10.0, 0.01, unit="years"),
            ParameterSpec("sigma", "BM Volatility (σ)", "Volatility of the Brownian component", "float", 0.15, 0.001, 2.0, 0.01, unit="decimal"),
            ParameterSpec("theta", "Skew (θ)", "θ<0 = devaluation jumps dominate", "float", -0.10, -2.0, 2.0, 0.01),
            ParameterSpec("nu", "Kurtosis (ν)", "ν>0 = fat tails, ν→0 = GK", "float", 0.30, 0.001, 5.0, 0.01),
            ParameterSpec("r_d", "Domestic Rate (r_d)", "Domestic risk-free rate", "float", 0.125, -0.1, 0.5, 0.001, unit="decimal"),
            ParameterSpec("r_f", "Foreign Rate (r_f)", "Foreign risk-free rate", "float", 0.053, -0.1, 0.5, 0.001, unit="decimal"),
            ParameterSpec("option_type", "Option Type", "Call or Put", "select", "call", options=["call", "put"]),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "USD/BRL OTM Put (devaluation hedge)": {
                "spot": 5.10, "strike": 5.50, "maturity": 0.25,
                "sigma": 0.15, "theta": -0.10, "nu": 0.30,
                "r_d": 0.125, "r_f": 0.053, "option_type": "put",
            },
            "USD/TRY ATM Call (3M)": {
                "spot": 32.0, "strike": 32.0, "maturity": 0.25,
                "sigma": 0.20, "theta": -0.15, "nu": 0.40,
                "r_d": 0.42, "r_f": 0.053, "option_type": "call",
            },
            "USD/ZAR symmetric (ν only)": {
                "spot": 18.50, "strike": 18.50, "maturity": 0.5,
                "sigma": 0.16, "theta": 0.0, "nu": 0.25,
                "r_d": 0.08, "r_f": 0.053, "option_type": "call",
            },
            "Near-GK (ν→0)": {
                "spot": 1.0850, "strike": 1.0850, "maturity": 0.25,
                "sigma": 0.08, "theta": 0.0, "nu": 0.01,
                "r_d": 0.053, "r_f": 0.035, "option_type": "call",
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        theta = float(params["theta"])
        nu = float(params["nu"])
        r_d = float(params["r_d"])
        r_f = float(params["r_f"])
        opt_type = params.get("option_type", "call").lower()
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []

        # Step 1: martingale correction
        omega = (1.0 / nu) * math.log(1.0 - theta * nu - 0.5 * sigma**2 * nu)
        steps.append(CalculationStep(
            step_number=1,
            label="Martingale correction ω",
            formula=r"\omega = \frac{1}{\nu}\ln\!\left(1 - \theta\nu - \frac{\sigma^2\nu}{2}\right)",
            substitution=(
                f"ω = (1/{nu}) × ln(1 - ({theta})×{nu} - {sigma}²×{nu}/2)"
                f" = {omega:.6f}"
            ),
            result=round(omega, 6),
            explanation="Ensures the discounted FX rate is a martingale under the domestic risk-neutral measure.",
        ))

        # Step 2: return distribution
        vg_var = (sigma**2 + theta**2 * nu) * T
        vg_skew = (2 * theta**3 * nu**2 + 3 * sigma**2 * theta * nu) * T / vg_var**1.5 if vg_var > 0 else 0
        vg_kurt = 3 * (1 + (2 * theta**4 * nu**3 + 4 * sigma**2 * theta**2 * nu**2 + sigma**4 * nu) * T / vg_var**2) if vg_var > 0 else 3

        steps.append(CalculationStep(
            step_number=2,
            label="FX return distribution moments",
            formula=r"\text{Var} = (\sigma^2 + \theta^2 \nu)T",
            substitution=(
                f"Variance = {vg_var:.6f}, Skewness = {vg_skew:.4f}, "
                f"Excess kurtosis = {vg_kurt - 3:.4f}"
            ),
            result=round(vg_var, 6),
            explanation=(
                f"{'Negative skew — devaluation tail is heavier' if vg_skew < 0 else 'Positive skew' if vg_skew > 0 else 'Symmetric'}. "
                f"Excess kurtosis of {vg_kurt - 3:.2f} vs 0 for GK."
            ),
        ))

        # Step 3: FFT pricing
        N_fft = 4096
        call_price = _carr_madan_fft_fx(S, K, T, r_d, r_f, sigma, theta, nu, N=N_fft)
        steps.append(CalculationStep(
            step_number=3,
            label="Carr-Madan FFT pricing",
            formula=r"C(K) = \frac{e^{-\alpha k}}{\pi}\text{Re}\int_0^\infty e^{-iuk}\psi(u)\,du",
            substitution=f"FFT with N={N_fft}, Call price = {call_price:.6f}",
            result=round(call_price, 6),
            explanation="Carr-Madan FFT adapted for FX with domestic/foreign rate structure.",
        ))

        # Step 4: put via parity if needed
        if is_call:
            price = call_price
        else:
            price = call_price + K * math.exp(-r_d * T) - S * math.exp(-r_f * T)
            steps.append(CalculationStep(
                step_number=4,
                label="Put via put-call parity",
                formula=r"P = C + Ke^{-r_d T} - Se^{-r_f T}",
                substitution=f"P = {call_price:.6f} + {K * math.exp(-r_d * T):.6f} - {S * math.exp(-r_f * T):.6f} = {price:.6f}",
                result=round(price, 6),
                explanation="FX put-call parity with domestic/foreign discount factors.",
            ))

        # Step 5: GK comparison
        gk_ref = _bsm_fx_price(S, K, T, sigma, r_d, r_f, is_call)
        diff = price - gk_ref
        step_n = 4 if is_call else 5
        steps.append(CalculationStep(
            step_number=step_n + 1,
            label="Comparison with Garman-Kohlhagen",
            formula=r"\Delta_{model} = C_{VG} - C_{GK}",
            substitution=(
                f"GK price (same σ): {gk_ref:.6f},  VG price: {price:.6f},  "
                f"Difference: {diff:+.6f}"
                + (f" ({diff / gk_ref * 100:+.2f}%)" if gk_ref != 0 else "")
            ),
            result=round(diff, 6),
            explanation=(
                "The VG-GK difference quantifies the impact of jumps and "
                "fat tails. For EM FX OTM puts, VG typically prices higher."
            ),
        ))

        # Greeks via finite differences
        greeks = self._finite_diff_greeks(params)

        return SimulatorResult(
            fair_value=round(price, 6),
            method="FX Variance Gamma (Carr-Madan FFT)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "omega": round(omega, 6),
                "vg_variance": round(vg_var, 6),
                "vg_skewness": round(vg_skew, 4),
                "vg_excess_kurtosis": round(vg_kurt - 3, 4),
                "gk_reference": round(gk_ref, 6),
                "model_difference": round(diff, 6),
                "forward_rate": round(S * math.exp((r_d - r_f) * T), 6),
            },
        )

    def _finite_diff_greeks(self, params: dict[str, Any]) -> dict[str, float]:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        theta = float(params["theta"])
        nu = float(params["nu"])
        r_d = float(params["r_d"])
        r_f = float(params["r_f"])
        is_call = params.get("option_type", "call").lower() == "call"

        def _price(s, k, t, sig, th, v, rd, rf):
            c = _carr_madan_fft_fx(s, k, t, rd, rf, sig, th, v)
            if is_call:
                return c
            return c + k * math.exp(-rd * t) - s * math.exp(-rf * t)

        p0 = _price(S, K, T, sigma, theta, nu, r_d, r_f)
        ds = S * 0.001
        delta = (_price(S + ds, K, T, sigma, theta, nu, r_d, r_f)
                 - _price(S - ds, K, T, sigma, theta, nu, r_d, r_f)) / (2 * ds)
        gamma = (_price(S + ds, K, T, sigma, theta, nu, r_d, r_f)
                 - 2 * p0
                 + _price(S - ds, K, T, sigma, theta, nu, r_d, r_f)) / (ds**2)

        dv = sigma * 0.01
        vega = (_price(S, K, T, sigma + dv, theta, nu, r_d, r_f)
                - _price(S, K, T, sigma - dv, theta, nu, r_d, r_f)) / (2 * dv) / 100

        return {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega, 6),
        }

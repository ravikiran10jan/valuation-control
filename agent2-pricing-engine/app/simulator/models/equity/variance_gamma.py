"""Variance Gamma (VG) model for European options.

The Variance Gamma process (Madan, Carr & Chang, 1998) is obtained by
evaluating a Brownian motion at a random (gamma) time.  It captures both
skewness and excess kurtosis in the return distribution, controlled by
three parameters:

  σ  — volatility of the Brownian motion component
  θ  — drift of the BM  (θ < 0 → negative skew, typical for equities)
  ν  — variance of the gamma time change  (ν > 0 → fat tails)

Pricing uses the Carr-Madan FFT method via the VG characteristic function.
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


def _bsm_price(S: float, K: float, T: float, sigma: float,
                r: float, q: float, is_call: bool) -> float:
    """BSM reference price."""
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return (S * math.exp(-q * T) * norm.cdf(d1)
                - K * math.exp(-r * T) * norm.cdf(d2))
    return (K * math.exp(-r * T) * norm.cdf(-d2)
            - S * math.exp(-q * T) * norm.cdf(-d1))


def _vg_characteristic_function(
    u: np.ndarray, T: float, sigma: float, theta: float, nu: float,
    r: float, q: float,
) -> np.ndarray:
    """Risk-neutral VG characteristic function of log(S_T/S_0).

    φ(u) = exp(i u ω T) · (1 - i u θ ν + σ² ν u² / 2)^{-T/ν}

    where ω = (1/ν) ln(1 - θν - σ²ν/2) is the martingale correction.
    """
    omega = (1.0 / nu) * math.log(1.0 - theta * nu - 0.5 * sigma**2 * nu)
    drift = (r - q + omega) * T

    inner = 1.0 - 1j * u * theta * nu + 0.5 * sigma**2 * nu * u**2
    return np.exp(1j * u * drift) * inner ** (-T / nu)


def _carr_madan_fft(
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, theta: float, nu: float,
    N: int = 4096, alpha: float = 1.5, eta: float = 0.25,
) -> float:
    """Price a European call via the Carr-Madan (1999) FFT method.

    Returns the call price for a single strike K.
    """
    lam = 2 * math.pi / (N * eta)          # log-strike spacing
    b = N * lam / 2                         # centering offset

    # Grid in Fourier space
    j = np.arange(N)
    v = eta * j                             # integration variable

    # Carr-Madan modified call transform  ψ(v)
    #   ψ(v) = exp(-rT) φ(v - (α+1)i) / [α² + α - v² + i(2α+1)v]
    u = v - (alpha + 1) * 1j
    phi = _vg_characteristic_function(u, T, sigma, theta, nu, r, q)
    denom = alpha**2 + alpha - v**2 + 1j * (2 * alpha + 1) * v
    psi = math.exp(-r * T) * phi / denom

    # Simpson weights
    w = eta / 3.0 * (3 + (-1) ** (j + 1))
    w[0] = eta / 3.0

    # FFT input
    x = np.exp(1j * v * b) * psi * w * S ** (1j * v + alpha + 1)

    # Actually, the standard Carr-Madan uses log of S in the exponent.
    # Let's use the standard formulation properly:
    log_S = math.log(S)
    x2 = np.exp(-r * T) * phi / denom
    x2 *= np.exp(1j * v * (log_S + b)) * w

    fft_out = np.fft.fft(x2).real

    # Log-strike grid
    k_grid = -b + lam * np.arange(N) + log_S
    call_grid = np.exp(-alpha * (k_grid - log_S)) / math.pi * fft_out

    # Interpolate to get the price at the target strike
    log_K = math.log(K)
    call_price = float(np.interp(log_K, k_grid, call_grid))
    return max(call_price, 0.0)


@ModelRegistry.register
class VarianceGammaModel(BaseSimulatorModel):

    model_id = "variance_gamma"
    model_name = "Variance Gamma"
    product_type = "European Vanilla Option"
    asset_class = "equity"

    short_description = (
        "Option pricing with skewness and excess kurtosis via time-changed BM"
    )
    long_description = (
        "The Variance Gamma model (Madan, Carr & Chang, 1998) extends BSM by "
        "replacing calendar time with a random 'business time' drawn from a "
        "gamma process. This produces a pure-jump Lévy process that captures "
        "both skewness (via θ) and excess kurtosis (via ν) in the return "
        "distribution. When θ=0 and ν→0, VG converges to BSM. The model is "
        "particularly useful for pricing options in markets where jumps and "
        "fat tails are significant — e.g., equity earnings events or EM "
        "currencies. Pricing uses the Carr-Madan FFT method."
    )

    when_to_use = [
        "When returns exhibit excess kurtosis (fat tails) or skewness",
        "Pricing OTM puts where BSM underprices due to thin tails",
        "Equity options around earnings where jumps are expected",
        "EM currency options with jump risk",
        "Model comparison: quantifying the impact of non-normality",
        "LEAPS where non-normality compounds over time",
    ]
    when_not_to_use = [
        "When markets behave close to log-normal (simple, liquid equities)",
        "Real-time delta hedging (incomplete market, harder to hedge)",
        "Path-dependent exotics (MC under VG is slow and complex)",
        "When stochastic volatility dynamics are needed (VG has no vol-of-vol)",
        "Calibration to a full vol surface (VG has only 3 params)",
        "When fast pricing is critical (FFT is slower than BSM closed-form)",
    ]
    assumptions = [
        "Returns follow a pure-jump Lévy process (no diffusion component)",
        "Business time follows a Gamma process with mean rate 1 and variance ν",
        "Three parameters control the distribution: σ (diffusion), θ (skew), ν (kurtosis)",
        "Constant parameters over the option life (no term structure)",
        "Risk-neutral pricing via martingale correction ω",
    ]
    limitations = [
        "Only 3 free parameters — limited flexibility for full surface fit",
        "No stochastic vol — cannot capture vol-of-vol or vol clustering",
        "Hedging is harder (incomplete market, Greeks less intuitive)",
        "FFT pricing is slower than BSM analytical",
        "No efficient closed-form for Americans or path-dependents",
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
                "sigma", "BM Volatility (σ)",
                "Volatility of the Brownian motion component",
                "float", 0.20, 0.001, 2.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "theta", "Skew (θ)",
                "Drift of BM: θ<0 = negative skew (equity), θ=0 = symmetric",
                "float", -0.15, -2.0, 2.0, 0.01,
            ),
            ParameterSpec(
                "nu", "Kurtosis (ν)",
                "Variance of gamma time: ν>0 = fat tails, ν→0 = BSM",
                "float", 0.25, 0.001, 5.0, 0.01,
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)", "Continuous risk-free rate",
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
            "Fat tails, no skew": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "theta": 0.0, "nu": 0.25,
                "r": 0.05, "q": 0.0, "option_type": "call",
            },
            "Negative skew (equity-like)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "theta": -0.15, "nu": 0.25,
                "r": 0.05, "q": 0.0, "option_type": "call",
            },
            "OTM Put — high kurtosis (EM)": {
                "spot": 100.0, "strike": 90.0, "maturity": 0.5,
                "sigma": 0.25, "theta": -0.10, "nu": 0.50,
                "r": 0.05, "q": 0.0, "option_type": "put",
            },
            "Near-BSM (ν→0)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "sigma": 0.20, "theta": 0.0, "nu": 0.01,
                "r": 0.05, "q": 0.0, "option_type": "call",
            },
            "LEAPS with skew": {
                "spot": 150.0, "strike": 100.0, "maturity": 2.0,
                "sigma": 0.25, "theta": -0.15, "nu": 0.25,
                "r": 0.05, "q": 0.01, "option_type": "call",
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        theta = float(params["theta"])
        nu = float(params["nu"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        opt_type = params.get("option_type", "call").lower()
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []

        # ── Step 1: VG parameters ──
        omega = (1.0 / nu) * math.log(1.0 - theta * nu - 0.5 * sigma**2 * nu)
        steps.append(CalculationStep(
            step_number=1,
            label="Martingale correction ω",
            formula=r"\omega = \frac{1}{\nu}\ln\!\left(1 - \theta\nu - \frac{\sigma^2\nu}{2}\right)",
            substitution=(
                f"ω = (1/{nu}) × ln(1 - ({theta})×{nu} - {sigma}²×{nu}/2)"
                f" = {1.0 / nu:.4f} × ln({1 - theta * nu - 0.5 * sigma**2 * nu:.6f})"
            ),
            result=round(omega, 6),
            explanation=(
                "The martingale correction ensures the discounted stock price "
                "is a martingale under the risk-neutral measure."
            ),
        ))

        # ── Step 2: return distribution properties ──
        vg_mean = (r - q + omega) * T
        vg_var = (sigma**2 + theta**2 * nu) * T
        vg_skew = (2 * theta**3 * nu**2 + 3 * sigma**2 * theta * nu) * T / vg_var**1.5 if vg_var > 0 else 0
        vg_kurt = 3 * (1 + (2 * theta**4 * nu**3 + 4 * sigma**2 * theta**2 * nu**2 + sigma**4 * nu) * T / vg_var**2) if vg_var > 0 else 3

        steps.append(CalculationStep(
            step_number=2,
            label="Return distribution moments",
            formula=r"\text{Var} = (\sigma^2 + \theta^2 \nu)T, \quad \text{Skew} \propto \theta",
            substitution=(
                f"Annual var = {sigma}² + {theta}²×{nu} = {sigma**2 + theta**2 * nu:.6f}\n"
                f"Skewness ≈ {vg_skew:.4f} ({'negative — left tail heavier' if vg_skew < 0 else 'positive' if vg_skew > 0 else 'symmetric'})\n"
                f"Excess kurtosis ≈ {vg_kurt - 3:.4f} (BSM = 0)"
            ),
            result=round(vg_var, 6),
            explanation=(
                "VG with θ<0 generates negative skew (left tail). "
                f"ν={nu} adds {vg_kurt - 3:.2f} excess kurtosis vs BSM."
            ),
        ))

        # ── Step 3: characteristic function ──
        steps.append(CalculationStep(
            step_number=3,
            label="VG characteristic function",
            formula=(
                r"\varphi(u) = e^{iu\omega T}"
                r"\left(1 - iu\theta\nu + \tfrac{\sigma^2\nu u^2}{2}\right)^{-T/\nu}"
            ),
            substitution=(
                f"Exponent: -T/ν = -{T}/{nu} = {-T / nu:.4f}\n"
                f"Inner term at u=1: 1 - i({theta})({nu}) + {sigma}²({nu})/2"
                f" = {1 - theta * nu + 0.5 * sigma**2 * nu:.6f}"
            ),
            result=round(-T / nu, 4),
            explanation=(
                "The characteristic function encodes the full probability "
                "distribution. It is used as input to the FFT pricer."
            ),
        ))

        # ── Step 4: Carr-Madan FFT ──
        N_fft = 4096
        alpha_cm = 1.5
        eta = 0.25
        steps.append(CalculationStep(
            step_number=4,
            label="Carr-Madan FFT pricing",
            formula=(
                r"C(K) = \frac{e^{-\alpha k}}{\pi}"
                r"\text{Re}\!\int_0^\infty e^{-iuk}\psi(u)\,du"
            ),
            substitution=(
                f"FFT with N={N_fft}, damping α={alpha_cm}, grid spacing η={eta}\n"
                f"Log-strike spacing λ = 2π/(N·η) = {2 * math.pi / (N_fft * eta):.6f}\n"
                f"log(K) = {math.log(K):.6f}"
            ),
            result=N_fft,
            explanation=(
                "The Carr-Madan method transforms the pricing integral into "
                "Fourier space and evaluates it efficiently via FFT, producing "
                "prices for a grid of strikes simultaneously."
            ),
        ))

        # ── Step 5: compute the call price ──
        call_price = _carr_madan_fft(S, K, T, r, q, sigma, theta, nu,
                                     N=N_fft, alpha=alpha_cm, eta=eta)
        steps.append(CalculationStep(
            step_number=5,
            label="VG call price",
            formula=r"C_{VG} = \text{FFT}^{-1}[\psi(u)] \text{ at } K",
            substitution=f"Call price = {call_price:.4f}",
            result=round(call_price, 4),
            explanation="The European call price from the FFT inversion.",
        ))

        # ── Put via parity if needed ──
        if is_call:
            price = call_price
        else:
            price = call_price + K * math.exp(-r * T) - S * math.exp(-q * T)
            steps.append(CalculationStep(
                step_number=6,
                label="Put via put-call parity",
                formula=r"P = C + Ke^{-rT} - Se^{-qT}",
                substitution=(
                    f"P = {call_price:.4f} + {K}×{math.exp(-r * T):.6f}"
                    f" - {S}×{math.exp(-q * T):.6f} = {price:.4f}"
                ),
                result=round(price, 4),
                explanation="Put-call parity holds for European options.",
            ))

        # ── BSM comparison ──
        bsm_ref = _bsm_price(S, K, T, sigma, r, q, is_call)
        diff = price - bsm_ref
        step_n = 6 if is_call else 7
        steps.append(CalculationStep(
            step_number=step_n,
            label="Comparison with BSM",
            formula=r"\Delta_{model} = C_{VG} - C_{BSM}",
            substitution=(
                f"BSM price (same σ): {bsm_ref:.4f},  "
                f"VG price: {price:.4f},  "
                f"Difference: {diff:+.4f} ({diff / bsm_ref * 100:+.2f}%)" if bsm_ref != 0
                else f"BSM price: {bsm_ref:.4f}, VG price: {price:.4f}"
            ),
            result=round(diff, 4),
            explanation=(
                "The VG-BSM price difference shows the impact of skewness "
                "and kurtosis. For OTM puts with θ<0, VG typically prices higher."
            ),
        ))

        greeks = self._finite_diff_greeks(params)

        return SimulatorResult(
            fair_value=round(price, 4),
            method="Variance Gamma (Carr-Madan FFT)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "omega": round(omega, 6),
                "vg_variance": round(vg_var, 6),
                "vg_skewness": round(vg_skew, 4),
                "vg_excess_kurtosis": round(vg_kurt - 3, 4),
                "bsm_reference": round(bsm_ref, 4),
                "model_difference": round(diff, 4),
                "fft_grid_size": N_fft,
            },
        )

    def _finite_diff_greeks(self, params: dict[str, Any]) -> dict[str, float]:
        """Greeks via central finite differences."""
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        theta = float(params["theta"])
        nu = float(params["nu"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        is_call = params.get("option_type", "call").lower() == "call"

        def _price(s, k, t, sig, th, v, rate, div):
            c = _carr_madan_fft(s, k, t, rate, div, sig, th, v)
            if is_call:
                return c
            return c + k * math.exp(-rate * t) - s * math.exp(-div * t)

        p0 = _price(S, K, T, sigma, theta, nu, r, q)

        ds = S * 0.001
        delta = (_price(S + ds, K, T, sigma, theta, nu, r, q)
                 - _price(S - ds, K, T, sigma, theta, nu, r, q)) / (2 * ds)
        gamma = (_price(S + ds, K, T, sigma, theta, nu, r, q)
                 - 2 * p0
                 + _price(S - ds, K, T, sigma, theta, nu, r, q)) / (ds**2)

        dv = sigma * 0.01
        vega = (_price(S, K, T, sigma + dv, theta, nu, r, q)
                - _price(S, K, T, sigma - dv, theta, nu, r, q)) / (2 * dv) / 100

        dt = T * 0.001
        if T - dt > 0:
            theta_greek = (_price(S, K, T - dt, sigma, theta, nu, r, q) - p0) / dt / 365
        else:
            theta_greek = 0.0

        dr = 0.0001
        rho = (_price(S, K, T, sigma, theta, nu, r + dr, q)
               - _price(S, K, T, sigma, theta, nu, r - dr, q)) / (2 * dr) / 100

        return {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega, 6),
            "theta": round(theta_greek, 6),
            "rho": round(rho, 6),
        }

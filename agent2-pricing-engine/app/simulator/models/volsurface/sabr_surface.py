"""SABR Volatility Surface Model — Hagan et al. (2002).

The SABR (Stochastic Alpha Beta Rho) model is the industry standard for
modelling the implied volatility smile in FX, rates, and equity markets.

Dynamics:
    dF = alpha * F^beta * dW_1
    d_alpha = nu * alpha * dW_2
    corr(dW_1, dW_2) = rho

Parameters:
    alpha  - Initial volatility level (vol scale)
    beta   - CEV exponent (backbone / leverage), typically 0 <= beta <= 1
    rho    - Correlation between forward and vol Brownians, -1 < rho < 1
    nu     - Vol-of-vol (volatility of alpha process)

The Hagan approximation gives a closed-form implied vol sigma_impl(K, F, T)
that captures the smile, skew, and term structure.

SABR Greeks (model-specific sensitivities):
    d(sigma)/d(alpha) — vol sensitivity to alpha
    d(sigma)/d(rho)   — skew sensitivity
    d(sigma)/d(nu)    — smile curvature sensitivity

Reference: Hagan, Kumar, Lesniewski, Woodward (2002)
           "Managing Smile Risk", Wilmott Magazine.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _sabr_implied_vol(
    F: float, K: float, T: float,
    alpha: float, beta: float, rho: float, nu: float,
) -> float:
    """Hagan et al. (2002) SABR implied volatility approximation.

    Returns the Black implied volatility for strike K, forward F,
    expiry T under the SABR model with parameters (alpha, beta, rho, nu).
    """
    if F <= 0 or K <= 0 or T <= 0 or alpha <= 0:
        return 0.0

    # ATM limit
    if abs(F - K) < 1e-12:
        FK_mid = F ** (1.0 - beta)
        vol = (
            alpha / FK_mid
            * (
                1.0
                + (
                    ((1.0 - beta) ** 2 / 24.0) * alpha ** 2 / FK_mid ** 2
                    + 0.25 * rho * beta * nu * alpha / FK_mid
                    + (2.0 - 3.0 * rho ** 2) / 24.0 * nu ** 2
                )
                * T
            )
        )
        return max(vol, 1e-8)

    FK = F * K
    FK_beta = FK ** ((1.0 - beta) / 2.0)
    log_FK = math.log(F / K)

    z = (nu / alpha) * FK_beta * log_FK
    sqrt_term = math.sqrt(1.0 - 2.0 * rho * z + z ** 2)
    x_z = math.log((sqrt_term + z - rho) / (1.0 - rho))

    if abs(x_z) < 1e-12:
        x_z = 1.0

    prefix = alpha / (
        FK_beta
        * (
            1.0
            + (1.0 - beta) ** 2 / 24.0 * log_FK ** 2
            + (1.0 - beta) ** 4 / 1920.0 * log_FK ** 4
        )
    )
    correction = 1.0 + (
        (1.0 - beta) ** 2 / 24.0 * alpha ** 2 / FK_beta ** 2
        + 0.25 * rho * beta * nu * alpha / FK_beta
        + (2.0 - 3.0 * rho ** 2) / 24.0 * nu ** 2
    ) * T

    return max(prefix * (z / x_z) * correction, 1e-8)


def _sabr_d_alpha(
    F: float, K: float, T: float,
    alpha: float, beta: float, rho: float, nu: float,
    bump: float = 1e-5,
) -> float:
    """d(sigma)/d(alpha) — finite difference."""
    v_up = _sabr_implied_vol(F, K, T, alpha + bump, beta, rho, nu)
    v_dn = _sabr_implied_vol(F, K, T, max(alpha - bump, 1e-8), beta, rho, nu)
    return (v_up - v_dn) / (2.0 * bump)


def _sabr_d_rho(
    F: float, K: float, T: float,
    alpha: float, beta: float, rho: float, nu: float,
    bump: float = 1e-4,
) -> float:
    """d(sigma)/d(rho) — finite difference."""
    rho_up = min(rho + bump, 0.999)
    rho_dn = max(rho - bump, -0.999)
    v_up = _sabr_implied_vol(F, K, T, alpha, beta, rho_up, nu)
    v_dn = _sabr_implied_vol(F, K, T, alpha, beta, rho_dn, nu)
    return (v_up - v_dn) / (rho_up - rho_dn)


def _sabr_d_nu(
    F: float, K: float, T: float,
    alpha: float, beta: float, rho: float, nu: float,
    bump: float = 1e-4,
) -> float:
    """d(sigma)/d(nu) — finite difference."""
    v_up = _sabr_implied_vol(F, K, T, alpha, beta, rho, nu + bump)
    v_dn = _sabr_implied_vol(F, K, T, alpha, beta, rho, max(nu - bump, 1e-8))
    return (v_up - v_dn) / (2.0 * bump)


@ModelRegistry.register
class SABRVolSurfaceModel(BaseSimulatorModel):

    model_id = "sabr_vol_surface"
    model_name = "SABR Volatility Surface"
    product_type = "Volatility Surface"
    asset_class = "volsurface"

    short_description = (
        "SABR stochastic-alpha-beta-rho implied volatility smile and surface "
        "with full parameter sensitivities"
    )
    long_description = (
        "The SABR model (Hagan et al. 2002) is the most widely used parametric "
        "volatility smile model in derivatives markets. It models the forward rate "
        "as dF = alpha*F^beta*dW_1 with stochastic vol d_alpha = nu*alpha*dW_2 "
        "and correlation rho = corr(dW_1, dW_2).\n\n"
        "Key parameters:\n"
        "  - Alpha: initial vol level (drives ATM vol)\n"
        "  - Beta: CEV backbone (0=normal, 0.5=CIR, 1=lognormal)\n"
        "  - Rho: spot-vol correlation (drives skew; negative => equity-like)\n"
        "  - Nu: vol-of-vol (drives smile wings / curvature)\n\n"
        "This simulator computes the full implied vol smile across strikes, "
        "SABR-specific Greeks (d_sigma/d_alpha, d_sigma/d_rho, d_sigma/d_nu), "
        "and diagnostic surface statistics."
    )

    when_to_use = [
        "FX option smile interpolation (market standard for FX desks)",
        "Interest rate caps/floors and swaptions smile modelling",
        "When you need a parsimonious, arbitrage-aware smile parametrisation",
        "Calibrating to market butterfly/risk-reversal quotes",
        "Understanding how alpha, rho, nu affect the smile shape",
    ]
    when_not_to_use = [
        "Very deep OTM/ITM options (Hagan formula can break down)",
        "Negative rates without shifting (use shifted SABR instead)",
        "When you need a full local vol surface (use Dupire)",
        "Pricing path-dependent exotics (SABR is a marginal distribution model)",
    ]
    assumptions = [
        "dF = alpha * F^beta * dW_1  (CEV-type forward dynamics)",
        "d_alpha = nu * alpha * dW_2  (geometric Brownian vol)",
        "corr(dW_1, dW_2) = rho  (constant correlation)",
        "Uses the Hagan (2002) asymptotic expansion for implied vol",
        "Beta is typically pre-set (e.g. 0.5 for FX, 0 or 1 for rates)",
    ]
    limitations = [
        "Hagan formula can produce negative densities for extreme strikes",
        "Accuracy degrades for very long expiries (asymptotic expansion)",
        "Does not handle negative forwards (need shifted SABR extension)",
        "Beta and alpha are correlated — typically fix beta, calibrate the rest",
        "Forward smile dynamics may not match market behaviour",
    ]

    formula_latex = (
        r"\sigma_{SABR}(K) = \frac{\alpha}{(FK)^{(1-\beta)/2}"
        r"\left[1 + \frac{(1-\beta)^2}{24}\ln^2\frac{F}{K} + \ldots\right]}"
        r"\cdot \frac{z}{\chi(z)}"
        r"\cdot \left[1 + \left(\frac{(1-\beta)^2}{24}\frac{\alpha^2}{(FK)^{1-\beta}}"
        r"+ \frac{\rho\beta\nu\alpha}{4(FK)^{(1-\beta)/2}}"
        r"+ \frac{2-3\rho^2}{24}\nu^2\right)T\right]"
    )
    formula_plain = (
        "sigma_SABR(K) = [alpha / (FK)^((1-beta)/2)] * (z / chi(z)) * correction(T)\n"
        "where z = (nu/alpha) * (FK)^((1-beta)/2) * ln(F/K)\n"
        "and chi(z) = ln[(sqrt(1 - 2*rho*z + z^2) + z - rho) / (1 - rho)]"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "forward", "Forward Price (F)", "Forward price / rate",
                "float", 100.0, 0.001, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "maturity", "Expiry (T)", "Time to expiry in years",
                "float", 1.0, 0.01, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "alpha", "Alpha (α)", "Initial stochastic vol level (vol scale)",
                "float", 0.20, 0.001, 5.0, 0.001,
            ),
            ParameterSpec(
                "beta", "Beta (β)", "CEV exponent (0=normal, 0.5=CIR, 1=lognormal)",
                "float", 0.5, 0.0, 1.0, 0.05,
            ),
            ParameterSpec(
                "rho", "Rho (ρ)", "Spot-vol correlation (-1 < ρ < 1). Negative = equity skew",
                "float", -0.25, -0.999, 0.999, 0.01,
            ),
            ParameterSpec(
                "nu", "Nu (ν) — Vol-of-Vol", "Volatility of the alpha process",
                "float", 0.30, 0.001, 5.0, 0.01,
            ),
            ParameterSpec(
                "n_strikes", "Number of Strikes", "Number of strike points for the smile",
                "int", 21, 5, 101, 2,
            ),
            ParameterSpec(
                "strike_range", "Strike Range (±%)", "Range around forward as percentage",
                "float", 30.0, 5.0, 80.0, 5.0, unit="%",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "FX Smile (EUR/USD)": {
                "forward": 1.0850, "maturity": 0.25,
                "alpha": 0.068, "beta": 0.5, "rho": -0.15, "nu": 0.40,
                "n_strikes": 21, "strike_range": 15.0,
            },
            "Equity Skew (S&P 500)": {
                "forward": 5000.0, "maturity": 1.0,
                "alpha": 0.20, "beta": 0.7, "rho": -0.70, "nu": 0.50,
                "n_strikes": 21, "strike_range": 30.0,
            },
            "Rates Smile (Swaption)": {
                "forward": 0.042, "maturity": 5.0,
                "alpha": 0.0080, "beta": 0.0, "rho": 0.10, "nu": 0.35,
                "n_strikes": 21, "strike_range": 50.0,
            },
            "High Vol-of-Vol (Wings)": {
                "forward": 100.0, "maturity": 0.5,
                "alpha": 0.25, "beta": 0.5, "rho": -0.30, "nu": 0.80,
                "n_strikes": 31, "strike_range": 40.0,
            },
            "Symmetric Smile (rho=0)": {
                "forward": 100.0, "maturity": 1.0,
                "alpha": 0.20, "beta": 0.5, "rho": 0.0, "nu": 0.40,
                "n_strikes": 21, "strike_range": 25.0,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        p = self.params_with_defaults(params)

        F = float(p["forward"])
        T = float(p["maturity"])
        alpha = float(p["alpha"])
        beta = float(p["beta"])
        rho = float(p["rho"])
        nu = float(p["nu"])
        n_strikes = int(p["n_strikes"])
        strike_range = float(p["strike_range"]) / 100.0

        steps: list[CalculationStep] = []

        # Step 1: SABR parameters summary
        steps.append(CalculationStep(
            step_number=1,
            label="SABR parameters",
            formula="dF = α·F^β·dW₁,  dα = ν·α·dW₂,  corr = ρ",
            substitution=(
                f"Forward F = {F}\n"
                f"Expiry T = {T} years\n"
                f"Alpha (α) = {alpha} — vol scale\n"
                f"Beta (β) = {beta} — CEV exponent "
                f"({'normal' if beta == 0 else 'lognormal' if beta == 1 else f'mixed ({beta})'})\n"
                f"Rho (ρ) = {rho} — {'negative skew' if rho < 0 else 'positive skew' if rho > 0 else 'symmetric'}\n"
                f"Nu (ν) = {nu} — vol-of-vol"
            ),
            result=round(alpha, 6),
            explanation=(
                "Alpha sets the overall vol level. Beta controls the backbone "
                "(how vol relates to forward level). Rho drives the skew direction. "
                "Nu controls smile curvature (wing vol)."
            ),
        ))

        # Step 2: ATM implied vol
        atm_vol = _sabr_implied_vol(F, F, T, alpha, beta, rho, nu)

        steps.append(CalculationStep(
            step_number=2,
            label="ATM implied volatility",
            formula="σ_ATM = σ_SABR(F, F, T, α, β, ρ, ν)",
            substitution=(
                f"σ_ATM = σ_SABR({F}, {F}, {T}, {alpha}, {beta}, {rho}, {nu})\n"
                f"σ_ATM = {atm_vol:.6f} ({atm_vol * 100:.2f}%)"
            ),
            result=round(atm_vol, 6),
            explanation=(
                "The ATM vol under SABR is approximately alpha / F^(1-beta) "
                "for short expiries. The correction term adds T-dependent adjustments."
            ),
        ))

        # Step 3: Full smile across strikes
        K_min = F * (1.0 - strike_range)
        K_max = F * (1.0 + strike_range)
        strikes = np.linspace(max(K_min, F * 0.01), K_max, n_strikes)

        smile = {}
        for K in strikes:
            iv = _sabr_implied_vol(F, float(K), T, alpha, beta, rho, nu)
            moneyness = math.log(float(K) / F) if F > 0 else 0.0
            smile[f"{float(K):.4f}"] = {
                "strike": round(float(K), 4),
                "implied_vol": round(iv, 6),
                "implied_vol_pct": round(iv * 100, 2),
                "moneyness": round(moneyness, 4),
            }

        vols = [v["implied_vol"] for v in smile.values()]
        vol_min = min(vols)
        vol_max = max(vols)
        skew_25d = 0.0
        if len(strikes) >= 5:
            # Approximate 25-delta skew: vol(K_low) - vol(K_high)
            idx_low = len(strikes) // 4
            idx_high = 3 * len(strikes) // 4
            skew_25d = vols[idx_low] - vols[idx_high]

        smile_summary = (
            f"Computed {n_strikes} points from K={float(strikes[0]):.4f} to K={float(strikes[-1]):.4f}\n"
            f"Vol range: {vol_min*100:.2f}% to {vol_max*100:.2f}%\n"
            f"ATM vol: {atm_vol*100:.2f}%\n"
            f"Smile width: {(vol_max - vol_min)*100:.2f}%\n"
            f"Approx 25d skew: {skew_25d*100:+.2f}%"
        )

        steps.append(CalculationStep(
            step_number=3,
            label="Implied vol smile",
            formula="σ_SABR(K) for K ∈ [K_min, K_max]",
            substitution=smile_summary,
            result=round(atm_vol, 6),
            explanation=(
                "The SABR smile is driven by rho (skew) and nu (curvature). "
                "Negative rho produces equity-like downside skew. "
                "Higher nu widens the smile wings."
            ),
        ))

        # Step 4: SABR sensitivities (model-specific Greeks)
        d_alpha = _sabr_d_alpha(F, F, T, alpha, beta, rho, nu)
        d_rho_val = _sabr_d_rho(F, F, T, alpha, beta, rho, nu)
        d_nu_val = _sabr_d_nu(F, F, T, alpha, beta, rho, nu)

        steps.append(CalculationStep(
            step_number=4,
            label="SABR sensitivities (ATM)",
            formula=(
                "dσ/dα — vol sensitivity to alpha\n"
                "dσ/dρ — skew sensitivity\n"
                "dσ/dν — curvature sensitivity"
            ),
            substitution=(
                f"dσ/dα = {d_alpha:.6f} — 1 unit alpha bump => {d_alpha*100:.3f}% vol change\n"
                f"dσ/dρ = {d_rho_val:.6f} — 1 unit rho bump => {d_rho_val*100:.3f}% vol change\n"
                f"dσ/dν = {d_nu_val:.6f} — 1 unit nu bump => {d_nu_val*100:.3f}% vol change"
            ),
            result=round(d_alpha, 6),
            explanation=(
                "These SABR-specific sensitivities show how the implied vol changes "
                "when each SABR parameter is perturbed. Essential for SABR calibration "
                "risk and parameter hedging."
            ),
        ))

        # Step 5: Smile characteristics analysis
        # Risk reversal: OTM put vol - OTM call vol (25-delta convention)
        # Butterfly: 0.5*(OTM put vol + OTM call vol) - ATM vol
        n = len(strikes)
        if n >= 5:
            k_25p = strikes[n // 4]
            k_25c = strikes[3 * n // 4]
            v_25p = _sabr_implied_vol(F, float(k_25p), T, alpha, beta, rho, nu)
            v_25c = _sabr_implied_vol(F, float(k_25c), T, alpha, beta, rho, nu)
            risk_reversal = v_25p - v_25c
            butterfly = 0.5 * (v_25p + v_25c) - atm_vol
        else:
            risk_reversal = 0.0
            butterfly = 0.0

        steps.append(CalculationStep(
            step_number=5,
            label="Smile analytics (RR & Butterfly)",
            formula=(
                "Risk Reversal (RR) = σ(25d Put) - σ(25d Call)\n"
                "Butterfly (BF) = 0.5 * [σ(25d Put) + σ(25d Call)] - σ_ATM"
            ),
            substitution=(
                f"Risk Reversal = {risk_reversal*100:+.3f}% "
                f"({'negative skew' if risk_reversal > 0 else 'positive skew' if risk_reversal < 0 else 'flat'})\n"
                f"Butterfly = {butterfly*100:+.3f}% "
                f"({'convex smile' if butterfly > 0 else 'concave' if butterfly < 0 else 'flat'})"
            ),
            result=round(risk_reversal, 6),
            explanation=(
                "Risk Reversal measures the skew (difference between put and call wings). "
                "Butterfly measures the smile curvature (convexity of the wings vs ATM)."
            ),
        ))

        greeks = {
            "atm_vol": round(atm_vol, 6),
            "d_sigma_d_alpha": round(d_alpha, 6),
            "d_sigma_d_rho": round(d_rho_val, 6),
            "d_sigma_d_nu": round(d_nu_val, 6),
            "risk_reversal_25d": round(risk_reversal, 6),
            "butterfly_25d": round(butterfly, 6),
        }

        return SimulatorResult(
            fair_value=round(atm_vol, 6),
            method="SABR Hagan (2002) Implied Vol Approximation",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "sabr_params": {
                    "alpha": alpha, "beta": beta, "rho": rho, "nu": nu,
                },
                "atm_vol": round(atm_vol, 6),
                "vol_range": {"min": round(vol_min, 6), "max": round(vol_max, 6)},
                "smile_width_pct": round((vol_max - vol_min) * 100, 3),
                "risk_reversal_25d": round(risk_reversal, 6),
                "butterfly_25d": round(butterfly, 6),
                "smile": smile,
            },
        )

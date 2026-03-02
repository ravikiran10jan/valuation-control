"""First-to-Default Basket CDS — Gaussian Copula Monte Carlo.

Prices a first-to-default credit default swap on a basket of N obligors
using the one-factor Gaussian Copula model (Li, 2000).

The key mechanism:
1. Each obligor has a marginal hazard rate → survival curve
2. Default times are correlated through a Gaussian copula
3. The first default triggers the protection payment
4. Par spread = Protection Leg PV / Risky Annuity PV

The correlation parameter ρ controls everything:
  ρ = 0 → independent defaults → spread ≈ sum of individual spreads
  ρ = 1 → perfectly correlated → spread ≈ max individual spread
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


def _survival_prob(hazard_rate: float, t: float) -> float:
    """Q(t) = exp(-λt), constant hazard rate."""
    return math.exp(-hazard_rate * t)


def _default_time_from_uniform(u: float, hazard_rate: float) -> float:
    """Invert Q(t) = u  →  t = -ln(u) / λ."""
    if u <= 0 or u >= 1:
        return 1e10
    return -math.log(u) / hazard_rate


def _simulate_basket_defaults(
    hazard_rates: list[float],
    correlation: float,
    n_sims: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Simulate first-default times for a basket using Gaussian Copula.

    Returns array of shape (n_sims,) with the first default time per path.
    """
    n_names = len(hazard_rates)

    # One-factor Gaussian Copula:
    # Z_i = √ρ · M + √(1-ρ) · ε_i
    # where M ~ N(0,1) is the common factor, ε_i ~ N(0,1) are idiosyncratic

    M = rng.standard_normal(n_sims)
    first_defaults = np.full(n_sims, 1e10)

    for j in range(n_names):
        eps = rng.standard_normal(n_sims)
        Z = math.sqrt(max(correlation, 0)) * M + math.sqrt(max(1 - correlation, 0)) * eps
        U = norm.cdf(Z)  # transform to uniform
        tau = -np.log(np.clip(U, 1e-15, 1 - 1e-15)) / hazard_rates[j]
        first_defaults = np.minimum(first_defaults, tau)

    return first_defaults


@ModelRegistry.register
class FirstToDefaultModel(BaseSimulatorModel):

    model_id = "first_to_default"
    model_name = "First-to-Default Basket CDS"
    product_type = "Basket Credit Default Swap"
    asset_class = "credit"

    short_description = (
        "Price a first-to-default basket CDS via Gaussian Copula MC"
    )
    long_description = (
        "Prices a first-to-default credit default swap on a basket of N "
        "obligors using the one-factor Gaussian Copula model (Li, 2000). "
        "Each name has a constant hazard rate (flat CDS curve). Default "
        "correlation is introduced through a single common factor. The par "
        "spread is computed via Monte Carlo simulation of default times. "
        "This model is foundational to understanding basket credit products "
        "and was central to CDO pricing before the 2008 crisis."
    )

    when_to_use = [
        "Basket credit derivatives: first-to-default, nth-to-default swaps",
        "Understanding how default correlation drives basket spread",
        "Comparing correlation scenarios for credit portfolio risk",
        "Educational: demonstrating the Gaussian Copula for credit",
        "Quick indicative pricing for basket protection",
    ]
    when_not_to_use = [
        "Single-name CDS (use ISDA standard model)",
        "When you need dynamic/stochastic correlation",
        "Bespoke CDO tranches with complex subordination (need full loss dist)",
        "When hazard rate term structure matters (use piecewise flat)",
        "Production pricing requiring exact calibration to tranche markets",
    ]
    assumptions = [
        "Constant (flat) hazard rates for each obligor",
        "One-factor Gaussian Copula for default dependence",
        "Single correlation parameter ρ for all pairs (equicorrelation)",
        "Fixed recovery rate (same for all names)",
        "Continuous premium payments (simplified from quarterly)",
        "Deterministic interest rates",
    ]
    limitations = [
        "Gaussian Copula has thin tails — underestimates joint extreme events",
        "Equicorrelation is unrealistic for heterogeneous baskets",
        "Static correlation — cannot capture contagion or time-varying dependence",
        "Monte Carlo convergence requires large number of simulations",
        "Flat hazard rates ignore CDS term structure shape",
    ]

    formula_latex = (
        r"\text{Par Spread} = \frac{\text{Protection Leg PV}}{\text{Risky Annuity PV}}"
        r" = \frac{E[(1-R) \cdot D(\tau_1) \cdot 1_{\{\tau_1 \le T\}}]}"
        r"{E\left[\sum_{i} \Delta t_i \cdot D(t_i) \cdot 1_{\{\tau_1 > t_i\}}\right]}"
    )
    formula_plain = (
        "Par Spread = Protection Leg / Risky Annuity, "
        "where τ₁ = min(τ₁,...,τₙ) is the first default time"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "n_names", "Number of Names", "Obligors in the basket",
                "int", 5, 2, 20, 1,
            ),
            ParameterSpec(
                "hazard_rate", "Avg Hazard Rate (λ)",
                "Annual default intensity (all names equal)",
                "float", 0.02, 0.001, 0.20, 0.001,
            ),
            ParameterSpec(
                "correlation", "Default Correlation (ρ)",
                "Gaussian copula correlation (0=independent, 1=perfect)",
                "float", 0.30, 0.0, 0.99, 0.01,
            ),
            ParameterSpec(
                "recovery", "Recovery Rate (R)",
                "Expected recovery in default",
                "float", 0.40, 0.0, 0.95, 0.05,
            ),
            ParameterSpec(
                "maturity", "Maturity (T)", "CDS maturity in years",
                "float", 5.0, 1.0, 10.0, 1.0, unit="years",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Flat discount rate",
                "float", 0.05, 0.0, 0.20, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "n_sims", "MC Simulations", "Number of Monte Carlo paths",
                "int", 50000, 1000, 500000, 1000,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "5-name IG basket (ρ=0.3)": {
                "n_names": 5, "hazard_rate": 0.01, "correlation": 0.30,
                "recovery": 0.40, "maturity": 5.0, "r": 0.05, "n_sims": 50000,
            },
            "5-name HY basket (ρ=0.3)": {
                "n_names": 5, "hazard_rate": 0.05, "correlation": 0.30,
                "recovery": 0.40, "maturity": 5.0, "r": 0.05, "n_sims": 50000,
            },
            "High correlation (ρ=0.8)": {
                "n_names": 5, "hazard_rate": 0.02, "correlation": 0.80,
                "recovery": 0.40, "maturity": 5.0, "r": 0.05, "n_sims": 50000,
            },
            "Independent defaults (ρ=0)": {
                "n_names": 5, "hazard_rate": 0.02, "correlation": 0.0,
                "recovery": 0.40, "maturity": 5.0, "r": 0.05, "n_sims": 50000,
            },
            "10-name diversified basket": {
                "n_names": 10, "hazard_rate": 0.02, "correlation": 0.20,
                "recovery": 0.40, "maturity": 5.0, "r": 0.05, "n_sims": 50000,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        n_names = int(params["n_names"])
        lam = float(params["hazard_rate"])
        rho = float(params["correlation"])
        R = float(params["recovery"])
        T = float(params["maturity"])
        r = float(params["r"])
        n_sims = int(params.get("n_sims", 50000))

        hazard_rates = [lam] * n_names
        steps: list[CalculationStep] = []
        rng = np.random.default_rng(42)

        # Step 1: Marginal survival curves
        surv_1y = _survival_prob(lam, 1.0)
        surv_5y = _survival_prob(lam, 5.0)
        single_spread = lam * (1 - R) * 10000  # approx in bps

        steps.append(CalculationStep(
            step_number=1,
            label="Marginal survival curves",
            formula=r"Q(t) = e^{-\lambda t}, \quad \text{single-name spread} \approx \lambda(1-R)",
            substitution=(
                f"λ = {lam}, R = {R}\n"
                f"Q(1Y) = {surv_1y:.6f}, Q(5Y) = {surv_5y:.6f}\n"
                f"Single-name approx spread: {single_spread:.1f} bps\n"
                f"All {n_names} names have the same hazard rate"
            ),
            result=round(single_spread, 1),
            explanation=(
                "Under constant hazard rate, survival is exponential. "
                "Single-name CDS spread ≈ λ(1-R) for small λ."
            ),
        ))

        # Step 2: Gaussian Copula correlation structure
        steps.append(CalculationStep(
            step_number=2,
            label="Gaussian Copula correlation",
            formula=r"Z_i = \sqrt{\rho}\,M + \sqrt{1-\rho}\,\varepsilon_i, \quad U_i = \Phi(Z_i)",
            substitution=(
                f"ρ = {rho}\n"
                f"Factor loading: √ρ = {math.sqrt(rho):.4f}\n"
                f"Idiosyncratic loading: √(1-ρ) = {math.sqrt(1 - rho):.4f}\n"
                f"N = {n_names} names, equicorrelation"
            ),
            result=round(rho, 4),
            explanation=(
                "The one-factor Gaussian Copula generates correlated uniform "
                "random variables. Higher ρ means defaults are more clustered."
            ),
        ))

        # Step 3: Simulate first-default times
        first_defaults = _simulate_basket_defaults(hazard_rates, rho, n_sims, rng)

        pct_default_before_T = float(np.mean(first_defaults <= T)) * 100
        mean_first_default = float(np.mean(first_defaults[first_defaults <= T * 2]))
        median_first_default = float(np.median(first_defaults[first_defaults <= T * 2]))

        steps.append(CalculationStep(
            step_number=3,
            label="Simulate first-default times",
            formula=r"\tau_1 = \min(\tau_1, \tau_2, \ldots, \tau_N)",
            substitution=(
                f"Paths: {n_sims}\n"
                f"P(first default ≤ {T}Y): {pct_default_before_T:.1f}%\n"
                f"Mean first default time: {mean_first_default:.2f}Y\n"
                f"Median first default time: {median_first_default:.2f}Y"
            ),
            result=round(pct_default_before_T, 1),
            explanation=(
                "The first-to-default event is the minimum of N correlated "
                "default times. More names and lower correlation → earlier expected first default."
            ),
        ))

        # Step 4: Price protection leg
        # Protection PV = E[(1-R) × D(τ₁) × 1{τ₁ ≤ T}]
        prot_mask = first_defaults <= T
        if np.any(prot_mask):
            disc_at_default = np.exp(-r * first_defaults[prot_mask])
            prot_pv = float(np.mean(disc_at_default)) * (1 - R) * pct_default_before_T / 100
        else:
            prot_pv = 0.0

        # More precise: average over all paths
        prot_payments = np.where(
            first_defaults <= T,
            (1 - R) * np.exp(-r * first_defaults),
            0.0,
        )
        prot_pv = float(np.mean(prot_payments))

        steps.append(CalculationStep(
            step_number=4,
            label="Protection leg PV",
            formula=r"\text{Prot} = E[(1-R) \cdot e^{-r\tau_1} \cdot 1_{\{\tau_1 \le T\}}]",
            substitution=(
                f"(1-R) = {1 - R}\n"
                f"E[D(τ₁) × 1{{τ₁≤T}}] = {prot_pv / (1 - R):.6f}\n"
                f"Protection PV = {prot_pv:.6f}"
            ),
            result=round(prot_pv, 6),
            explanation=(
                "The protection buyer receives (1-R) at the time of the first "
                "default, discounted to today. Zero if no default occurs."
            ),
        ))

        # Step 5: Price premium (risky annuity) leg
        # Annuity = E[Σ Δt × D(tᵢ) × 1{τ₁ > tᵢ}]
        # Use quarterly payment dates
        payment_dates = np.arange(0.25, T + 0.01, 0.25)
        dt_payment = 0.25

        annuity_sum = np.zeros(n_sims)
        for t_pay in payment_dates:
            surviving = first_defaults > t_pay
            annuity_sum += dt_payment * math.exp(-r * t_pay) * surviving

        risky_annuity = float(np.mean(annuity_sum))

        steps.append(CalculationStep(
            step_number=5,
            label="Risky annuity (premium leg PV per unit spread)",
            formula=r"\text{Annuity} = E\!\left[\sum_{i} \Delta t \cdot e^{-r t_i} \cdot 1_{\{\tau_1 > t_i\}}\right]",
            substitution=(
                f"Payment frequency: quarterly ({len(payment_dates)} dates)\n"
                f"Risky Annuity = {risky_annuity:.6f}"
            ),
            result=round(risky_annuity, 6),
            explanation=(
                "The risky annuity is the PV of receiving $1/year until the first "
                "default or maturity, whichever comes first."
            ),
        ))

        # Step 6: Par spread
        if risky_annuity > 1e-10:
            par_spread = prot_pv / risky_annuity
            par_spread_bps = par_spread * 10000
        else:
            par_spread = 0
            par_spread_bps = 0

        steps.append(CalculationStep(
            step_number=6,
            label="First-to-default par spread",
            formula=r"s = \frac{\text{Protection PV}}{\text{Risky Annuity}} \times 10000 \text{ bps}",
            substitution=(
                f"s = {prot_pv:.6f} / {risky_annuity:.6f} = {par_spread:.6f}\n"
                f"Par spread = {par_spread_bps:.1f} bps"
            ),
            result=round(par_spread_bps, 1),
            explanation=(
                "The par spread is the annual premium (in bps) that makes the "
                "CDS have zero value at inception."
            ),
        ))

        # Step 7: Sensitivity analysis
        # Compare with independent (ρ=0) and single-name
        # Independent: 1 - (1-p)^N where p is single-name default prob
        indep_first_def_prob = 1 - _survival_prob(lam, T) ** n_names
        indep_approx_spread = n_names * single_spread  # rough upper bound for independent

        steps.append(CalculationStep(
            step_number=7,
            label="Correlation sensitivity",
            formula=r"\text{Spread}(\rho=0) \approx N \times s_{single}, \quad \text{Spread}(\rho=1) \approx s_{single}",
            substitution=(
                f"Single-name spread: ~{single_spread:.0f} bps\n"
                f"Basket spread (ρ={rho}): {par_spread_bps:.0f} bps\n"
                f"Independent approx (ρ=0): ~{indep_approx_spread:.0f} bps\n"
                f"Perfect corr (ρ=1): ~{single_spread:.0f} bps\n"
                f"Ratio to single: {par_spread_bps / single_spread:.2f}x"
                if single_spread > 0 else ""
            ),
            result=round(par_spread_bps / single_spread if single_spread > 0 else 0, 2),
            explanation=(
                "At ρ=0 (independent), the first-to-default spread ≈ N × single-name "
                "(diversification benefit). At ρ=1, all names default together, "
                "so basket spread ≈ single-name."
            ),
        ))

        # Build histogram of first default times
        ftd_within = first_defaults[first_defaults <= T * 1.5]
        if len(ftd_within) > 10:
            hist_counts, hist_edges = np.histogram(ftd_within, bins=25)
            histogram = [
                {"bin_start": round(float(hist_edges[i]), 2),
                 "bin_end": round(float(hist_edges[i + 1]), 2),
                 "count": int(hist_counts[i])}
                for i in range(len(hist_counts))
            ]
        else:
            histogram = []

        return SimulatorResult(
            fair_value=round(par_spread_bps, 1),
            method=f"Gaussian Copula MC ({n_sims:,} sims, {n_names} names)",
            greeks={},
            calculation_steps=steps,
            diagnostics={
                "par_spread_bps": round(par_spread_bps, 1),
                "protection_pv": round(prot_pv, 6),
                "risky_annuity": round(risky_annuity, 6),
                "pct_default_within_T": round(pct_default_before_T, 1),
                "single_name_spread_bps": round(single_spread, 1),
                "spread_to_single_ratio": round(par_spread_bps / single_spread if single_spread > 0 else 0, 2),
                "n_names": n_names,
                "correlation": rho,
                "recovery": R,
                "histogram": histogram,
            },
        )

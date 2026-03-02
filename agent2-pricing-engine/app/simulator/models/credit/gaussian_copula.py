"""Gaussian Copula CDO Tranche Pricing — Li (2000) One-Factor Model.

The workhorse of structured credit:

1. Generate correlated default times for N portfolio names using a
   one-factor Gaussian Copula: Z_i = √ρ·M + √(1-ρ)·ε_i
2. Transform uniform marginals to default times via survival inversion
3. At each payment date compute the portfolio loss distribution
4. Map portfolio loss to tranche loss: clip to [attachment, detachment]
5. Protection leg PV = E[discounted incremental tranche losses]
6. Premium leg PV01 = E[discounted outstanding tranche notional × Δt]
7. Fair tranche spread = Protection PV / Premium PV01 (in bps)

This is the model that priced the CDO market pre-2008 and is still used
as the baseline for structured credit analytics.
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


# ─────────────────────────────────────────────────────────────────────────────
# Core numeric helpers
# ─────────────────────────────────────────────────────────────────────────────

def _default_times(
    n_names: int,
    hazard_rate: float,
    correlation: float,
    n_sims: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Simulate default times for N names × n_sims paths using one-factor GC.

    Returns ndarray of shape (n_sims, n_names).
    """
    sqrt_rho = math.sqrt(max(correlation, 0.0))
    sqrt_1mrho = math.sqrt(max(1.0 - correlation, 0.0))

    # Common market factor: shape (n_sims, 1)
    M = rng.standard_normal((n_sims, 1))
    # Idiosyncratic factors: shape (n_sims, n_names)
    eps = rng.standard_normal((n_sims, n_names))

    # Latent variable Z_i = √ρ·M + √(1-ρ)·ε_i
    Z = sqrt_rho * M + sqrt_1mrho * eps  # (n_sims, n_names)

    # Uniform marginals via Gaussian CDF
    U = norm.cdf(Z)  # (n_sims, n_names)

    # Default times via inverse exponential CDF: τ = -ln(U) / λ
    U_clipped = np.clip(U, 1e-15, 1.0 - 1e-15)
    tau = -np.log(U_clipped) / hazard_rate  # (n_sims, n_names)
    return tau


def _portfolio_loss_at(
    tau: np.ndarray,
    t: float,
    recovery: float,
    loss_per_name: float,
) -> np.ndarray:
    """Portfolio loss (absolute $) at time t for each simulation path.

    loss_per_name = (1 - R) × (notional / N)
    """
    defaults_by_t = (tau <= t).sum(axis=1)  # (n_sims,)
    return defaults_by_t * loss_per_name


def _tranche_loss(
    portfolio_loss: np.ndarray,
    attachment: float,
    detachment: float,
    notional: float,
) -> np.ndarray:
    """Map portfolio loss to tranche loss.

    Tranche loss = min(max(L - A×N, 0), (D-A)×N)
    """
    A = attachment * notional
    D = detachment * notional
    return np.clip(portfolio_loss - A, 0.0, D - A)


def _price_tranche(
    tau: np.ndarray,
    recovery: float,
    attachment: float,
    detachment: float,
    notional: float,
    maturity: float,
    r: float,
) -> tuple[float, float, float, list[dict]]:
    """Price a CDO tranche via MC.

    Returns:
        protection_pv   – PV of protection leg (per unit notional)
        premium_pv01    – PV01 of premium leg (risky annuity of outstanding)
        fair_spread_bps – par spread in bps
        loss_timeline   – list of {t, E_tranche_loss, E_outstanding} dicts
    """
    n_sims = tau.shape[0]
    n_names = tau.shape[1]
    loss_per_name = (1.0 - recovery) * notional / n_names
    tranche_face = (detachment - attachment) * notional

    # Payment dates (quarterly)
    payment_dates = np.arange(0.25, maturity + 0.01, 0.25)
    dt = 0.25

    protection_pv = 0.0
    premium_pv01 = 0.0
    prev_tranche_loss = np.zeros(n_sims)
    loss_timeline = []

    for t in payment_dates:
        port_loss = _portfolio_loss_at(tau, t, recovery, loss_per_name)
        curr_tranche_loss = _tranche_loss(port_loss, attachment, detachment, notional)

        # Incremental tranche loss this period
        delta_t_loss = curr_tranche_loss - prev_tranche_loss
        df = math.exp(-r * t)

        # Protection leg: E[ΔTrancheLoss(t)] × D(t)
        protection_pv += float(np.mean(delta_t_loss)) * df

        # Outstanding tranche notional this period
        outstanding = tranche_face - curr_tranche_loss
        premium_pv01 += float(np.mean(outstanding)) * df * dt

        loss_timeline.append({
            "t": round(t, 2),
            "E_tranche_loss": round(float(np.mean(curr_tranche_loss)), 4),
            "E_outstanding": round(float(np.mean(outstanding)), 4),
        })

        prev_tranche_loss = curr_tranche_loss

    if premium_pv01 > 1e-10:
        fair_spread_bps = (protection_pv / premium_pv01) * 10000
    else:
        fair_spread_bps = 0.0

    return protection_pv, premium_pv01, fair_spread_bps, loss_timeline


# ─────────────────────────────────────────────────────────────────────────────
# Model class
# ─────────────────────────────────────────────────────────────────────────────

@ModelRegistry.register
class GaussianCopulaCDOModel(BaseSimulatorModel):

    model_id = "gaussian_copula"
    model_name = "Gaussian Copula CDO Tranche"
    product_type = "CDO Tranche"
    asset_class = "credit"

    short_description = (
        "Price a CDO tranche via one-factor Gaussian Copula Monte Carlo"
    )
    long_description = (
        "The Li (2000) one-factor Gaussian Copula model for Collateralised Debt "
        "Obligation (CDO) tranche pricing. The model generates correlated default "
        "times for a homogeneous credit portfolio, then prices a tranche defined "
        "by attachment and detachment points. The protection leg PV equals the "
        "expected discounted incremental tranche loss. The fair spread is the "
        "ratio of the protection leg to the premium leg PV01 (risky outstanding "
        "tranche notional). The single correlation parameter ρ drives the entire "
        "tranche structure: low ρ benefits senior tranches, high ρ benefits equity. "
        "This was the industry standard for CDO pricing from 2000–2008 and remains "
        "a key reference model."
    )

    when_to_use = [
        "Pricing CDO equity, mezzanine, senior, and super-senior tranches",
        "Understanding correlation sensitivity of CDO tranche spreads",
        "Computing the expected tranche loss and survival profile",
        "Scenario analysis: stress-testing correlation and default intensity",
        "Comparing tranche relative value across the capital structure",
        "Educational: demonstrating the role of correlation in structured credit",
    ]
    when_not_to_use = [
        "When you need a calibrated base-correlation surface (use market-quoted ρ per tranche)",
        "For bespoke tranches on heterogeneous portfolios (extend to name-by-name hazard rates)",
        "Dynamic tranche pricing requiring mark-to-market over time (need stochastic intensity)",
        "When tail dependence is critical — Gaussian Copula has thin joint tails",
        "Single-name CDS pricing (use ISDA standard model)",
        "When exact QuantLib/Markit implementation is needed for production booking",
    ]
    assumptions = [
        "Flat (constant) hazard rate λ — all names are homogeneous",
        "Single pairwise correlation ρ (equicorrelation Gaussian Copula)",
        "Fixed recovery rate R applied equally to all names",
        "Static correlation — no stochastic or contagion effects",
        "Quarterly premium payments on the outstanding tranche notional",
        "Flat yield curve for discounting",
        "Independent loss-given-default across names",
    ]
    limitations = [
        "Gaussian Copula underestimates joint tail events (correlation smile observed in markets)",
        "Equicorrelation is unrealistic for diversified portfolios",
        "A single ρ cannot fit all tranches simultaneously — base correlation needed",
        "Static model: cannot price tranche options or compute forward CDO spreads",
        "Monte Carlo convergence is slow for deep senior tranches (rare events)",
        "No term structure of hazard rates or correlations",
    ]

    formula_latex = (
        r"s = \frac{\sum_k E\!\left[\Delta L^{[\alpha,\delta]}(t_k)\right] e^{-r t_k}}"
        r"{\sum_k E\!\left[(\delta-\alpha)N - L^{[\alpha,\delta]}(t_k)\right] e^{-r t_k} \Delta t}"
        r", \quad L^{[\alpha,\delta]} = \min\!\left(\max\!\left(L - \alpha N, 0\right), (\delta-\alpha)N\right)"
    )
    formula_plain = (
        "Fair Spread = Protection Leg PV / Premium PV01, "
        "where L^[α,δ](t) = tranche loss clipped to [attachment, detachment], "
        "Z_i = √ρ·M + √(1-ρ)·ε_i, τ_i = -ln(Φ(Z_i)) / λ"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Parameters
    # ─────────────────────────────────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "n_names", "Number of Names (N)",
                "Total obligors in the reference portfolio",
                "int", 125, 10, 500, 5,
            ),
            ParameterSpec(
                "hazard_rate", "Flat Hazard Rate (λ)",
                "Annual default intensity applied to all names (≈ spread / (1-R))",
                "float", 0.02, 0.001, 0.50, 0.001,
            ),
            ParameterSpec(
                "recovery_rate", "Recovery Rate (R)",
                "Expected recovery fraction on each default",
                "float", 0.40, 0.0, 0.95, 0.05,
            ),
            ParameterSpec(
                "correlation", "Copula Correlation (ρ)",
                "Gaussian Copula pairwise correlation (0=independent, 1=perfectly correlated)",
                "float", 0.30, 0.0, 0.99, 0.01,
            ),
            ParameterSpec(
                "maturity", "Maturity (T)",
                "CDO maturity in years",
                "float", 5.0, 1.0, 10.0, 1.0, unit="years",
            ),
            ParameterSpec(
                "attachment_point", "Attachment Point (α)",
                "Tranche attachment as fraction of portfolio notional (e.g. 0.03 = 3%)",
                "float", 0.03, 0.0, 0.99, 0.01,
            ),
            ParameterSpec(
                "detachment_point", "Detachment Point (δ)",
                "Tranche detachment as fraction of portfolio notional (e.g. 0.06 = 6%)",
                "float", 0.06, 0.01, 1.0, 0.01,
            ),
            ParameterSpec(
                "notional", "Portfolio Notional",
                "Total reference portfolio notional",
                "float", 125_000_000.0, 1_000_000.0, None, 1_000_000.0, unit="$",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate",
                "Flat discount rate",
                "float", 0.05, 0.0, 0.20, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "n_simulations", "MC Simulations",
                "Number of Monte Carlo paths (higher = more accurate but slower)",
                "int", 50000, 1000, 500000, 5000,
            ),
            ParameterSpec(
                "seed", "Random Seed",
                "Seed for reproducibility",
                "int", 42, 0, 9999, 1,
            ),
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Samples
    # ─────────────────────────────────────────────────────────────────────────

    def get_samples(self) -> dict[str, dict[str, Any]]:
        base = dict(
            n_names=125, hazard_rate=0.01, recovery_rate=0.40,
            correlation=0.30, maturity=5.0, notional=125_000_000,
            r=0.05, n_simulations=50000, seed=42,
        )
        return {
            "Equity Tranche 0–3%": {
                **base,
                "attachment_point": 0.00,
                "detachment_point": 0.03,
            },
            "Mezzanine Tranche 3–6%": {
                **base,
                "attachment_point": 0.03,
                "detachment_point": 0.06,
            },
            "Senior Tranche 6–9%": {
                **base,
                "attachment_point": 0.06,
                "detachment_point": 0.09,
            },
            "Super-Senior Tranche 12–22%": {
                **base,
                "attachment_point": 0.12,
                "detachment_point": 0.22,
            },
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Calculate
    # ─────────────────────────────────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        n_names = int(params["n_names"])
        lam = float(params["hazard_rate"])
        R = float(params["recovery_rate"])
        rho = float(params["correlation"])
        T = float(params["maturity"])
        alpha = float(params["attachment_point"])
        delta = float(params["detachment_point"])
        N = float(params.get("notional", 125_000_000))
        r = float(params.get("r", 0.05))
        n_sims = int(params.get("n_simulations", 50_000))
        seed = int(params.get("seed", 42))

        if alpha >= delta:
            raise ValueError("attachment_point must be strictly less than detachment_point")

        rng = np.random.default_rng(seed)
        steps: list[CalculationStep] = []

        # ── Step 1: Portfolio setup ──────────────────────────────────────────
        loss_per_name = (1.0 - R) * N / n_names
        single_spread_bps = lam * (1.0 - R) * 10_000
        cum_default_prob = 1.0 - math.exp(-lam * T)
        expected_n_defaults = n_names * cum_default_prob
        expected_portfolio_loss_pct = expected_n_defaults * (1.0 - R) / n_names * 100

        steps.append(CalculationStep(
            step_number=1,
            label="Portfolio setup",
            formula=(
                r"Q(T) = e^{-\lambda T},\quad"
                r"E[\text{defaults}] = N \cdot (1-Q(T)),\quad"
                r"s_{\text{single}} \approx \lambda(1-R)"
            ),
            substitution=(
                f"N = {n_names}, λ = {lam}, R = {R}, T = {T}Y\n"
                f"Survival Q(T) = exp(-{lam}×{T}) = {math.exp(-lam * T):.6f}\n"
                f"P(default ≤ T) = {cum_default_prob:.4%}\n"
                f"E[defaults] = {expected_n_defaults:.1f} / {n_names} names\n"
                f"Expected portfolio loss = {expected_portfolio_loss_pct:.2f}%\n"
                f"Single-name spread ≈ {single_spread_bps:.1f} bps\n"
                f"Tranche: [{alpha*100:.1f}%, {delta*100:.1f}%], face = "
                f"${(delta - alpha) * N:,.0f}"
            ),
            result=round(expected_portfolio_loss_pct, 2),
            explanation=(
                "Uniform hazard rates give an exponential survival function. "
                "The expected portfolio loss as a percentage of notional drives "
                "the tranche economics: tranches with attachment above expected loss "
                "are typically senior; below is equity/mezzanine."
            ),
        ))

        # ── Step 2: Correlated default simulation ────────────────────────────
        sqrt_rho = math.sqrt(max(rho, 0.0))
        sqrt_1mrho = math.sqrt(max(1.0 - rho, 0.0))

        tau = _default_times(n_names, lam, rho, n_sims, rng)  # (n_sims, n_names)

        pct_at_least_one_default = float(np.mean(tau.min(axis=1) <= T)) * 100
        avg_defaults_at_T = float(np.mean((tau <= T).sum(axis=1)))

        steps.append(CalculationStep(
            step_number=2,
            label="One-factor Gaussian Copula — correlated default simulation",
            formula=(
                r"Z_i = \sqrt{\rho}\,M + \sqrt{1-\rho}\,\varepsilon_i,\quad"
                r"U_i = \Phi(Z_i),\quad"
                r"\tau_i = -\ln(U_i)/\lambda"
            ),
            substitution=(
                f"ρ = {rho}, √ρ = {sqrt_rho:.4f}, √(1-ρ) = {sqrt_1mrho:.4f}\n"
                f"Paths simulated: {n_sims:,}\n"
                f"Avg defaults by T={T}Y: {avg_defaults_at_T:.2f} / {n_names}\n"
                f"P(≥1 default by T): {pct_at_least_one_default:.1f}%"
            ),
            result=round(avg_defaults_at_T, 2),
            explanation=(
                "The common factor M represents the macro-economic state. "
                "High ρ means names move together — most paths have either "
                "many or few defaults, fattening the tails of the loss distribution."
            ),
        ))

        # ── Step 3: Portfolio loss distribution at maturity ──────────────────
        port_loss_at_T = _portfolio_loss_at(tau, T, R, loss_per_name)
        port_loss_pct_at_T = port_loss_at_T / N * 100

        pct_exceeds_attach = float(np.mean(port_loss_at_T > alpha * N)) * 100
        pct_exceeds_detach = float(np.mean(port_loss_at_T > delta * N)) * 100
        mean_loss_pct = float(np.mean(port_loss_pct_at_T))
        p95_loss_pct = float(np.percentile(port_loss_pct_at_T, 95))
        p99_loss_pct = float(np.percentile(port_loss_pct_at_T, 99))

        # Build histogram of portfolio loss % for diagnostics
        hist_counts, hist_edges = np.histogram(port_loss_pct_at_T, bins=40)
        loss_histogram = [
            {
                "bin_start": round(float(hist_edges[i]), 3),
                "bin_end": round(float(hist_edges[i + 1]), 3),
                "count": int(hist_counts[i]),
            }
            for i in range(len(hist_counts))
        ]

        steps.append(CalculationStep(
            step_number=3,
            label="Portfolio loss distribution at maturity",
            formula=(
                r"L(T) = \frac{(1-R)}{N}\sum_{i=1}^{N} \mathbf{1}_{\{\tau_i \le T\}} \times N_{\text{portfolio}}"
            ),
            substitution=(
                f"Mean loss: {mean_loss_pct:.3f}%\n"
                f"95th pct loss: {p95_loss_pct:.3f}%\n"
                f"99th pct loss: {p99_loss_pct:.3f}%\n"
                f"P(loss > attachment {alpha*100:.1f}%): {pct_exceeds_attach:.2f}%\n"
                f"P(loss > detachment {delta*100:.1f}%): {pct_exceeds_detach:.2f}%"
            ),
            result=round(mean_loss_pct, 3),
            explanation=(
                "The portfolio loss distribution at maturity shows the "
                "probability of breaching tranche boundaries. "
                "P(L > attachment) is the probability of any tranche loss; "
                "P(L > detachment) is the probability of full tranche wipeout."
            ),
        ))

        # ── Step 4: Tranche loss computation ────────────────────────────────
        tranche_face = (delta - alpha) * N
        tranche_loss_at_T = _tranche_loss(port_loss_at_T, alpha, delta, N)

        expected_tranche_loss = float(np.mean(tranche_loss_at_T))
        expected_tranche_loss_pct = expected_tranche_loss / tranche_face * 100 if tranche_face > 0 else 0.0
        prob_full_wipeout = float(np.mean(tranche_loss_at_T >= tranche_face - 1e-6)) * 100
        prob_any_loss = float(np.mean(tranche_loss_at_T > 0)) * 100

        steps.append(CalculationStep(
            step_number=4,
            label="Tranche loss profile",
            formula=(
                r"L^{[\alpha,\delta]}(T) = \min\!\left(\max\!\left(L(T) - \alpha N,\,0\right),\,(\delta-\alpha)N\right)"
            ),
            substitution=(
                f"Tranche [{alpha*100:.1f}%, {delta*100:.1f}%], face = ${tranche_face:,.0f}\n"
                f"E[tranche loss at T] = ${expected_tranche_loss:,.0f} "
                f"({expected_tranche_loss_pct:.2f}% of face)\n"
                f"P(any tranche loss): {prob_any_loss:.2f}%\n"
                f"P(full wipeout): {prob_full_wipeout:.2f}%"
            ),
            result=round(expected_tranche_loss_pct, 2),
            explanation=(
                "The tranche loss clips the portfolio loss to the [attachment, detachment] "
                "window. Equity tranches (low attachment) absorb first-loss risk and "
                "have the highest P(any loss); super-senior tranches almost never lose "
                "under base-case assumptions."
            ),
        ))

        # ── Step 5: Protection leg (expected tranche loss PV) ────────────────
        prot_pv, prem_pv01, fair_spread_bps, loss_timeline = _price_tranche(
            tau, R, alpha, delta, N, T, r
        )

        steps.append(CalculationStep(
            step_number=5,
            label="Protection leg PV (expected tranche loss)",
            formula=(
                r"\text{ProtPV} = \sum_{k} E\!\left[\Delta L^{[\alpha,\delta]}(t_k)\right] e^{-r t_k}"
            ),
            substitution=(
                f"Quarterly payments: {int(T * 4)} dates\n"
                f"Protection PV = ${prot_pv:,.2f}\n"
                f"As % of tranche face (${tranche_face:,.0f}): "
                f"{prot_pv / tranche_face * 100:.4f}%\n"
                f"Discount rate: {r*100:.1f}%"
            ),
            result=round(prot_pv, 2),
            explanation=(
                "The protection leg is the present value of all expected tranche "
                "losses, each discounted to today. This is the total expected payout "
                "the protection seller bears, analogous to the loss-given-default PV "
                "in a single-name CDS but now clipped to the tranche boundaries."
            ),
        ))

        # ── Step 6: Premium leg PV01 ─────────────────────────────────────────
        steps.append(CalculationStep(
            step_number=6,
            label="Premium leg PV01 (risky outstanding tranche notional)",
            formula=(
                r"\text{PV01} = \sum_k E\!\left[(\delta-\alpha)N - L^{[\alpha,\delta]}(t_k)\right]"
                r"e^{-r t_k}\,\Delta t"
            ),
            substitution=(
                f"PV01 = ${prem_pv01:,.2f}\n"
                f"Tranche face: ${tranche_face:,.0f}\n"
                f"PV01 / face: {prem_pv01 / tranche_face:.4f}\n"
                f"Risk-free annuity (no default): "
                f"{sum(math.exp(-r * t) * 0.25 for t in np.arange(0.25, T + 0.01, 0.25)) * tranche_face:,.2f}"
            ),
            result=round(prem_pv01, 2),
            explanation=(
                "The premium leg PV01 is the expected discounted area under the "
                "outstanding tranche notional. As tranche losses accumulate, the "
                "premium notional shrinks. For super-senior tranches this barely "
                "differs from the risk-free annuity; for equity it decays quickly."
            ),
        ))

        # ── Step 7: Fair spread and Greeks ───────────────────────────────────
        # CS01: sensitivity to 1% change in correlation (ρ → ρ + 0.01)
        rho_bumped = min(rho + 0.01, 0.98)
        rng_bump = np.random.default_rng(seed)
        tau_rho_up = _default_times(n_names, lam, rho_bumped, n_sims, rng_bump)
        _, _, spread_rho_up, _ = _price_tranche(
            tau_rho_up, R, alpha, delta, N, T, r
        )
        rho_sensitivity = spread_rho_up - fair_spread_bps  # per 1% rho increase

        # Spread CS01: sensitivity to 1bp increase in hazard rate (equivalent to ~1bp single-name spread)
        lam_bumped = lam + 0.0001  # +1bp in hazard rate
        rng_cs01 = np.random.default_rng(seed)
        tau_lam_up = _default_times(n_names, lam_bumped, rho, n_sims, rng_cs01)
        _, _, spread_lam_up, _ = _price_tranche(
            tau_lam_up, R, alpha, delta, N, T, r
        )
        spread_cs01_bps = spread_lam_up - fair_spread_bps  # per 1bp hazard rate move

        # Tranche leverage: ratio of tranche spread sensitivity to portfolio spread sensitivity
        leverage = abs(spread_cs01_bps / (lam * (1 - R))) if lam > 0 else 0.0

        steps.append(CalculationStep(
            step_number=7,
            label="Fair tranche spread + Greeks",
            formula=(
                r"s = \frac{\text{ProtPV}}{\text{PV01}} \times 10000 \text{ bps},\quad"
                r"\text{CS01} \approx \frac{\partial s}{\partial \lambda},\quad"
                r"\text{Rho-Sensitivity} = \frac{\partial s}{\partial \rho}\bigg|_{\Delta\rho=1\%}"
            ),
            substitution=(
                f"Fair spread = {prot_pv:,.2f} / {prem_pv01:,.2f} × 10,000\n"
                f"            = {fair_spread_bps:.2f} bps\n"
                f"Rho-sensitivity (Δρ=+1%): {rho_sensitivity:+.2f} bps\n"
                f"Spread CS01 (Δλ=+1bp):    {spread_cs01_bps:+.2f} bps\n"
                f"Tranche leverage vs single-name: {leverage:.2f}x"
            ),
            result=round(fair_spread_bps, 2),
            explanation=(
                "The fair spread is the annual premium (in bps) on the outstanding "
                "tranche notional that makes the CDO tranche have zero value at "
                "inception. Rho-sensitivity shows how sensitive equity tranches are "
                "to correlation (positive = equity widens as ρ rises). "
                "Spread CS01 is the tranche repricing per 1bp move in the underlying "
                "single-name hazard rates."
            ),
        ))

        greeks = {
            "rho_sensitivity_bps_per_pct": round(rho_sensitivity, 4),
            "spread_cs01_bps": round(spread_cs01_bps, 4),
            "tranche_leverage": round(leverage, 4),
        }

        return SimulatorResult(
            fair_value=round(fair_spread_bps, 2),
            method=(
                f"Gaussian Copula MC — {n_sims:,} sims, {n_names} names, "
                f"ρ={rho}, [{alpha*100:.1f}%–{delta*100:.1f}%]"
            ),
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "fair_spread_bps": round(fair_spread_bps, 2),
                "protection_pv": round(prot_pv, 4),
                "premium_pv01": round(prem_pv01, 4),
                "tranche_face": round(tranche_face, 0),
                "expected_tranche_loss_pct": round(expected_tranche_loss_pct, 4),
                "prob_any_loss_pct": round(prob_any_loss, 2),
                "prob_full_wipeout_pct": round(prob_full_wipeout, 2),
                "expected_portfolio_loss_pct": round(mean_loss_pct, 4),
                "p95_portfolio_loss_pct": round(p95_loss_pct, 4),
                "p99_portfolio_loss_pct": round(p99_loss_pct, 4),
                "single_name_spread_bps": round(single_spread_bps, 2),
                "rho_sensitivity_bps_per_pct": round(rho_sensitivity, 4),
                "spread_cs01_bps": round(spread_cs01_bps, 4),
                "tranche_leverage": round(leverage, 4),
                "loss_histogram": loss_histogram,
                "loss_timeline": loss_timeline,
            },
        )

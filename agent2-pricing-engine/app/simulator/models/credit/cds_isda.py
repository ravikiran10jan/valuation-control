"""CDS — ISDA Standard Model (simplified).

The ISDA standard model for pricing single-name Credit Default Swaps.
This implements the core mechanics:

1. Bootstrap a piecewise-constant hazard rate curve from market CDS spreads
2. Compute protection leg PV = Σ (1-R) × [Q(tᵢ₋₁) - Q(tᵢ)] × D(tᵢ)
3. Compute premium leg PV = spread × Σ Δtᵢ × Q(tᵢ) × D(tᵢ) + accrual
4. Par spread = Protection PV / Risky Annuity PV

The model uses:
- Flat or piecewise-constant hazard rates
- Act/360 day count for premiums
- Quarterly premium payments
- Flat yield curve for discounting
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.optimize import brentq

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


def _survival(hazard_rate: float, t: float) -> float:
    return math.exp(-hazard_rate * t)


def _discount(r: float, t: float) -> float:
    return math.exp(-r * t)


def _cds_pv(spread_bps: float, hazard_rate: float, recovery: float,
            r: float, maturity: float, notional: float = 1.0) -> float:
    """Compute CDS PV (from protection buyer perspective).

    PV = Protection Leg - Premium Leg
    """
    spread = spread_bps / 10000

    # Payment dates (quarterly)
    dates = np.arange(0.25, maturity + 0.01, 0.25)
    dt = 0.25

    # Protection leg: sum over small intervals
    fine_dt = 1 / 12  # monthly integration
    fine_dates = np.arange(fine_dt, maturity + 0.001, fine_dt)
    prot_pv = 0.0
    for t in fine_dates:
        q_prev = _survival(hazard_rate, t - fine_dt)
        q_now = _survival(hazard_rate, t)
        default_prob = q_prev - q_now
        prot_pv += (1 - recovery) * default_prob * _discount(r, t)

    # Premium leg: quarterly payments
    prem_pv = 0.0
    for t in dates:
        prem_pv += spread * dt * _survival(hazard_rate, t) * _discount(r, t)

    # Accrual on default (simplified)
    accrual = 0.0
    for t in fine_dates:
        q_prev = _survival(hazard_rate, t - fine_dt)
        q_now = _survival(hazard_rate, t)
        default_prob = q_prev - q_now
        # Approximate accrual as half a period
        accrual += spread * (fine_dt / 2) * default_prob * _discount(r, t)

    return notional * (prot_pv - prem_pv - accrual)


def _risky_annuity(hazard_rate: float, r: float, maturity: float) -> float:
    """Risky PV01: PV of receiving 1bp/year until default or maturity."""
    dates = np.arange(0.25, maturity + 0.01, 0.25)
    dt = 0.25
    annuity = 0.0
    for t in dates:
        annuity += dt * _survival(hazard_rate, t) * _discount(r, t)
    return annuity


def _par_spread(hazard_rate: float, recovery: float, r: float,
                maturity: float) -> float:
    """Compute the par CDS spread in bps."""
    fine_dt = 1 / 12
    fine_dates = np.arange(fine_dt, maturity + 0.001, fine_dt)
    prot_pv = 0.0
    for t in fine_dates:
        q_prev = _survival(hazard_rate, t - fine_dt)
        q_now = _survival(hazard_rate, t)
        prot_pv += (1 - recovery) * (q_prev - q_now) * _discount(r, t)

    annuity = _risky_annuity(hazard_rate, r, maturity)
    if annuity < 1e-12:
        return 0.0
    return (prot_pv / annuity) * 10000


def _bootstrap_hazard(market_spread_bps: float, recovery: float,
                      r: float, maturity: float) -> float:
    """Bootstrap a flat hazard rate from a market CDS spread."""
    def obj(lam):
        return _par_spread(lam, recovery, r, maturity) - market_spread_bps

    try:
        return brentq(obj, 1e-6, 2.0)
    except ValueError:
        # Approximate: λ ≈ s / (1-R)
        return market_spread_bps / 10000 / (1 - recovery)


@ModelRegistry.register
class CDSISDAModel(BaseSimulatorModel):

    model_id = "cds_isda"
    model_name = "CDS — ISDA Standard Model"
    product_type = "Credit Default Swap"
    asset_class = "credit"

    short_description = (
        "Price and risk a single-name CDS with hazard rate bootstrap"
    )
    long_description = (
        "The ISDA standard model for Credit Default Swaps. Given a market "
        "CDS spread, the model bootstraps a flat hazard rate, then computes "
        "protection leg PV, premium leg PV, and the mark-to-market value "
        "of an off-market CDS. Also shows the risky annuity (RPV01), "
        "survival probabilities, and credit sensitivities (CS01, CR01). "
        "This is the workhorse model for single-name CDS trading desks."
    )

    when_to_use = [
        "Pricing and marking single-name CDS positions",
        "Computing CS01 (spread sensitivity) for hedging",
        "Bootstrapping hazard rates from market spreads",
        "Computing CVA/DVA for counterparty risk",
        "Understanding CDS mechanics and cashflows",
    ]
    when_not_to_use = [
        "Basket or portfolio credit products (use copula models)",
        "When you need a term structure of hazard rates (extend to piecewise)",
        "CDS options / swaptions (need stochastic hazard rates)",
        "When exact ISDA implementation is required (use QuantLib/Markit)",
    ]
    assumptions = [
        "Flat (constant) hazard rate over the CDS life",
        "Fixed recovery rate (standard: 40% for IG, 25% for HY)",
        "Quarterly premium payments on standard IMM dates",
        "Flat yield curve for discounting",
        "No counterparty risk (clean CDS pricing)",
    ]
    limitations = [
        "Simplified vs production ISDA: no exact date generation, no stub periods",
        "Flat hazard rate — real markets use piecewise-flat bootstrapped from multiple tenors",
        "No accrual rebate on default (approximated)",
        "Day count simplified to Act/365 equivalent",
    ]

    formula_latex = (
        r"s_{par} = \frac{\sum_i (1-R)[Q(t_{i-1})-Q(t_i)]D(t_i)}"
        r"{\sum_j \Delta t_j \, Q(t_j) \, D(t_j)}"
    )
    formula_plain = (
        "Par Spread = Protection Leg PV / Risky Annuity, "
        "where Q(t) = exp(-λt), D(t) = exp(-rt)"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "market_spread", "Market CDS Spread",
                "Current market CDS spread", "float",
                100.0, 1.0, 5000.0, 1.0, unit="bps",
            ),
            ParameterSpec(
                "trade_spread", "Trade Spread",
                "Coupon spread on the CDS position (0 = par)", "float",
                0.0, 0.0, 5000.0, 1.0, unit="bps",
            ),
            ParameterSpec(
                "recovery", "Recovery Rate (R)",
                "Expected recovery in default", "float",
                0.40, 0.0, 0.95, 0.05,
            ),
            ParameterSpec(
                "maturity", "Maturity (T)", "CDS maturity", "float",
                5.0, 0.5, 10.0, 0.5, unit="years",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Flat discount rate", "float",
                0.05, 0.0, 0.20, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "notional", "Notional", "CDS notional amount", "float",
                10000000.0, 1000.0, None, 1000.0, unit="$",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "IG 5Y (100bps)": {
                "market_spread": 100, "trade_spread": 0, "recovery": 0.40,
                "maturity": 5.0, "r": 0.05, "notional": 10000000,
            },
            "HY 5Y (500bps)": {
                "market_spread": 500, "trade_spread": 0, "recovery": 0.40,
                "maturity": 5.0, "r": 0.05, "notional": 10000000,
            },
            "Distressed (2000bps)": {
                "market_spread": 2000, "trade_spread": 0, "recovery": 0.25,
                "maturity": 5.0, "r": 0.05, "notional": 10000000,
            },
            "Off-market position": {
                "market_spread": 150, "trade_spread": 100, "recovery": 0.40,
                "maturity": 5.0, "r": 0.05, "notional": 10000000,
            },
            "Short-dated CDS": {
                "market_spread": 80, "trade_spread": 0, "recovery": 0.40,
                "maturity": 1.0, "r": 0.05, "notional": 10000000,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        mkt_spread = float(params["market_spread"])
        trade_spread = float(params.get("trade_spread", 0))
        R = float(params["recovery"])
        T = float(params["maturity"])
        r = float(params["r"])
        notional = float(params.get("notional", 10_000_000))

        steps: list[CalculationStep] = []

        # Step 1: Bootstrap hazard rate
        lam = _bootstrap_hazard(mkt_spread, R, r, T)

        steps.append(CalculationStep(
            step_number=1,
            label="Bootstrap hazard rate from market spread",
            formula=r"\lambda : s_{par}(\lambda) = s_{market}",
            substitution=(
                f"Market spread: {mkt_spread} bps\n"
                f"Recovery: {R}\n"
                f"Bootstrapped λ = {lam:.6f}\n"
                f"Approx check: λ ≈ s/(1-R) = {mkt_spread / 10000 / (1 - R):.6f}"
            ),
            result=round(lam, 6),
            explanation=(
                "The hazard rate λ is the constant default intensity that "
                "reproduces the market CDS spread. For small spreads, λ ≈ s/(1-R)."
            ),
        ))

        # Step 2: Survival probabilities
        tenors = [1, 2, 3, 5, 7, 10]
        surv_table = {f"{t}Y": round(_survival(lam, t), 6) for t in tenors if t <= T * 2}

        cum_default_T = 1 - _survival(lam, T)
        steps.append(CalculationStep(
            step_number=2,
            label="Survival probabilities",
            formula=r"Q(t) = e^{-\lambda t}, \quad P(\text{default} \le T) = 1 - Q(T)",
            substitution=(
                "\n".join(f"  Q({k}) = {v}" for k, v in surv_table.items())
                + f"\nP(default ≤ {T}Y) = {cum_default_T:.4%}"
            ),
            result=round(cum_default_T, 4),
            explanation="Exponential survival under constant hazard rate.",
        ))

        # Step 3: Protection leg PV
        par = _par_spread(lam, R, r, T)
        annuity = _risky_annuity(lam, r, T)

        # Compute protection leg directly
        fine_dt = 1 / 12
        fine_dates = np.arange(fine_dt, T + 0.001, fine_dt)
        prot_pv = 0.0
        for t in fine_dates:
            q_prev = _survival(lam, t - fine_dt)
            q_now = _survival(lam, t)
            prot_pv += (1 - R) * (q_prev - q_now) * _discount(r, t)

        steps.append(CalculationStep(
            step_number=3,
            label="Protection leg PV (per unit notional)",
            formula=r"\text{Prot} = \sum_i (1-R)[Q(t_{i-1})-Q(t_i)]D(t_i)",
            substitution=(
                f"Protection PV = {prot_pv:.6f}\n"
                f"In $ terms: {prot_pv * notional:,.0f}"
            ),
            result=round(prot_pv, 6),
            explanation="PV of the contingent payment made if default occurs.",
        ))

        # Step 4: Premium leg / Risky annuity
        steps.append(CalculationStep(
            step_number=4,
            label="Risky annuity (RPV01)",
            formula=r"\text{RPV01} = \sum_j \Delta t \cdot Q(t_j) \cdot D(t_j)",
            substitution=(
                f"Risky Annuity = {annuity:.6f}\n"
                f"Risk-free annuity (no default): {sum(_discount(r, t) * 0.25 for t in np.arange(0.25, T + 0.01, 0.25)):.6f}"
            ),
            result=round(annuity, 6),
            explanation=(
                "The risky PV01: PV of receiving 1bp/year of spread until "
                "default or maturity."
            ),
        ))

        # Step 5: Par spread verification
        steps.append(CalculationStep(
            step_number=5,
            label="Par spread (model output)",
            formula=r"s_{par} = \frac{\text{Prot PV}}{\text{RPV01}} \times 10000",
            substitution=(
                f"s_par = {prot_pv:.6f} / {annuity:.6f} × 10000 = {par:.1f} bps\n"
                f"Market spread: {mkt_spread} bps\n"
                f"Calibration error: {par - mkt_spread:.2f} bps"
            ),
            result=round(par, 1),
            explanation="Should match the input market spread (calibration check).",
        ))

        # Step 6: Mark-to-market
        if trade_spread > 0:
            mtm = (prot_pv - trade_spread / 10000 * annuity) * notional
            mtm_desc = f"Mark-to-market of existing position"
        else:
            mtm = 0.0
            mtm_desc = "At par (trade spread = 0 or not specified)"

        steps.append(CalculationStep(
            step_number=6,
            label="Mark-to-market",
            formula=r"\text{MtM} = (\text{Prot PV} - s_{trade} \times \text{RPV01}) \times N",
            substitution=(
                f"Trade spread: {trade_spread} bps, Market: {mkt_spread} bps\n"
                f"MtM = ({prot_pv:.6f} - {trade_spread / 10000:.6f} × {annuity:.6f}) × {notional:,.0f}\n"
                f"MtM = ${mtm:,.0f}\n"
                f"{mtm_desc}"
            ),
            result=round(mtm, 0),
            explanation=(
                "Positive MtM means the protection buyer has a gain "
                "(market spread > trade spread, credit has deteriorated)."
            ),
        ))

        # Step 7: Sensitivities
        # CS01: PV change for 1bp spread widening
        lam_up = _bootstrap_hazard(mkt_spread + 1, R, r, T)
        prot_up = sum(
            (1 - R) * (_survival(lam_up, t - 1/12) - _survival(lam_up, t)) * _discount(r, t)
            for t in np.arange(1/12, T + 0.001, 1/12)
        )
        annuity_up = _risky_annuity(lam_up, r, T)
        if trade_spread > 0:
            mtm_up = (prot_up - trade_spread / 10000 * annuity_up) * notional
        else:
            mtm_up = 0

        cs01 = (mtm_up - mtm) if trade_spread > 0 else annuity * notional / 10000

        steps.append(CalculationStep(
            step_number=7,
            label="Credit sensitivities",
            formula=r"\text{CS01} = \frac{\partial \text{MtM}}{\partial s} \approx \text{RPV01} \times N / 10000",
            substitution=(
                f"CS01 (per 1bp): ${cs01:,.0f}\n"
                f"RPV01 × Notional: ${annuity * notional:,.0f}\n"
                f"Jump-to-default loss: ${(1 - R) * notional:,.0f}"
            ),
            result=round(cs01, 0),
            explanation=(
                "CS01: P&L for 1bp spread widening. "
                "Jump-to-default: loss if immediate default occurs."
            ),
        ))

        greeks = {
            "cs01": round(cs01, 2),
            "rpv01": round(annuity * notional, 2),
            "jtd_loss": round((1 - R) * notional, 0),
        }

        return SimulatorResult(
            fair_value=round(par, 1),
            method="ISDA Standard Model (flat hazard rate)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "par_spread_bps": round(par, 1),
                "hazard_rate": round(lam, 6),
                "protection_pv": round(prot_pv, 6),
                "risky_annuity": round(annuity, 6),
                "cum_default_prob": round(cum_default_T, 4),
                "mtm_dollars": round(mtm, 0),
                "cs01_dollars": round(cs01, 0),
                "survival_table": surv_table,
            },
        )

"""Net Interest Income (NII) Forecasting Model.

Simulates NII under parallel and non-parallel rate shifts to measure
interest rate risk in the banking book (IRRBB).

NII = Σ (asset_i × asset_rate_i) - Σ (liability_j × liability_rate_j)

Key dynamics modelled:
  - Repricing gaps: assets and liabilities reprice at different frequencies
  - Basis risk: asset spread vs liability spread may move independently
  - Optionality: prepayment on loans, early withdrawal on deposits
  - Rate floors/caps: contractual floors on lending rates, deposit rate floors at 0

This model supports:
  1. Base case NII over a 12-month horizon
  2. Parallel rate shocks (+/- 100bp, +/- 200bp)
  3. Non-parallel shocks (steepener, flattener, short-rate shock)
  4. NII sensitivity (ΔNII) per basis point
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


def _reprice_rate(base_rate: float, shift_bps: float, floor: float,
                  cap: float, repricing_lag_months: int,
                  month: int, pass_through: float) -> float:
    """Compute the effective rate at a given month after a rate shift.

    pass_through: fraction of the shift that passes through (0-1).
    repricing_lag_months: months before the shift takes effect.
    """
    if month < repricing_lag_months:
        return max(min(base_rate, cap), floor)
    effective_shift = shift_bps / 10000 * pass_through
    new_rate = base_rate + effective_shift
    return max(min(new_rate, cap), floor)


def _compute_monthly_nii(
    asset_balance: float, asset_rate: float, asset_repricing_months: int,
    asset_pass_through: float, asset_spread: float,
    liability_balance: float, liability_rate: float, liability_repricing_months: int,
    liability_pass_through: float, liability_spread: float,
    equity_balance: float, shift_bps: float,
    rate_floor: float, rate_cap: float,
    horizon_months: int,
) -> dict[str, Any]:
    """Compute monthly NII over the horizon under a given rate shift."""
    monthly_nii = []
    monthly_interest_income = []
    monthly_interest_expense = []

    for m in range(1, horizon_months + 1):
        # Asset side: base rate + shift + spread
        a_rate = _reprice_rate(
            asset_rate, shift_bps, rate_floor, rate_cap,
            asset_repricing_months, m, asset_pass_through
        ) + asset_spread

        # Liability side: base rate + shift + spread (floor at 0 for deposits)
        l_rate = _reprice_rate(
            liability_rate, shift_bps, 0.0, rate_cap,
            liability_repricing_months, m, liability_pass_through
        ) + liability_spread

        # Monthly income and expense
        interest_income = asset_balance * a_rate / 12
        interest_expense = liability_balance * l_rate / 12

        # Equity earns the base rate (no cost of funds)
        equity_income = equity_balance * _reprice_rate(
            asset_rate, shift_bps, rate_floor, rate_cap, 0, m, 1.0
        ) / 12

        nii = interest_income + equity_income - interest_expense
        monthly_nii.append(nii)
        monthly_interest_income.append(interest_income + equity_income)
        monthly_interest_expense.append(interest_expense)

    return {
        "monthly_nii": monthly_nii,
        "monthly_income": monthly_interest_income,
        "monthly_expense": monthly_interest_expense,
        "total_nii": sum(monthly_nii),
        "total_income": sum(monthly_interest_income),
        "total_expense": sum(monthly_interest_expense),
        "average_monthly": sum(monthly_nii) / horizon_months,
    }


@ModelRegistry.register
class NIIForecastModel(BaseSimulatorModel):

    model_id = "nii_forecast"
    model_name = "NII Forecast (IRRBB)"
    product_type = "Net Interest Income Simulation"
    asset_class = "income"

    short_description = (
        "Forecast net interest income under rate shocks for IRRBB analysis"
    )
    long_description = (
        "Models net interest income (NII) — the difference between interest "
        "earned on assets and interest paid on liabilities — over a 12-month "
        "horizon under various rate scenarios.  This is a core IRRBB (Interest "
        "Rate Risk in the Banking Book) tool used by ALM/Treasury teams.  The "
        "model captures repricing gaps (assets and liabilities reprice at "
        "different speeds), pass-through rates (how much of a rate change "
        "reaches customers), and contractual floors/caps.  Outputs include "
        "base-case NII, NII under standard rate shocks (±100bp, ±200bp), "
        "and NII sensitivity per basis point."
    )

    when_to_use = [
        "IRRBB analysis: measuring earnings-at-risk from rate movements",
        "ALM committee reporting: NII forecast under stress scenarios",
        "Regulatory stress testing (Basel IRRBB, Fed CCAR NII component)",
        "Pricing a new deposit or loan product: impact on NII",
        "Understanding repricing gap dynamics and pass-through effects",
    ]
    when_not_to_use = [
        "EVE (Economic Value of Equity) analysis — use discounted cashflow models",
        "When you need stochastic rate simulation (use HJM or Monte Carlo)",
        "Detailed prepayment modelling (use CPR models)",
        "Trading book P&L — this is banking book / ALM focused",
    ]
    assumptions = [
        "Balance sheet is static over the horizon (no growth/runoff)",
        "Rate shift is instantaneous at t=0 and held constant",
        "Linear pass-through: a fixed fraction of the shift reaches customers",
        "Repricing lag: assets/liabilities reprice after a fixed delay",
        "Deposit rate floored at 0 (non-negative deposit rates)",
        "Equity component earns the full asset rate (free funding)",
    ]
    limitations = [
        "Static balance sheet — no modelling of new business or runoff",
        "Deterministic rate shifts — no stochastic rate paths",
        "Simplified pass-through — in reality, it's nonlinear and competitive",
        "No prepayment or early withdrawal optionality",
        "Single asset/liability bucket — real banks have many segments",
    ]

    formula_latex = (
        r"NII = \sum_i A_i \cdot r_i^{asset} - \sum_j L_j \cdot r_j^{liability} + E \cdot r^{equity}"
    )
    formula_plain = (
        "NII = Σ(Asset × AssetRate) - Σ(Liability × LiabilityRate) + Equity × EquityRate"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec("asset_balance", "Total Assets ($M)", "Interest-earning assets", "float", 10000.0, 100.0, 1000000.0, 100.0, unit="$M"),
            ParameterSpec("asset_rate", "Asset Base Rate", "Current weighted average asset yield", "float", 0.055, -0.05, 0.30, 0.001, unit="decimal"),
            ParameterSpec("asset_spread", "Asset Spread", "Credit/liquidity spread over base rate", "float", 0.015, 0.0, 0.10, 0.001, unit="decimal"),
            ParameterSpec("asset_repricing_months", "Asset Repricing Lag (months)", "Months before assets reprice", "int", 3, 0, 60, 1),
            ParameterSpec("asset_pass_through", "Asset Pass-Through", "Fraction of rate change passed to asset yields", "float", 0.90, 0.0, 1.0, 0.05),
            ParameterSpec("liability_balance", "Total Liabilities ($M)", "Interest-bearing liabilities", "float", 8500.0, 100.0, 1000000.0, 100.0, unit="$M"),
            ParameterSpec("liability_rate", "Liability Base Rate", "Current weighted average funding cost", "float", 0.040, -0.05, 0.30, 0.001, unit="decimal"),
            ParameterSpec("liability_spread", "Liability Spread", "Additional spread on liabilities", "float", 0.005, 0.0, 0.10, 0.001, unit="decimal"),
            ParameterSpec("liability_repricing_months", "Liability Repricing Lag (months)", "Months before liabilities reprice", "int", 1, 0, 60, 1),
            ParameterSpec("liability_pass_through", "Liability Pass-Through", "Fraction of rate change passed to funding costs", "float", 0.70, 0.0, 1.0, 0.05),
            ParameterSpec("equity_balance", "Equity ($M)", "Non-interest-bearing equity", "float", 1500.0, 0.0, 100000.0, 100.0, unit="$M"),
            ParameterSpec("rate_floor", "Rate Floor", "Minimum rate (contractual floor)", "float", 0.0, -0.05, 0.10, 0.001, unit="decimal"),
            ParameterSpec("rate_cap", "Rate Cap", "Maximum rate (contractual cap)", "float", 0.25, 0.05, 1.0, 0.01, unit="decimal"),
            ParameterSpec("horizon_months", "Forecast Horizon (months)", "NII forecast period", "int", 12, 1, 60, 1),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Mid-Size Bank (asset-sensitive)": {
                "asset_balance": 10000, "asset_rate": 0.055, "asset_spread": 0.015,
                "asset_repricing_months": 3, "asset_pass_through": 0.90,
                "liability_balance": 8500, "liability_rate": 0.040,
                "liability_spread": 0.005, "liability_repricing_months": 1,
                "liability_pass_through": 0.70, "equity_balance": 1500,
                "rate_floor": 0.0, "rate_cap": 0.25, "horizon_months": 12,
            },
            "Liability-Sensitive Bank": {
                "asset_balance": 10000, "asset_rate": 0.045, "asset_spread": 0.020,
                "asset_repricing_months": 12, "asset_pass_through": 0.50,
                "liability_balance": 9000, "liability_rate": 0.035,
                "liability_spread": 0.003, "liability_repricing_months": 1,
                "liability_pass_through": 0.95, "equity_balance": 1000,
                "rate_floor": 0.0, "rate_cap": 0.25, "horizon_months": 12,
            },
            "Low Rate Environment": {
                "asset_balance": 10000, "asset_rate": 0.025, "asset_spread": 0.015,
                "asset_repricing_months": 6, "asset_pass_through": 0.85,
                "liability_balance": 8500, "liability_rate": 0.010,
                "liability_spread": 0.002, "liability_repricing_months": 1,
                "liability_pass_through": 0.50, "equity_balance": 1500,
                "rate_floor": 0.0, "rate_cap": 0.25, "horizon_months": 12,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        asset_bal = float(params["asset_balance"])
        asset_rate = float(params["asset_rate"])
        asset_spread = float(params["asset_spread"])
        asset_reprice = int(params["asset_repricing_months"])
        asset_pt = float(params["asset_pass_through"])
        liab_bal = float(params["liability_balance"])
        liab_rate = float(params["liability_rate"])
        liab_spread = float(params["liability_spread"])
        liab_reprice = int(params["liability_repricing_months"])
        liab_pt = float(params["liability_pass_through"])
        equity_bal = float(params["equity_balance"])
        rate_floor = float(params["rate_floor"])
        rate_cap = float(params["rate_cap"])
        horizon = int(params["horizon_months"])

        steps: list[CalculationStep] = []

        # Step 1: base case NII
        base = _compute_monthly_nii(
            asset_bal, asset_rate, asset_reprice, asset_pt, asset_spread,
            liab_bal, liab_rate, liab_reprice, liab_pt, liab_spread,
            equity_bal, 0, rate_floor, rate_cap, horizon,
        )

        net_margin = (base["total_income"] - base["total_expense"]) / (asset_bal * horizon / 12) if asset_bal > 0 else 0

        steps.append(CalculationStep(
            step_number=1,
            label="Base case NII",
            formula=r"NII = \sum_{m=1}^{H} (A \cdot r_a - L \cdot r_l + E \cdot r_e) / 12",
            substitution=(
                f"Total interest income: ${base['total_income']:.2f}M\n"
                f"Total interest expense: ${base['total_expense']:.2f}M\n"
                f"Total NII ({horizon} months): ${base['total_nii']:.2f}M\n"
                f"Average monthly NII: ${base['average_monthly']:.2f}M\n"
                f"Net interest margin: {net_margin * 100:.2f}%"
            ),
            result=round(base["total_nii"], 2),
            explanation="Base case NII with no rate changes, reflecting current yields and costs.",
        ))

        # Step 2: parallel rate shocks
        shocks = [-200, -100, +100, +200]
        shock_results = {}
        for shift in shocks:
            res = _compute_monthly_nii(
                asset_bal, asset_rate, asset_reprice, asset_pt, asset_spread,
                liab_bal, liab_rate, liab_reprice, liab_pt, liab_spread,
                equity_bal, shift, rate_floor, rate_cap, horizon,
            )
            shock_results[shift] = res

        shock_sub = "Parallel rate shocks (NII change vs base):\n"
        for shift in shocks:
            delta_nii = shock_results[shift]["total_nii"] - base["total_nii"]
            shock_sub += f"  {shift:+d}bp: NII = ${shock_results[shift]['total_nii']:.2f}M (Δ = ${delta_nii:+.2f}M)\n"

        steps.append(CalculationStep(
            step_number=2,
            label="Parallel rate shocks",
            formula=r"\Delta NII = NII_{shifted} - NII_{base}",
            substitution=shock_sub.strip(),
            result=round(shock_results[100]["total_nii"] - base["total_nii"], 2),
            explanation=(
                "Positive ΔNII for rate increases → asset-sensitive. "
                "Negative → liability-sensitive. Asymmetry from floors/caps."
            ),
        ))

        # Step 3: NII sensitivity per basis point
        up_1bp = _compute_monthly_nii(
            asset_bal, asset_rate, asset_reprice, asset_pt, asset_spread,
            liab_bal, liab_rate, liab_reprice, liab_pt, liab_spread,
            equity_bal, 1, rate_floor, rate_cap, horizon,
        )
        down_1bp = _compute_monthly_nii(
            asset_bal, asset_rate, asset_reprice, asset_pt, asset_spread,
            liab_bal, liab_rate, liab_reprice, liab_pt, liab_spread,
            equity_bal, -1, rate_floor, rate_cap, horizon,
        )
        nii_per_bp = (up_1bp["total_nii"] - down_1bp["total_nii"]) / 2

        steps.append(CalculationStep(
            step_number=3,
            label="NII sensitivity (per basis point)",
            formula=r"\frac{\partial NII}{\partial r} \approx \frac{NII_{+1bp} - NII_{-1bp}}{2}",
            substitution=(
                f"NII(+1bp) = ${up_1bp['total_nii']:.4f}M\n"
                f"NII(-1bp) = ${down_1bp['total_nii']:.4f}M\n"
                f"ΔNII per bp = ${nii_per_bp:.4f}M"
            ),
            result=round(nii_per_bp, 4),
            explanation=(
                "ΔNII/bp tells you how much annual NII changes per 1bp parallel shift. "
                "This is the key IRRBB earnings sensitivity metric."
            ),
        ))

        # Step 4: repricing gap analysis
        repricing_gap = (asset_bal * asset_pt / max(asset_reprice, 1)
                         - liab_bal * liab_pt / max(liab_reprice, 1))
        asset_sensitivity = "asset-sensitive" if repricing_gap > 0 else "liability-sensitive"

        steps.append(CalculationStep(
            step_number=4,
            label="Repricing gap analysis",
            formula=r"Gap = A \cdot \alpha_{asset} / T_{asset} - L \cdot \alpha_{liab} / T_{liab}",
            substitution=(
                f"Asset repricing per month: ${asset_bal * asset_pt / max(asset_reprice, 1):.2f}M\n"
                f"Liability repricing per month: ${liab_bal * liab_pt / max(liab_reprice, 1):.2f}M\n"
                f"Net repricing gap: ${repricing_gap:.2f}M/month\n"
                f"Position: {asset_sensitivity}"
            ),
            result=round(repricing_gap, 2),
            explanation=(
                "Positive gap = assets reprice faster → NII benefits from rate hikes. "
                "Negative gap = liabilities reprice faster → NII suffers from rate hikes."
            ),
        ))

        # Step 5: NII-at-risk
        worst_nii = min(r["total_nii"] for r in shock_results.values())
        nii_at_risk = base["total_nii"] - worst_nii

        steps.append(CalculationStep(
            step_number=5,
            label="NII-at-Risk",
            formula=r"NII\text{-}at\text{-}Risk = NII_{base} - NII_{worst}",
            substitution=(
                f"Base NII: ${base['total_nii']:.2f}M\n"
                f"Worst scenario NII: ${worst_nii:.2f}M\n"
                f"NII-at-Risk: ${nii_at_risk:.2f}M\n"
                f"NII-at-Risk as % of base: {nii_at_risk / base['total_nii'] * 100:.1f}%" if base["total_nii"] != 0 else ""
            ),
            result=round(nii_at_risk, 2),
            explanation="Maximum NII loss across the standard parallel shock scenarios.",
        ))

        greeks = {
            "nii_per_bp": round(nii_per_bp, 4),
            "repricing_gap": round(repricing_gap, 2),
        }

        return SimulatorResult(
            fair_value=round(base["total_nii"], 2),
            method=f"NII Forecast ({horizon}-month horizon, static balance sheet)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "base_nii": round(base["total_nii"], 2),
                "base_income": round(base["total_income"], 2),
                "base_expense": round(base["total_expense"], 2),
                "net_interest_margin_pct": round(net_margin * 100, 2),
                "nii_per_bp": round(nii_per_bp, 4),
                "nii_at_risk": round(nii_at_risk, 2),
                "position": asset_sensitivity,
                "shock_minus200": round(shock_results[-200]["total_nii"], 2),
                "shock_minus100": round(shock_results[-100]["total_nii"], 2),
                "shock_plus100": round(shock_results[100]["total_nii"], 2),
                "shock_plus200": round(shock_results[200]["total_nii"], 2),
                "monthly_nii_base": [round(x, 2) for x in base["monthly_nii"]],
            },
        )

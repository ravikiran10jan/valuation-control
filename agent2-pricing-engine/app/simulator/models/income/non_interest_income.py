"""Non-Interest Income (NII) Forecasting Model.

Forecasts non-interest income streams including:
  - Fee & commission income (advisory, underwriting, servicing)
  - Trading revenue (market-making, proprietary trading P&L)
  - Gains/losses on investment securities
  - Other non-interest income (insurance, trust, servicing fees)

The model applies scenario-based multipliers tied to market conditions:
  - Equity market performance (S&P proxy)
  - Credit spread environment
  - FX volatility
  - Interest rate level and volatility

This is complementary to NII forecasting for total revenue projection.
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


def _market_sensitivity(
    base_value: float,
    equity_return: float, equity_beta: float,
    spread_change_bps: float, spread_sensitivity: float,
    vol_change: float, vol_sensitivity: float,
    rate_change_bps: float, rate_sensitivity: float,
) -> float:
    """Apply market factor sensitivities to a revenue stream."""
    adjustment = 1.0
    adjustment += equity_beta * equity_return
    adjustment += spread_sensitivity * spread_change_bps / 100
    adjustment += vol_sensitivity * vol_change
    adjustment += rate_sensitivity * rate_change_bps / 10000
    return base_value * max(adjustment, 0.0)


@ModelRegistry.register
class NonInterestIncomeModel(BaseSimulatorModel):

    model_id = "non_interest_income"
    model_name = "Non-Interest Income Forecast"
    product_type = "Revenue Forecasting"
    asset_class = "income"

    short_description = (
        "Forecast fee, trading, and other non-interest income under market scenarios"
    )
    long_description = (
        "Projects non-interest income across four revenue streams: (1) fee & "
        "commission income (relatively stable, slightly market-sensitive), "
        "(2) trading revenue (highly sensitive to vol and market conditions), "
        "(3) investment securities gains/losses (rate and spread sensitive), "
        "and (4) other non-interest income (insurance, trust, servicing). "
        "Each stream has configurable sensitivity to equity markets, credit "
        "spreads, FX volatility, and interest rates.  Used by FP&A, Treasury, "
        "and management reporting for total revenue projection alongside NII."
    )

    when_to_use = [
        "Total bank revenue forecasting (NII + non-interest income)",
        "Stress testing: projecting fee and trading income under adverse scenarios",
        "Budget planning: estimating non-interest income sensitivity to markets",
        "Strategic planning: understanding revenue mix and diversification",
        "CCAR/DFAST revenue projection (non-interest income component)",
    ]
    when_not_to_use = [
        "Detailed trading desk P&L — use position-level VaR/Greeks",
        "Individual product pricing — use product-specific models",
        "When you need stochastic simulation of each revenue line",
        "Intraday trading revenue estimation",
    ]
    assumptions = [
        "Revenue streams are decomposed into base level + market sensitivity",
        "Linear sensitivity to market factors (first-order approximation)",
        "Base revenue reflects current run-rate (trailing 12-month average)",
        "Market factors: equity returns, credit spreads, FX vol, rates",
        "Sensitivities (betas) are constant over the forecast horizon",
    ]
    limitations = [
        "Linear sensitivities — in reality, trading revenue can be nonlinear",
        "No correlation modelling between revenue streams",
        "Static sensitivities — do not adapt to market regime changes",
        "No modelling of business growth, loss of clients, or strategy changes",
        "Simplified: real banks have dozens of fee categories with different drivers",
    ]

    formula_latex = (
        r"R_i = R_i^{base} \cdot \left(1 + \beta_i^{eq} \Delta_{eq} + "
        r"\beta_i^{spread} \frac{\Delta_{spread}}{100} + "
        r"\beta_i^{vol} \Delta_{vol} + "
        r"\beta_i^{rate} \frac{\Delta_{rate}}{10000}\right)"
    )
    formula_plain = (
        "R_i = Base_i × (1 + β_eq × ΔEquity + β_spread × ΔSpread/100 "
        "+ β_vol × ΔVol + β_rate × ΔRate/10000)"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            # Fee & commission income
            ParameterSpec("fee_income_base", "Fee Income Base ($M/yr)", "Annual fee & commission income", "float", 800.0, 0.0, 50000.0, 10.0, unit="$M"),
            ParameterSpec("fee_equity_beta", "Fee — Equity Beta", "Fee income sensitivity to equity markets", "float", 0.15, -1.0, 2.0, 0.05),
            ParameterSpec("fee_spread_sens", "Fee — Spread Sensitivity", "Fee sensitivity to credit spreads (per 100bp)", "float", -0.05, -1.0, 1.0, 0.01),

            # Trading revenue
            ParameterSpec("trading_base", "Trading Revenue Base ($M/yr)", "Annual trading revenue", "float", 500.0, -500.0, 20000.0, 10.0, unit="$M"),
            ParameterSpec("trading_equity_beta", "Trading — Equity Beta", "Trading P&L sensitivity to equities", "float", 0.30, -2.0, 2.0, 0.05),
            ParameterSpec("trading_vol_sens", "Trading — Vol Sensitivity", "Trading revenue sensitivity to vol increase", "float", 0.40, -2.0, 2.0, 0.05),
            ParameterSpec("trading_spread_sens", "Trading — Spread Sensitivity", "Trading sensitivity to credit spread widening", "float", -0.20, -2.0, 2.0, 0.05),

            # Investment securities
            ParameterSpec("securities_base", "Securities Gains Base ($M/yr)", "Annual investment securities gains", "float", 100.0, -500.0, 5000.0, 10.0, unit="$M"),
            ParameterSpec("securities_rate_sens", "Securities — Rate Sensitivity", "Gain/loss sensitivity to rate changes (per 100bp)", "float", -0.30, -2.0, 2.0, 0.05),
            ParameterSpec("securities_spread_sens", "Securities — Spread Sensitivity", "Sensitivity to credit spread changes", "float", -0.15, -2.0, 2.0, 0.05),

            # Other income
            ParameterSpec("other_income_base", "Other Income Base ($M/yr)", "Other non-interest income (insurance, trust)", "float", 200.0, 0.0, 10000.0, 10.0, unit="$M"),

            # Market scenario inputs
            ParameterSpec("equity_return", "Equity Market Return", "Expected equity return over horizon (e.g., -0.20 = -20%)", "float", 0.0, -0.5, 0.5, 0.01, unit="decimal"),
            ParameterSpec("spread_change_bps", "Credit Spread Change (bps)", "Change in credit spreads (positive = widening)", "float", 0.0, -200.0, 500.0, 10.0, unit="bps"),
            ParameterSpec("vol_change", "Volatility Change", "Change in implied vol level (e.g., 0.10 = vol up 10 pts)", "float", 0.0, -0.3, 0.5, 0.01, unit="decimal"),
            ParameterSpec("rate_change_bps", "Rate Change (bps)", "Parallel rate shift", "float", 0.0, -300.0, 300.0, 25.0, unit="bps"),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Base Case (no market moves)": {
                "fee_income_base": 800, "fee_equity_beta": 0.15, "fee_spread_sens": -0.05,
                "trading_base": 500, "trading_equity_beta": 0.30,
                "trading_vol_sens": 0.40, "trading_spread_sens": -0.20,
                "securities_base": 100, "securities_rate_sens": -0.30,
                "securities_spread_sens": -0.15, "other_income_base": 200,
                "equity_return": 0.0, "spread_change_bps": 0,
                "vol_change": 0.0, "rate_change_bps": 0,
            },
            "Recession Stress": {
                "fee_income_base": 800, "fee_equity_beta": 0.15, "fee_spread_sens": -0.05,
                "trading_base": 500, "trading_equity_beta": 0.30,
                "trading_vol_sens": 0.40, "trading_spread_sens": -0.20,
                "securities_base": 100, "securities_rate_sens": -0.30,
                "securities_spread_sens": -0.15, "other_income_base": 200,
                "equity_return": -0.25, "spread_change_bps": 150,
                "vol_change": 0.15, "rate_change_bps": -100,
            },
            "Bull Market": {
                "fee_income_base": 800, "fee_equity_beta": 0.15, "fee_spread_sens": -0.05,
                "trading_base": 500, "trading_equity_beta": 0.30,
                "trading_vol_sens": 0.40, "trading_spread_sens": -0.20,
                "securities_base": 100, "securities_rate_sens": -0.30,
                "securities_spread_sens": -0.15, "other_income_base": 200,
                "equity_return": 0.15, "spread_change_bps": -50,
                "vol_change": -0.05, "rate_change_bps": 50,
            },
            "Rate Shock (rising rates)": {
                "fee_income_base": 800, "fee_equity_beta": 0.15, "fee_spread_sens": -0.05,
                "trading_base": 500, "trading_equity_beta": 0.30,
                "trading_vol_sens": 0.40, "trading_spread_sens": -0.20,
                "securities_base": 100, "securities_rate_sens": -0.30,
                "securities_spread_sens": -0.15, "other_income_base": 200,
                "equity_return": -0.05, "spread_change_bps": 25,
                "vol_change": 0.05, "rate_change_bps": 200,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        # Extract parameters
        fee_base = float(params["fee_income_base"])
        fee_eq_beta = float(params["fee_equity_beta"])
        fee_sp_sens = float(params["fee_spread_sens"])

        trade_base = float(params["trading_base"])
        trade_eq_beta = float(params["trading_equity_beta"])
        trade_vol_sens = float(params["trading_vol_sens"])
        trade_sp_sens = float(params["trading_spread_sens"])

        sec_base = float(params["securities_base"])
        sec_rate_sens = float(params["securities_rate_sens"])
        sec_sp_sens = float(params["securities_spread_sens"])

        other_base = float(params["other_income_base"])

        eq_ret = float(params["equity_return"])
        sp_chg = float(params["spread_change_bps"])
        vol_chg = float(params["vol_change"])
        rate_chg = float(params["rate_change_bps"])

        steps: list[CalculationStep] = []

        # Step 1: base case
        total_base = fee_base + trade_base + sec_base + other_base
        steps.append(CalculationStep(
            step_number=1,
            label="Base non-interest income",
            formula=r"R_{base} = R_{fee} + R_{trading} + R_{securities} + R_{other}",
            substitution=(
                f"Fee income: ${fee_base:.1f}M\n"
                f"Trading revenue: ${trade_base:.1f}M\n"
                f"Securities gains: ${sec_base:.1f}M\n"
                f"Other income: ${other_base:.1f}M\n"
                f"Total base: ${total_base:.1f}M"
            ),
            result=round(total_base, 1),
            explanation="Base run-rate non-interest income before market scenario adjustments.",
        ))

        # Step 2: market scenario
        steps.append(CalculationStep(
            step_number=2,
            label="Market scenario",
            formula=r"\Delta_{eq}, \Delta_{spread}, \Delta_{vol}, \Delta_{rate}",
            substitution=(
                f"Equity return: {eq_ret:+.1%}\n"
                f"Spread change: {sp_chg:+.0f}bp\n"
                f"Vol change: {vol_chg:+.2f}\n"
                f"Rate change: {rate_chg:+.0f}bp"
            ),
            result=round(eq_ret, 4),
            explanation="Market factors that drive changes in non-interest income components.",
        ))

        # Step 3: fee income
        fee_adjusted = _market_sensitivity(
            fee_base, eq_ret, fee_eq_beta,
            sp_chg, fee_sp_sens, vol_chg, 0.0, rate_chg, 0.0,
        )
        fee_delta = fee_adjusted - fee_base

        steps.append(CalculationStep(
            step_number=3,
            label="Fee & commission income",
            formula=r"R_{fee} = base \times (1 + \beta_{eq} \Delta_{eq} + \beta_{sp} \Delta_{sp}/100)",
            substitution=(
                f"Base: ${fee_base:.1f}M\n"
                f"Equity effect: {fee_eq_beta} × {eq_ret:+.1%} = {fee_eq_beta * eq_ret:+.4f}\n"
                f"Spread effect: {fee_sp_sens} × {sp_chg:+.0f}/100 = {fee_sp_sens * sp_chg / 100:+.4f}\n"
                f"Adjusted: ${fee_adjusted:.1f}M (Δ = ${fee_delta:+.1f}M)"
            ),
            result=round(fee_adjusted, 1),
            explanation=(
                "Fee income is moderately sensitive to equity markets (advisory, AUM-based fees) "
                "and slightly to credit spreads (underwriting activity)."
            ),
        ))

        # Step 4: trading revenue
        trade_adjusted = _market_sensitivity(
            trade_base, eq_ret, trade_eq_beta,
            sp_chg, trade_sp_sens, vol_chg, trade_vol_sens, rate_chg, 0.0,
        )
        trade_delta = trade_adjusted - trade_base

        steps.append(CalculationStep(
            step_number=4,
            label="Trading revenue",
            formula=r"R_{trade} = base \times (1 + \beta_{eq}\Delta_{eq} + \beta_{vol}\Delta_{vol} + \beta_{sp}\Delta_{sp}/100)",
            substitution=(
                f"Base: ${trade_base:.1f}M\n"
                f"Equity effect: {trade_eq_beta} × {eq_ret:+.1%} = {trade_eq_beta * eq_ret:+.4f}\n"
                f"Vol effect: {trade_vol_sens} × {vol_chg:+.2f} = {trade_vol_sens * vol_chg:+.4f}\n"
                f"Spread effect: {trade_sp_sens} × {sp_chg:+.0f}/100 = {trade_sp_sens * sp_chg / 100:+.4f}\n"
                f"Adjusted: ${trade_adjusted:.1f}M (Δ = ${trade_delta:+.1f}M)"
            ),
            result=round(trade_adjusted, 1),
            explanation=(
                "Trading revenue is highly market-sensitive. Higher vol generally helps "
                "market-making revenue but wider spreads can hurt credit trading."
            ),
        ))

        # Step 5: securities gains
        sec_adjusted = _market_sensitivity(
            sec_base, eq_ret, 0.0,
            sp_chg, sec_sp_sens, vol_chg, 0.0, rate_chg, sec_rate_sens,
        )
        sec_delta = sec_adjusted - sec_base

        steps.append(CalculationStep(
            step_number=5,
            label="Investment securities gains/losses",
            formula=r"R_{sec} = base \times (1 + \beta_{rate}\Delta_{rate}/10000 + \beta_{sp}\Delta_{sp}/100)",
            substitution=(
                f"Base: ${sec_base:.1f}M\n"
                f"Rate effect: {sec_rate_sens} × {rate_chg:+.0f}/10000 = {sec_rate_sens * rate_chg / 10000:+.4f}\n"
                f"Spread effect: {sec_sp_sens} × {sp_chg:+.0f}/100 = {sec_sp_sens * sp_chg / 100:+.4f}\n"
                f"Adjusted: ${sec_adjusted:.1f}M (Δ = ${sec_delta:+.1f}M)"
            ),
            result=round(sec_adjusted, 1),
            explanation=(
                "Securities gains are inversely related to rate increases (mark-to-market "
                "losses on bond portfolio) and credit spread widening."
            ),
        ))

        # Step 6: total
        total_adjusted = fee_adjusted + trade_adjusted + sec_adjusted + other_base
        total_delta = total_adjusted - total_base

        steps.append(CalculationStep(
            step_number=6,
            label="Total non-interest income",
            formula=r"R_{total} = R_{fee} + R_{trading} + R_{securities} + R_{other}",
            substitution=(
                f"Fee income: ${fee_adjusted:.1f}M\n"
                f"Trading revenue: ${trade_adjusted:.1f}M\n"
                f"Securities gains: ${sec_adjusted:.1f}M\n"
                f"Other income: ${other_base:.1f}M (unchanged)\n"
                f"Total: ${total_adjusted:.1f}M\n"
                f"Change from base: ${total_delta:+.1f}M ({total_delta / total_base * 100:+.1f}%)" if total_base != 0 else ""
            ),
            result=round(total_adjusted, 1),
            explanation="Total non-interest income under the specified market scenario.",
        ))

        greeks = {
            "equity_sensitivity": round(
                (fee_base * fee_eq_beta + trade_base * trade_eq_beta) / total_base if total_base != 0 else 0, 4
            ),
            "spread_sensitivity_per_100bp": round(
                (fee_base * fee_sp_sens + trade_base * trade_sp_sens + sec_base * sec_sp_sens) / total_base if total_base != 0 else 0, 4
            ),
            "vol_sensitivity": round(
                trade_base * trade_vol_sens / total_base if total_base != 0 else 0, 4
            ),
        }

        return SimulatorResult(
            fair_value=round(total_adjusted, 1),
            method="Non-Interest Income Forecast (scenario-based)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "base_total": round(total_base, 1),
                "adjusted_total": round(total_adjusted, 1),
                "total_change": round(total_delta, 1),
                "total_change_pct": round(total_delta / total_base * 100, 1) if total_base != 0 else 0,
                "fee_income": round(fee_adjusted, 1),
                "trading_revenue": round(trade_adjusted, 1),
                "securities_gains": round(sec_adjusted, 1),
                "other_income": round(other_base, 1),
                "fee_change": round(fee_delta, 1),
                "trading_change": round(trade_delta, 1),
                "securities_change": round(sec_delta, 1),
                "revenue_mix": {
                    "fee_pct": round(fee_adjusted / total_adjusted * 100, 1) if total_adjusted != 0 else 0,
                    "trading_pct": round(trade_adjusted / total_adjusted * 100, 1) if total_adjusted != 0 else 0,
                    "securities_pct": round(sec_adjusted / total_adjusted * 100, 1) if total_adjusted != 0 else 0,
                    "other_pct": round(other_base / total_adjusted * 100, 1) if total_adjusted != 0 else 0,
                },
            },
        )

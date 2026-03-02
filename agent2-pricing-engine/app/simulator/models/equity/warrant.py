"""Warrant pricing — dilution-adjusted Black-Scholes.

Adjusts BSM for the dilution effect when warrants are exercised,
since new shares are issued.
"""

from __future__ import annotations

import math
from typing import Any

from scipy.stats import norm

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


@ModelRegistry.register
class WarrantModel(BaseSimulatorModel):

    model_id = "warrant"
    model_name = "Warrant (Dilution-Adjusted BSM)"
    product_type = "Equity Warrant"
    asset_class = "equity"

    short_description = "BSM warrant pricing with dilution adjustment for new share issuance"
    long_description = (
        "Prices equity warrants using a dilution-adjusted Black-Scholes model. "
        "When warrants are exercised, the company issues new shares, diluting "
        "existing shareholders. The dilution factor is N/(N+M) where N is the "
        "number of existing shares and M is the number of warrants. The warrant "
        "price equals the dilution factor times the BSM call value. This is the "
        "standard approach for IFRS 2 / ASC 718 valuation of employee warrants."
    )

    when_to_use = [
        "Pricing company warrants where dilution matters",
        "IFRS 2 / ASC 718 fair value estimation",
        "When warrants represent a material fraction of shares outstanding",
        "Understanding the difference between warrants and exchange-traded options",
    ]
    when_not_to_use = [
        "Exchange-traded options (no dilution — use standard BSM)",
        "When dilution is negligible (M << N — standard BSM suffices)",
        "Warrants with complex exercise provisions (use lattice methods)",
        "When the company has multiple tranches of warrants/converts",
    ]
    assumptions = [
        "Stock follows GBM (same as BSM)",
        "All M warrants are exercised simultaneously",
        "Exercise proceeds are invested at the risk-free rate",
        "No transaction costs or taxes on exercise",
        "Dilution factor is constant: N/(N+M)",
    ]
    limitations = [
        "Assumes simultaneous exercise of all warrants (unrealistic)",
        "Does not model optimal exercise for American-style warrants",
        "Static dilution — ignores impact of exercise proceeds on firm value",
        "Single-tranche — cannot handle multiple warrant series",
    ]

    formula_latex = (
        r"W = \frac{N}{N+M} \cdot C_{BSM}(S, K, T, \sigma, r, q)"
    )
    formula_plain = (
        "Warrant = (N/(N+M)) × BSM_Call(S, K, T, σ, r, q),  "
        "where N = shares outstanding, M = warrants outstanding"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Stock Price (S)", "Current stock price",
                "float", 50.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "strike", "Exercise Price (K)", "Warrant exercise price",
                "float", 60.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Warrant life in years",
                "float", 5.0, 0.01, 30.0, 0.1, unit="years",
            ),
            ParameterSpec(
                "vol", "Volatility (σ)", "Stock volatility (annualized)",
                "float", 0.35, 0.01, 3.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Continuous risk-free rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield", "Continuous dividend yield",
                "float", 0.01, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "shares_outstanding", "Shares Outstanding (N)",
                "Number of existing shares (millions)",
                "float", 100.0, 0.1, None, 1.0, unit="M",
            ),
            ParameterSpec(
                "warrants_outstanding", "Warrants Outstanding (M)",
                "Number of warrants (millions)",
                "float", 10.0, 0.1, None, 1.0, unit="M",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Standard Warrant (10% dilution)": {
                "spot": 50.0, "strike": 60.0, "maturity": 5.0,
                "vol": 0.35, "r": 0.05, "q": 0.01,
                "shares_outstanding": 100.0, "warrants_outstanding": 10.0,
            },
            "Low Dilution (2%)": {
                "spot": 50.0, "strike": 60.0, "maturity": 5.0,
                "vol": 0.35, "r": 0.05, "q": 0.01,
                "shares_outstanding": 100.0, "warrants_outstanding": 2.0,
            },
            "High Dilution (25%)": {
                "spot": 50.0, "strike": 60.0, "maturity": 5.0,
                "vol": 0.35, "r": 0.05, "q": 0.01,
                "shares_outstanding": 100.0, "warrants_outstanding": 25.0,
            },
            "ATM Short-dated": {
                "spot": 50.0, "strike": 50.0, "maturity": 2.0,
                "vol": 0.30, "r": 0.05, "q": 0.01,
                "shares_outstanding": 100.0, "warrants_outstanding": 10.0,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        N_shares = float(params["shares_outstanding"])
        M_warrants = float(params["warrants_outstanding"])

        steps_list: list[CalculationStep] = []
        sqrt_T = math.sqrt(T)

        # Step 1: dilution factor
        dilution = N_shares / (N_shares + M_warrants)
        dilution_pct = M_warrants / (N_shares + M_warrants) * 100

        steps_list.append(CalculationStep(
            step_number=1,
            label="Dilution factor",
            formula=r"\alpha = \frac{N}{N+M}",
            substitution=(
                f"α = {N_shares}/{N_shares}+{M_warrants} = {dilution:.6f}.  "
                f"Dilution = {dilution_pct:.2f}%"
            ),
            result=round(dilution, 6),
            explanation=(
                "When M warrants are exercised, N+M shares exist. "
                "Each warrant gets N/(N+M) of the BSM call value."
            ),
        ))

        # Step 2: BSM call value
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        Nd1 = norm.cdf(d1)
        Nd2 = norm.cdf(d2)
        df_q = math.exp(-q * T)
        df_r = math.exp(-r * T)
        bsm_call = S * df_q * Nd1 - K * df_r * Nd2

        steps_list.append(CalculationStep(
            step_number=2,
            label="BSM call value (undiluted)",
            formula=r"C_{BSM} = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)",
            substitution=(
                f"d₁={d1:.6f}, d₂={d2:.6f}.  "
                f"C_BSM = {S}×{df_q:.6f}×{Nd1:.6f} - {K}×{df_r:.6f}×{Nd2:.6f}"
                f" = ${bsm_call:.4f}"
            ),
            result=round(bsm_call, 4),
            explanation="Standard BSM call value before dilution adjustment.",
        ))

        # Step 3: warrant value
        warrant = dilution * bsm_call
        discount_amount = bsm_call - warrant

        steps_list.append(CalculationStep(
            step_number=3,
            label="Dilution-adjusted warrant price",
            formula=r"W = \alpha \times C_{BSM}",
            substitution=(
                f"W = {dilution:.6f} × ${bsm_call:.4f} = ${warrant:.4f}.  "
                f"Dilution discount = ${discount_amount:.4f} "
                f"({discount_amount / bsm_call * 100:.1f}% of BSM)"
            ),
            result=round(warrant, 4),
            explanation=(
                "The warrant price is the diluted BSM call. The dilution discount "
                "represents value lost to existing shareholders upon exercise."
            ),
        ))

        # Step 4: Greeks (diluted)
        nd1 = norm.pdf(d1)
        delta = dilution * df_q * Nd1
        gamma = dilution * df_q * nd1 / (S * sigma * sqrt_T)
        vega = dilution * S * df_q * nd1 * sqrt_T
        theta = dilution * (
            -S * nd1 * sigma * df_q / (2 * sqrt_T)
            - r * K * df_r * Nd2
            + q * S * df_q * Nd1
        )
        rho = dilution * K * T * df_r * Nd2

        greeks = {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega / 100, 6),
            "theta": round(theta / 365, 6),
            "rho": round(rho / 100, 6),
        }

        steps_list.append(CalculationStep(
            step_number=4,
            label="Diluted Greeks",
            formula=r"\Delta_W = \alpha \cdot \Delta_{BSM}",
            substitution=(
                f"Δ={delta:.6f}  Γ={gamma:.6f}  "
                f"V={vega / 100:.4f}/1%  Θ={theta / 365:.4f}/day  "
                f"ρ={rho / 100:.4f}/1%"
            ),
            result=round(delta, 6),
            explanation="All Greeks are scaled by the dilution factor α.",
        ))

        # Step 5: total warrant issuance value
        total_value = warrant * M_warrants * 1e6
        total_exercise_proceeds = K * M_warrants * 1e6

        steps_list.append(CalculationStep(
            step_number=5,
            label="Aggregate values",
            formula=r"\text{Total} = W \times M",
            substitution=(
                f"Total warrant value = ${warrant:.4f} × {M_warrants}M "
                f"= ${total_value / 1e6:,.2f}M.  "
                f"Exercise proceeds (if all exercised) = ${total_exercise_proceeds / 1e6:,.2f}M"
            ),
            result=round(total_value / 1e6, 2),
            explanation="Aggregate fair value of all warrants and potential exercise proceeds.",
        ))

        return SimulatorResult(
            fair_value=round(warrant, 4),
            method="Dilution-Adjusted Black-Scholes",
            greeks=greeks,
            calculation_steps=steps_list,
            diagnostics={
                "bsm_call_undiluted": round(bsm_call, 4),
                "warrant_diluted": round(warrant, 4),
                "dilution_factor": round(dilution, 6),
                "dilution_pct": round(dilution_pct, 2),
                "dilution_discount": round(discount_amount, 4),
                "d1": round(d1, 6),
                "d2": round(d2, 6),
                "total_warrant_value_M": round(total_value / 1e6, 2),
                "exercise_proceeds_M": round(total_exercise_proceeds / 1e6, 2),
            },
        )

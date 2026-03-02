"""Garman-Kohlhagen model for European FX vanilla options.

Extension of Black-Scholes to foreign exchange, replacing the dividend
yield with the foreign risk-free rate.  The model was published by
Garman & Kohlhagen (1983) and remains the market-standard quoting
convention for FX options.
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
class GarmanKohlhagenModel(BaseSimulatorModel):

    model_id = "garman_kohlhagen"
    model_name = "Garman-Kohlhagen"
    product_type = "European FX Vanilla Option"
    asset_class = "fx"

    short_description = (
        "BSM extended to FX options with domestic and foreign interest rates"
    )
    long_description = (
        "The Garman-Kohlhagen (1983) model prices European FX options by treating "
        "the foreign interest rate as a continuous dividend yield in the Black-Scholes "
        "framework. The spot rate S is expressed as domestic per unit of foreign "
        "currency (e.g. USD/EUR = 1.08 means 1 EUR costs 1.08 USD). A call gives "
        "the right to buy foreign currency (pay domestic), a put gives the right to "
        "sell foreign currency (receive domestic). Greeks are expressed in domestic "
        "currency terms."
    )

    when_to_use = [
        "European FX vanilla options (no early exercise)",
        "Liquid G10 currency pairs with stable vol",
        "Quick indicative pricing and delta hedging",
        "Baseline model for FX options — industry-standard quoting convention",
        "When a single implied volatility is available (ATM or strike-specific)",
    ]
    when_not_to_use = [
        "FX barrier options — use analytical barrier formulas or MC",
        "FX options where smile is critical — use Vanna-Volga or SABR",
        "TARFs, accumulators, and other path-dependent structures",
        "Long-dated FX options where rate vol matters — consider stochastic rates",
        "Emerging market pairs with jump risk or capital controls",
    ]
    assumptions = [
        "Spot rate follows geometric Brownian motion: dS = (r_d - r_f)S dt + σS dW",
        "Constant domestic and foreign risk-free rates",
        "Constant volatility over the life of the option",
        "Continuous trading, no transaction costs, no bid-ask spread",
        "Log-normal distribution of returns — no skew or excess kurtosis",
    ]
    limitations = [
        "Cannot reproduce the FX volatility smile (25Δ RR, 25Δ BF structure)",
        "Single vol for all strikes — use Vanna-Volga for smile adjustment",
        "Assumes deterministic interest rates — inaccurate for long-dated options",
        "No jump component — underestimates tail risk in EM pairs",
    ]

    formula_latex = (
        r"C = S e^{-r_f T} N(d_1) - K e^{-r_d T} N(d_2)"
        r"\quad\quad"
        r"P = K e^{-r_d T} N(-d_2) - S e^{-r_f T} N(-d_1)"
    )
    formula_plain = (
        "C = S·exp(-rf·T)·N(d1) - K·exp(-rd·T)·N(d2),  "
        "where d1 = [ln(S/K) + (rd - rf + σ²/2)T] / (σ√T),  d2 = d1 - σ√T"
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Rate (S)", "Spot FX rate (domestic per foreign)",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "strike", "Strike (K)", "Option strike rate",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Time to expiration in years",
                "float", 0.25, 0.001, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "vol", "Volatility (σ)", "Annualized implied volatility",
                "float", 0.08, 0.001, 5.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_dom", "Domestic Rate (r_d)", "Domestic risk-free rate (continuous)",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_for", "Foreign Rate (r_f)", "Foreign risk-free rate (continuous)",
                "float", 0.03, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call (buy foreign) or Put (sell foreign)",
                "select", "call", options=["call", "put"],
            ),
            ParameterSpec(
                "notional", "Notional (foreign)", "Foreign currency notional amount",
                "float", 1_000_000.0, 1.0, None, 1000.0, unit="FOR",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "EURUSD ATM Call 3M": {
                "spot": 1.0800, "strike": 1.0800, "maturity": 0.25,
                "vol": 0.08, "r_dom": 0.053, "r_for": 0.035,
                "option_type": "call", "notional": 1_000_000.0,
            },
            "USDJPY OTM Put 6M": {
                "spot": 155.50, "strike": 150.00, "maturity": 0.5,
                "vol": 0.10, "r_dom": 0.001, "r_for": 0.053,
                "option_type": "put", "notional": 10_000_000.0,
            },
            "GBPUSD ITM Call 1Y": {
                "spot": 1.2700, "strike": 1.2200, "maturity": 1.0,
                "vol": 0.09, "r_dom": 0.053, "r_for": 0.05,
                "option_type": "call", "notional": 5_000_000.0,
            },
            "AUDUSD ATM Put 3M": {
                "spot": 0.6550, "strike": 0.6550, "maturity": 0.25,
                "vol": 0.11, "r_dom": 0.053, "r_for": 0.043,
                "option_type": "put", "notional": 2_000_000.0,
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        rd = float(params["r_dom"])
        rf = float(params["r_for"])
        opt_type = params.get("option_type", "call").lower()
        notional = float(params.get("notional", 1_000_000.0))

        steps: list[CalculationStep] = []
        sqrt_T = math.sqrt(T)

        # Step 1: d1
        d1_num = math.log(S / K) + (rd - rf + 0.5 * sigma**2) * T
        d1_den = sigma * sqrt_T
        d1 = d1_num / d1_den
        steps.append(CalculationStep(
            step_number=1,
            label="Calculate d₁",
            formula=r"d_1 = \frac{\ln(S/K) + (r_d - r_f + \sigma^2/2) T}{\sigma \sqrt{T}}",
            substitution=(
                f"d₁ = [ln({S}/{K}) + ({rd} - {rf} + {sigma}²/2) × {T}]"
                f" / ({sigma} × √{T})"
                f" = {d1_num:.6f} / {d1_den:.6f}"
            ),
            result=round(d1, 6),
            explanation=(
                "d₁ measures how far in-the-money the option is in standard-deviation "
                "units, using the forward rate implied by interest rate differential."
            ),
        ))

        # Step 2: d2
        d2 = d1 - sigma * sqrt_T
        steps.append(CalculationStep(
            step_number=2,
            label="Calculate d₂",
            formula=r"d_2 = d_1 - \sigma \sqrt{T}",
            substitution=(
                f"d₂ = {d1:.6f} - {sigma} × √{T}"
                f" = {d1:.6f} - {sigma * sqrt_T:.6f}"
            ),
            result=round(d2, 6),
            explanation="d₂ adjusts d₁ for the volatility over the option's life.",
        ))

        # Step 3: cumulative normals
        Nd1 = norm.cdf(d1)
        Nd2 = norm.cdf(d2)
        Nmd1 = norm.cdf(-d1)
        Nmd2 = norm.cdf(-d2)
        steps.append(CalculationStep(
            step_number=3,
            label="Cumulative normal values",
            formula=r"N(d_1),\; N(d_2),\; N(-d_1),\; N(-d_2)",
            substitution=(
                f"N({d1:.4f}) = {Nd1:.6f},  N({d2:.4f}) = {Nd2:.6f},  "
                f"N({-d1:.4f}) = {Nmd1:.6f},  N({-d2:.4f}) = {Nmd2:.6f}"
            ),
            result=round(Nd1, 6),
            explanation="Standard normal CDF values used in the pricing formula.",
        ))

        # Step 4: discount factors
        df_f = math.exp(-rf * T)
        df_d = math.exp(-rd * T)
        steps.append(CalculationStep(
            step_number=4,
            label="Discount factors",
            formula=r"e^{-r_f T} \text{ (foreign)},\quad e^{-r_d T} \text{ (domestic)}",
            substitution=(
                f"e^(-{rf}×{T}) = {df_f:.6f} (foreign),  "
                f"e^(-{rd}×{T}) = {df_d:.6f} (domestic)"
            ),
            result=round(df_d, 6),
            explanation=(
                "Foreign discount factor adjusts spot for carry; "
                "domestic discount factor present-values the strike."
            ),
        ))

        # Step 5: forward rate
        F = S * math.exp((rd - rf) * T)
        steps.append(CalculationStep(
            step_number=5,
            label="Forward rate",
            formula=r"F = S \cdot e^{(r_d - r_f) T}",
            substitution=f"F = {S} × e^(({rd} - {rf}) × {T}) = {F:.6f}",
            result=round(F, 6),
            explanation=(
                "The implied forward FX rate from covered interest rate parity. "
                "If rd > rf the forward is at a premium (foreign currency at discount)."
            ),
        ))

        # Step 6: option price (per unit of foreign)
        if opt_type == "call":
            term1 = S * df_f * Nd1
            term2 = K * df_d * Nd2
            price = term1 - term2
            steps.append(CalculationStep(
                step_number=6,
                label="Call price (per unit foreign)",
                formula=(
                    r"C = S \cdot e^{-r_f T} \cdot N(d_1)"
                    r" - K \cdot e^{-r_d T} \cdot N(d_2)"
                ),
                substitution=(
                    f"C = {S}×{df_f:.6f}×{Nd1:.6f}"
                    f" - {K}×{df_d:.6f}×{Nd2:.6f}"
                    f" = {term1:.6f} - {term2:.6f}"
                ),
                result=round(price, 6),
                explanation="Call price in domestic currency per one unit of foreign notional.",
            ))
        else:
            term1 = K * df_d * Nmd2
            term2 = S * df_f * Nmd1
            price = term1 - term2
            steps.append(CalculationStep(
                step_number=6,
                label="Put price (per unit foreign)",
                formula=(
                    r"P = K \cdot e^{-r_d T} \cdot N(-d_2)"
                    r" - S \cdot e^{-r_f T} \cdot N(-d_1)"
                ),
                substitution=(
                    f"P = {K}×{df_d:.6f}×{Nmd2:.6f}"
                    f" - {S}×{df_f:.6f}×{Nmd1:.6f}"
                    f" = {term1:.6f} - {term2:.6f}"
                ),
                result=round(price, 6),
                explanation="Put price in domestic currency per one unit of foreign notional.",
            ))

        # Step 7: total premium
        premium = price * notional
        steps.append(CalculationStep(
            step_number=7,
            label="Total premium",
            formula=r"\text{Premium} = \text{price per unit} \times \text{Notional}",
            substitution=f"Premium = {price:.6f} × {notional:,.0f} = {premium:,.2f}",
            result=round(premium, 2),
            explanation="Total option premium in domestic currency.",
        ))

        # Step 8: Greeks
        nd1 = norm.pdf(d1)

        if opt_type == "call":
            delta_spot = df_f * Nd1
            delta_fwd = Nd1
            theta = (
                -S * nd1 * sigma * df_f / (2 * sqrt_T)
                - rd * K * df_d * Nd2
                + rf * S * df_f * Nd1
            )
            rho_dom = K * T * df_d * Nd2
            rho_for = -S * T * df_f * Nd1
        else:
            delta_spot = -df_f * Nmd1
            delta_fwd = -Nmd1
            theta = (
                -S * nd1 * sigma * df_f / (2 * sqrt_T)
                + rd * K * df_d * Nmd2
                - rf * S * df_f * Nmd1
            )
            rho_dom = -K * T * df_d * Nmd2
            rho_for = S * T * df_f * Nmd1

        gamma = df_f * nd1 / (S * sigma * sqrt_T)
        vega = S * df_f * nd1 * sqrt_T

        greeks = {
            "delta_spot": round(delta_spot, 6),
            "delta_forward": round(delta_fwd, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega / 100, 6),
            "theta": round(theta / 365, 6),
            "rho_domestic": round(rho_dom / 100, 6),
            "rho_foreign": round(rho_for / 100, 6),
        }

        steps.append(CalculationStep(
            step_number=8,
            label="Greeks",
            formula=(
                r"\Delta_s = e^{-r_f T} N(d_1),\;\;"
                r"\Gamma = \frac{e^{-r_f T} n(d_1)}{S \sigma \sqrt{T}},\;\;"
                r"\mathcal{V} = S e^{-r_f T} n(d_1) \sqrt{T}"
            ),
            substitution=(
                f"Δ_spot={delta_spot:.6f}  Δ_fwd={delta_fwd:.6f}  "
                f"Γ={gamma:.6f}  V={vega / 100:.4f}/1%  "
                f"Θ={theta / 365:.4f}/day  ρ_d={rho_dom / 100:.4f}/1%  "
                f"ρ_f={rho_for / 100:.4f}/1%"
            ),
            result=round(delta_spot, 6),
            explanation=(
                "Spot delta: change in option value per unit spot move. "
                "Forward delta: N(d1) for calls, used in FX market conventions. "
                "Two rhos: domestic and foreign rate sensitivity."
            ),
        ))

        intrinsic = max(S - K, 0) if opt_type == "call" else max(K - S, 0)

        return SimulatorResult(
            fair_value=round(price, 6),
            method="Garman-Kohlhagen (Analytical)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "d1": round(d1, 6),
                "d2": round(d2, 6),
                "N_d1": round(Nd1, 6),
                "N_d2": round(Nd2, 6),
                "forward_rate": round(F, 6),
                "forward_points": round((F - S) * 10000, 2),
                "moneyness": round(S / K, 6),
                "intrinsic_value": round(intrinsic, 6),
                "time_value": round(price - intrinsic, 6),
                "total_premium_domestic": round(premium, 2),
            },
        )

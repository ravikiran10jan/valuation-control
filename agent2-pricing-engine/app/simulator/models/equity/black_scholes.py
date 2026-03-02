"""Black-Scholes-Merton model for European vanilla options.

The foundational model in derivatives pricing (1973). Assumes geometric
Brownian motion with constant volatility.  Produces closed-form prices
and analytical Greeks for European calls and puts.
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
class BlackScholesModel(BaseSimulatorModel):

    model_id = "black_scholes"
    model_name = "Black-Scholes-Merton"
    product_type = "European Vanilla Option"
    asset_class = "equity"

    short_description = (
        "Closed-form pricing for European options under log-normal dynamics"
    )
    long_description = (
        "The Black-Scholes-Merton (1973) model prices European options assuming "
        "the underlying follows geometric Brownian motion with constant volatility. "
        "It produces closed-form solutions for calls and puts, along with analytical "
        "Greeks. This is the foundational model in derivatives pricing and serves as "
        "the benchmark against which all other models are compared. The key input is "
        "implied volatility — the vol that equates the BSM formula to the market price."
    )

    when_to_use = [
        "European vanilla options (no early exercise)",
        "Liquid markets with reasonably stable volatility",
        "Quick indicative pricing and delta hedging",
        "As a baseline comparison model for any option pricing",
        "When implied volatility is quoted (standard quoting convention)",
    ]
    when_not_to_use = [
        "American options — does not handle early exercise (use Binomial or PDE)",
        "Deep OTM/ITM options where vol smile/skew matters significantly",
        "Long-dated options where vol-of-vol dynamics are important (use Heston)",
        "Path-dependent products: barriers, Asians, lookbacks (use MC or PDE)",
        "Markets with jumps: EM currencies, earnings events (use Variance Gamma)",
        "When underlying pays large discrete dividends (use tree methods)",
    ]
    assumptions = [
        "Constant volatility over the life of the option",
        "Log-normal distribution of returns (no skew, no excess kurtosis)",
        "Continuous trading with no transaction costs",
        "Constant risk-free rate",
        "No arbitrage opportunities",
        "Underlying follows GBM: dS = (r-q)S dt + σS dW",
    ]
    limitations = [
        "Cannot reproduce the volatility smile — same vol for all strikes",
        "Underprices OTM puts (no skew) and misprices wings",
        "Greeks can be unreliable near expiry for ATM options",
        "Assumes continuous hedging — in practice rebalancing is discrete",
    ]

    formula_latex = (
        r"C = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)"
        r"\quad\quad"
        r"P = K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)"
    )
    formula_plain = (
        "C = S·exp(-qT)·N(d1) - K·exp(-rT)·N(d2),  "
        "where d1 = [ln(S/K) + (r-q+σ²/2)T] / (σ√T),  d2 = d1 - σ√T"
    )

    # ── Parameters ──────────────────────────────────────────────

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
                "vol", "Volatility (σ)", "Annualized implied volatility",
                "float", 0.20, 0.001, 5.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)", "Continuous compounding risk-free rate",
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
            "ATM Call (AAPL-like)": {
                "spot": 185.0, "strike": 185.0, "maturity": 0.25,
                "vol": 0.22, "r": 0.053, "q": 0.005, "option_type": "call",
            },
            "OTM Put (SPX-like)": {
                "spot": 5200.0, "strike": 4900.0, "maturity": 0.5,
                "vol": 0.18, "r": 0.053, "q": 0.015, "option_type": "put",
            },
            "Deep ITM LEAPS Call": {
                "spot": 150.0, "strike": 100.0, "maturity": 2.0,
                "vol": 0.30, "r": 0.05, "q": 0.01, "option_type": "call",
            },
            "Near-Expiry ATM": {
                "spot": 100.0, "strike": 100.0, "maturity": 0.02,
                "vol": 0.25, "r": 0.05, "q": 0.0, "option_type": "call",
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        opt_type = params.get("option_type", "call").lower()

        steps: list[CalculationStep] = []
        sqrt_T = math.sqrt(T)

        # Step 1: d1
        d1_num = math.log(S / K) + (r - q + 0.5 * sigma**2) * T
        d1_den = sigma * sqrt_T
        d1 = d1_num / d1_den
        steps.append(CalculationStep(
            step_number=1,
            label="Calculate d₁",
            formula=r"d_1 = \frac{\ln(S/K) + (r - q + \sigma^2/2) T}{\sigma \sqrt{T}}",
            substitution=(
                f"d₁ = [ln({S}/{K}) + ({r} - {q} + {sigma}²/2) × {T}]"
                f" / ({sigma} × √{T})"
                f" = {d1_num:.6f} / {d1_den:.6f}"
            ),
            result=round(d1, 6),
            explanation=(
                "d₁ measures how far in-the-money the option is, adjusted for "
                "drift, in units of standard deviation."
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
            explanation=(
                "d₂ is the risk-adjusted probability that the option "
                "expires in-the-money."
            ),
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
            explanation=(
                "N(x) is the standard normal CDF — the probability that a "
                "standard normal variable is ≤ x."
            ),
        ))

        # Step 4: discount factors
        df_q = math.exp(-q * T)
        df_r = math.exp(-r * T)
        steps.append(CalculationStep(
            step_number=4,
            label="Discount factors",
            formula=r"e^{-qT} \text{ and } e^{-rT}",
            substitution=(
                f"e^(-{q}×{T}) = {df_q:.6f},  "
                f"e^(-{r}×{T}) = {df_r:.6f}"
            ),
            result=round(df_r, 6),
            explanation=(
                "Discount factors for dividend yield (spot) and "
                "risk-free rate (strike)."
            ),
        ))

        # Step 5: option price
        if opt_type == "call":
            term1 = S * df_q * Nd1
            term2 = K * df_r * Nd2
            price = term1 - term2
            steps.append(CalculationStep(
                step_number=5,
                label="Call price",
                formula=(
                    r"C = S \cdot e^{-qT} \cdot N(d_1)"
                    r" - K \cdot e^{-rT} \cdot N(d_2)"
                ),
                substitution=(
                    f"C = {S}×{df_q:.6f}×{Nd1:.6f}"
                    f" - {K}×{df_r:.6f}×{Nd2:.6f}"
                    f" = {term1:.4f} - {term2:.4f}"
                ),
                result=round(price, 4),
                explanation=(
                    "The call price is the discounted expected payoff "
                    "under the risk-neutral measure."
                ),
            ))
        else:
            term1 = K * df_r * Nmd2
            term2 = S * df_q * Nmd1
            price = term1 - term2
            steps.append(CalculationStep(
                step_number=5,
                label="Put price",
                formula=(
                    r"P = K \cdot e^{-rT} \cdot N(-d_2)"
                    r" - S \cdot e^{-qT} \cdot N(-d_1)"
                ),
                substitution=(
                    f"P = {K}×{df_r:.6f}×{Nmd2:.6f}"
                    f" - {S}×{df_q:.6f}×{Nmd1:.6f}"
                    f" = {term1:.4f} - {term2:.4f}"
                ),
                result=round(price, 4),
                explanation="The put price via the direct formula.",
            ))

        # Step 6: Greeks
        nd1 = norm.pdf(d1)

        if opt_type == "call":
            delta = df_q * Nd1
            theta = (
                -S * nd1 * sigma * df_q / (2 * sqrt_T)
                - r * K * df_r * Nd2
                + q * S * df_q * Nd1
            )
            rho = K * T * df_r * Nd2
        else:
            delta = -df_q * Nmd1
            theta = (
                -S * nd1 * sigma * df_q / (2 * sqrt_T)
                + r * K * df_r * Nmd2
                - q * S * df_q * Nmd1
            )
            rho = -K * T * df_r * Nmd2

        gamma = df_q * nd1 / (S * sigma * sqrt_T)
        vega = S * df_q * nd1 * sqrt_T

        greeks = {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega / 100, 6),
            "theta": round(theta / 365, 6),
            "rho": round(rho / 100, 6),
        }

        steps.append(CalculationStep(
            step_number=6,
            label="Greeks",
            formula=(
                r"\Delta = e^{-qT} N(d_1),\;\;"
                r"\Gamma = \frac{e^{-qT} n(d_1)}{S \sigma \sqrt{T}},\;\;"
                r"\mathcal{V} = S e^{-qT} n(d_1) \sqrt{T}"
            ),
            substitution=(
                f"Δ={delta:.6f}  Γ={gamma:.6f}  "
                f"V={vega / 100:.4f}/1%  "
                f"Θ={theta / 365:.4f}/day  ρ={rho / 100:.4f}/1%"
            ),
            result=round(delta, 6),
            explanation=(
                "Delta: spot sensitivity. Gamma: convexity. "
                "Vega: vol sensitivity. Theta: time decay. Rho: rate sensitivity."
            ),
        ))

        intrinsic = max(S - K, 0) if opt_type == "call" else max(K - S, 0)

        return SimulatorResult(
            fair_value=round(price, 4),
            method="Black-Scholes-Merton (Analytical)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "d1": round(d1, 6),
                "d2": round(d2, 6),
                "N_d1": round(Nd1, 6),
                "N_d2": round(Nd2, 6),
                "moneyness": round(S / K, 4),
                "intrinsic_value": round(intrinsic, 4),
                "time_value": round(price - intrinsic, 4),
                "forward_price": round(S * math.exp((r - q) * T), 4),
            },
        )

"""Rainbow / Basket option pricing via correlated Monte Carlo.

Prices options on baskets of multiple correlated assets: best-of,
worst-of, spread, and weighted-average basket payoffs.
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


@ModelRegistry.register
class RainbowBasketModel(BaseSimulatorModel):

    model_id = "rainbow_basket"
    model_name = "Rainbow / Basket Option (MC)"
    product_type = "Multi-Asset Option"
    asset_class = "equity"

    short_description = "Correlated Monte Carlo for basket, best-of, worst-of options"
    long_description = (
        "Prices multi-asset options using correlated geometric Brownian motion via "
        "Cholesky-decomposed Monte Carlo simulation. Supports four payoff types: "
        "weighted basket (call/put on a weighted average), best-of (call on maximum), "
        "worst-of (put on minimum), and spread (difference between two assets). "
        "Correlation between assets drives the price: higher correlation reduces "
        "basket option value but increases best-of/worst-of value."
    )

    when_to_use = [
        "Multi-asset equity derivatives: basket options, outperformance options",
        "When correlation between assets drives the option value",
        "Rainbow options: best-of, worst-of N assets",
        "Spread options on two assets (approximation via MC)",
    ]
    when_not_to_use = [
        "Single-asset options — use analytical models (BSM, etc.)",
        "When stochastic volatility or jumps are important for each asset",
        "Very high-dimensional baskets (>10 assets) — convergence is slow",
        "When analytical approximations suffice (Kirk for 2-asset spreads)",
    ]
    assumptions = [
        "Each asset follows GBM: dS_i/S_i = (r-q_i)dt + σ_i dW_i",
        "Constant pairwise correlations: corr(dW_i, dW_j) = ρ_ij",
        "Constant volatilities, rates, and dividend yields",
        "No early exercise (European only)",
    ]
    limitations = [
        "GBM assumption — no stochastic vol, jumps, or local vol per asset",
        "Flat correlation — no correlation smile or term structure",
        "MC convergence depends on dimensionality and path count",
        "Simplified to 2-3 assets here; production systems handle N assets",
    ]

    formula_latex = (
        r"V = e^{-rT}\,\mathbb{E}\left[\text{payoff}(S_1(T), S_2(T), \ldots)\right]"
        r"\quad\text{with}\quad"
        r"Z = L \cdot \epsilon,\;\; L L^T = \Sigma"
    )
    formula_plain = (
        "Basket Call = exp(-rT) × E[max(w1×S1 + w2×S2 + ... - K, 0)].  "
        "Best-of Call = exp(-rT) × E[max(max(S1,S2,...) - K, 0)].  "
        "Correlated normals via Cholesky: Z = L × ε"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "s1", "Spot 1", "Current price of asset 1",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "s2", "Spot 2", "Current price of asset 2",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "strike", "Strike (K)", "Option strike",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Time to expiration in years",
                "float", 1.0, 0.01, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "vol1", "Vol 1 (σ₁)", "Annualized vol of asset 1",
                "float", 0.20, 0.01, 3.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "vol2", "Vol 2 (σ₂)", "Annualized vol of asset 2",
                "float", 0.25, 0.01, 3.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "rho", "Correlation (ρ)", "Correlation between assets",
                "float", 0.5, -0.999, 0.999, 0.01,
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Continuous risk-free rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q1", "Div Yield 1", "Continuous dividend yield asset 1",
                "float", 0.01, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q2", "Div Yield 2", "Continuous dividend yield asset 2",
                "float", 0.01, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "w1", "Weight 1", "Basket weight for asset 1 (for basket payoff)",
                "float", 0.5, 0.0, 1.0, 0.1,
            ),
            ParameterSpec(
                "w2", "Weight 2", "Basket weight for asset 2 (for basket payoff)",
                "float", 0.5, 0.0, 1.0, 0.1,
            ),
            ParameterSpec(
                "payoff_type", "Payoff Type", "Type of multi-asset payoff",
                "select", "basket_call",
                options=["basket_call", "basket_put", "best_of_call", "worst_of_put"],
            ),
            ParameterSpec(
                "n_paths", "MC Paths", "Number of Monte Carlo paths",
                "int", 100000, 1000, 1000000, 10000,
            ),
            ParameterSpec(
                "seed", "Random Seed", "Random seed (0 = random)",
                "int", 42, 0, 999999, 1,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Equal-Weight Basket Call (ρ=0.5)": {
                "s1": 100.0, "s2": 100.0, "strike": 100.0, "maturity": 1.0,
                "vol1": 0.20, "vol2": 0.25, "rho": 0.5,
                "r": 0.05, "q1": 0.01, "q2": 0.01,
                "w1": 0.5, "w2": 0.5, "payoff_type": "basket_call",
                "n_paths": 100000, "seed": 42,
            },
            "Best-of-Two Call (ρ=0.3)": {
                "s1": 100.0, "s2": 100.0, "strike": 100.0, "maturity": 1.0,
                "vol1": 0.20, "vol2": 0.25, "rho": 0.3,
                "r": 0.05, "q1": 0.01, "q2": 0.01,
                "w1": 0.5, "w2": 0.5, "payoff_type": "best_of_call",
                "n_paths": 100000, "seed": 42,
            },
            "Worst-of-Two Put (ρ=0.7)": {
                "s1": 100.0, "s2": 100.0, "strike": 100.0, "maturity": 1.0,
                "vol1": 0.20, "vol2": 0.25, "rho": 0.7,
                "r": 0.05, "q1": 0.01, "q2": 0.01,
                "w1": 0.5, "w2": 0.5, "payoff_type": "worst_of_put",
                "n_paths": 100000, "seed": 42,
            },
            "Spread Call (outperformance)": {
                "s1": 100.0, "s2": 100.0, "strike": 0.0, "maturity": 1.0,
                "vol1": 0.20, "vol2": 0.25, "rho": 0.5,
                "r": 0.05, "q1": 0.01, "q2": 0.02,
                "w1": 1.0, "w2": -1.0, "payoff_type": "basket_call",
                "n_paths": 100000, "seed": 42,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S1 = float(params["s1"])
        S2 = float(params["s2"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sig1 = float(params["vol1"])
        sig2 = float(params["vol2"])
        rho = float(params["rho"])
        r = float(params["r"])
        q1 = float(params.get("q1", 0.0))
        q2 = float(params.get("q2", 0.0))
        w1 = float(params.get("w1", 0.5))
        w2 = float(params.get("w2", 0.5))
        payoff_type = params.get("payoff_type", "basket_call")
        n_paths = int(params.get("n_paths", 100000))
        seed_val = int(params.get("seed", 42))

        steps: list[CalculationStep] = []

        # Step 1: Cholesky decomposition
        L = np.array([[1.0, 0.0], [rho, math.sqrt(1 - rho**2)]])
        steps.append(CalculationStep(
            step_number=1,
            label="Correlation and Cholesky",
            formula=r"L = \begin{pmatrix} 1 & 0 \\ \rho & \sqrt{1-\rho^2} \end{pmatrix}",
            substitution=(
                f"ρ = {rho},  L = [[1, 0], [{rho}, {math.sqrt(1 - rho**2):.6f}]]"
            ),
            result=round(rho, 4),
            explanation=(
                "Cholesky decomposition of the 2×2 correlation matrix. "
                "Used to generate correlated normal random variables."
            ),
        ))

        # Step 2: simulate terminal values
        rng = np.random.default_rng(seed_val if seed_val > 0 else None)
        eps = rng.standard_normal((2, n_paths))
        Z = L @ eps  # correlated normals

        drift1 = (r - q1 - 0.5 * sig1**2) * T
        drift2 = (r - q2 - 0.5 * sig2**2) * T
        S1_T = S1 * np.exp(drift1 + sig1 * math.sqrt(T) * Z[0])
        S2_T = S2 * np.exp(drift2 + sig2 * math.sqrt(T) * Z[1])

        steps.append(CalculationStep(
            step_number=2,
            label="Terminal asset values",
            formula=(
                r"S_i(T) = S_i \exp\left[(r-q_i-\sigma_i^2/2)T "
                r"+ \sigma_i\sqrt{T}\,Z_i\right]"
            ),
            substitution=(
                f"S1_T: mean={float(np.mean(S1_T)):.2f}, "
                f"S2_T: mean={float(np.mean(S2_T)):.2f}.  "
                f"Realized corr = {float(np.corrcoef(Z[0], Z[1])[0, 1]):.4f}"
            ),
            result=round(float(np.mean(S1_T)), 2),
            explanation="Terminal asset prices simulated via correlated GBM.",
        ))

        # Step 3: compute payoffs
        disc = math.exp(-r * T)
        if payoff_type == "basket_call":
            basket = w1 * S1_T + w2 * S2_T
            payoffs = np.maximum(basket - K, 0.0)
            label = f"Basket Call: max(w1·S1 + w2·S2 - K, 0)"
        elif payoff_type == "basket_put":
            basket = w1 * S1_T + w2 * S2_T
            payoffs = np.maximum(K - basket, 0.0)
            label = f"Basket Put: max(K - w1·S1 - w2·S2, 0)"
        elif payoff_type == "best_of_call":
            best = np.maximum(S1_T, S2_T)
            payoffs = np.maximum(best - K, 0.0)
            label = "Best-of Call: max(max(S1,S2) - K, 0)"
        else:  # worst_of_put
            worst = np.minimum(S1_T, S2_T)
            payoffs = np.maximum(K - worst, 0.0)
            label = "Worst-of Put: max(K - min(S1,S2), 0)"

        price = disc * float(np.mean(payoffs))
        std_err = disc * float(np.std(payoffs)) / math.sqrt(n_paths)

        steps.append(CalculationStep(
            step_number=3,
            label="Payoff and price",
            formula=r"V = e^{-rT} \cdot \frac{1}{M}\sum \text{payoff}_i",
            substitution=(
                f"{label}.  "
                f"Price = {disc:.6f} × {float(np.mean(payoffs)):.4f} = {price:.4f}.  "
                f"Std error = {std_err:.4f}"
            ),
            result=round(price, 4),
            explanation="Discounted average payoff across MC paths.",
        ))

        # Step 4: correlation sensitivity
        # Reprice at ρ ± 0.05
        rho_bump = 0.05
        rho_up = min(rho + rho_bump, 0.999)
        rho_dn = max(rho - rho_bump, -0.999)

        p_up = self._quick_reprice(
            S1, S2, K, T, sig1, sig2, rho_up, r, q1, q2,
            w1, w2, payoff_type, eps,
        )
        p_dn = self._quick_reprice(
            S1, S2, K, T, sig1, sig2, rho_dn, r, q1, q2,
            w1, w2, payoff_type, eps,
        )
        corr_sens = (p_up - p_dn) / (rho_up - rho_dn)

        steps.append(CalculationStep(
            step_number=4,
            label="Correlation sensitivity",
            formula=r"\frac{\partial V}{\partial \rho} \approx \frac{V(\rho+\delta) - V(\rho-\delta)}{2\delta}",
            substitution=(
                f"V(ρ={rho_up:.3f}) = {p_up:.4f},  "
                f"V(ρ={rho_dn:.3f}) = {p_dn:.4f},  "
                f"dV/dρ = {corr_sens:.4f}"
            ),
            result=round(corr_sens, 4),
            explanation=(
                "Sensitivity of the option price to correlation. Basket options "
                "decrease with correlation; best-of options increase."
            ),
        ))

        # Greeks via bump-and-reprice on S1
        bump = 0.01 * S1
        L_orig = L
        Z_orig = Z

        S1_up_T = (S1 + bump) * np.exp(drift1 + sig1 * math.sqrt(T) * Z[0])
        S1_dn_T = (S1 - bump) * np.exp(drift1 + sig1 * math.sqrt(T) * Z[0])

        def _payoff(s1t, s2t):
            if payoff_type == "basket_call":
                return np.maximum(w1 * s1t + w2 * s2t - K, 0.0)
            elif payoff_type == "basket_put":
                return np.maximum(K - w1 * s1t - w2 * s2t, 0.0)
            elif payoff_type == "best_of_call":
                return np.maximum(np.maximum(s1t, s2t) - K, 0.0)
            else:
                return np.maximum(K - np.minimum(s1t, s2t), 0.0)

        p_s1_up = disc * float(np.mean(_payoff(S1_up_T, S2_T)))
        p_s1_dn = disc * float(np.mean(_payoff(S1_dn_T, S2_T)))
        delta_s1 = (p_s1_up - p_s1_dn) / (2 * bump)

        greeks = {
            "delta_s1": round(delta_s1, 6),
            "correlation_sensitivity": round(corr_sens, 4),
        }

        steps.append(CalculationStep(
            step_number=5,
            label="Greeks",
            formula=r"\Delta_{S_1} = \frac{V(S_1+\epsilon) - V(S_1-\epsilon)}{2\epsilon}",
            substitution=f"Δ_S1 = {delta_s1:.6f},  Corr sens = {corr_sens:.4f}",
            result=round(delta_s1, 6),
            explanation="Delta w.r.t. asset 1 and correlation sensitivity.",
        ))

        return SimulatorResult(
            fair_value=round(price, 4),
            method=f"Correlated MC ({n_paths:,} paths, 2-asset GBM)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "payoff_type": payoff_type,
                "correlation": rho,
                "realized_correlation": round(float(np.corrcoef(Z[0], Z[1])[0, 1]), 4),
                "mean_S1_T": round(float(np.mean(S1_T)), 2),
                "mean_S2_T": round(float(np.mean(S2_T)), 2),
                "std_error": round(std_err, 4),
                "n_paths": n_paths,
            },
        )

    def _quick_reprice(self, S1, S2, K, T, sig1, sig2, rho, r, q1, q2,
                       w1, w2, payoff_type, eps):
        L = np.array([[1.0, 0.0], [rho, math.sqrt(1 - rho**2)]])
        Z = L @ eps
        disc = math.exp(-r * T)
        S1_T = S1 * np.exp((r - q1 - 0.5 * sig1**2) * T + sig1 * math.sqrt(T) * Z[0])
        S2_T = S2 * np.exp((r - q2 - 0.5 * sig2**2) * T + sig2 * math.sqrt(T) * Z[1])
        if payoff_type == "basket_call":
            payoffs = np.maximum(w1 * S1_T + w2 * S2_T - K, 0.0)
        elif payoff_type == "basket_put":
            payoffs = np.maximum(K - w1 * S1_T - w2 * S2_T, 0.0)
        elif payoff_type == "best_of_call":
            payoffs = np.maximum(np.maximum(S1_T, S2_T) - K, 0.0)
        else:
            payoffs = np.maximum(K - np.minimum(S1_T, S2_T), 0.0)
        return disc * float(np.mean(payoffs))

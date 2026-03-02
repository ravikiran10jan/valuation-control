"""Cox-Ross-Rubinstein (CRR) Binomial Tree for American & European options.

The workhorse lattice model that handles American early exercise.
Converges to Black-Scholes as the number of steps increases.
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
class BinomialTreeModel(BaseSimulatorModel):

    model_id = "binomial_tree"
    model_name = "CRR Binomial Tree"
    product_type = "European & American Vanilla Options"
    asset_class = "equity"

    short_description = (
        "Lattice pricing for American and European options via Cox-Ross-Rubinstein"
    )
    long_description = (
        "The Cox-Ross-Rubinstein (1979) binomial tree is a discrete-time model that "
        "approximates GBM by constructing a recombining lattice of up/down spot moves. "
        "At each node, the spot either rises by factor u = exp(σ√Δt) or falls by "
        "d = 1/u. The risk-neutral probability p = (exp((r-q)Δt) - d) / (u - d) "
        "ensures no-arbitrage. Option prices are computed by backward induction from "
        "the terminal payoff. For American options, early exercise is checked at every "
        "node. The model converges to Black-Scholes as N → ∞ and is the standard "
        "method for American equity options."
    )

    when_to_use = [
        "American options — the primary use case (early exercise)",
        "European options as a cross-check against analytical formulas",
        "Options on dividend-paying stocks with discrete dividends",
        "When you need to visualize the exercise boundary",
        "Educational: shows how risk-neutral pricing works step by step",
    ]
    when_not_to_use = [
        "Path-dependent options (barriers, Asians) — use MC or PDE",
        "Multi-asset options — tree dimensionality explodes",
        "When speed is critical and an analytical formula exists (use BSM)",
        "Very long-dated options with many steps (slow convergence)",
    ]
    assumptions = [
        "Underlying follows GBM: dS = (r-q)S dt + σS dW",
        "Constant volatility, risk-free rate, and dividend yield",
        "Recombining tree: u × d = 1",
        "Risk-neutral pricing with discrete time steps",
        "No transaction costs or market frictions",
    ]
    limitations = [
        "Convergence is O(1/N) — need many steps for accuracy",
        "Odd-even oscillation: prices oscillate as N increases",
        "Cannot easily handle stochastic volatility or jumps",
        "Memory O(N²) for storing the full tree (though O(N) possible)",
    ]

    formula_latex = (
        r"u = e^{\sigma\sqrt{\Delta t}},\quad d = e^{-\sigma\sqrt{\Delta t}},\quad"
        r"p = \frac{e^{(r-q)\Delta t} - d}{u - d}"
    )
    formula_plain = (
        "u = exp(σ√Δt), d = 1/u, p = (exp((r-q)Δt) - d)/(u-d).  "
        "Backward induction: V(i,j) = exp(-rΔt) × [p×V(i+1,j+1) + (1-p)×V(i+1,j)].  "
        "American: V(i,j) = max(V(i,j), exercise_value(i,j))"
    )

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
            ParameterSpec(
                "exercise", "Exercise Style", "European or American",
                "select", "american", options=["american", "european"],
            ),
            ParameterSpec(
                "n_steps", "Tree Steps (N)", "Number of time steps in the tree",
                "int", 200, 10, 2000, 10,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "American Put ATM": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "vol": 0.20, "r": 0.05, "q": 0.0,
                "option_type": "put", "exercise": "american", "n_steps": 200,
            },
            "American Call with Dividends": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "vol": 0.25, "r": 0.05, "q": 0.03,
                "option_type": "call", "exercise": "american", "n_steps": 200,
            },
            "European Call (BSM benchmark)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "vol": 0.20, "r": 0.05, "q": 0.0,
                "option_type": "call", "exercise": "european", "n_steps": 500,
            },
            "Deep OTM American Put": {
                "spot": 100.0, "strike": 80.0, "maturity": 0.5,
                "vol": 0.30, "r": 0.05, "q": 0.0,
                "option_type": "put", "exercise": "american", "n_steps": 200,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        opt_type = params.get("option_type", "call").lower()
        exercise = params.get("exercise", "american").lower()
        N = int(params.get("n_steps", 200))
        is_call = opt_type == "call"
        is_american = exercise == "american"

        steps: list[CalculationStep] = []
        dt = T / N

        # Step 1: tree parameters
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        disc = math.exp(-r * dt)
        p = (math.exp((r - q) * dt) - d) / (u - d)

        steps.append(CalculationStep(
            step_number=1,
            label="Tree parameters",
            formula=(
                r"u = e^{\sigma\sqrt{\Delta t}},\; d = 1/u,\; "
                r"p = \frac{e^{(r-q)\Delta t} - d}{u - d}"
            ),
            substitution=(
                f"Δt = {T}/{N} = {dt:.6f},  u = {u:.6f},  d = {d:.6f},  "
                f"p = {p:.6f},  disc = e^(-r·Δt) = {disc:.6f}"
            ),
            result=round(p, 6),
            explanation=(
                "u and d are the up/down factors per step. p is the risk-neutral "
                "probability of an up move. disc is the one-step discount factor."
            ),
        ))

        # Step 2: build terminal payoffs
        # Using numpy for efficiency
        j_arr = np.arange(N + 1)
        S_terminal = S * (u ** (N - j_arr)) * (d ** j_arr)
        if is_call:
            payoff = np.maximum(S_terminal - K, 0.0)
        else:
            payoff = np.maximum(K - S_terminal, 0.0)

        steps.append(CalculationStep(
            step_number=2,
            label="Terminal payoffs",
            formula=(
                r"S_{N,j} = S \cdot u^{N-j} \cdot d^{j},\quad"
                r"\text{payoff}_{N,j} = \max(S_{N,j} - K, 0)"
                if is_call else
                r"S_{N,j} = S \cdot u^{N-j} \cdot d^{j},\quad"
                r"\text{payoff}_{N,j} = \max(K - S_{N,j}, 0)"
            ),
            substitution=(
                f"S ranges from {S_terminal[0]:.2f} (all up) to "
                f"{S_terminal[-1]:.2f} (all down).  "
                f"Max payoff = {payoff.max():.4f},  "
                f"ITM nodes at expiry = {int(np.sum(payoff > 0))}/{N + 1}"
            ),
            result=round(float(payoff.max()), 4),
            explanation="Payoff at each terminal node of the tree.",
        ))

        # Step 3: backward induction
        V = payoff.copy()
        early_exercise_count = 0

        for i in range(N - 1, -1, -1):
            V_new = disc * (p * V[:i + 1] + (1 - p) * V[1:i + 2])
            if is_american:
                j_idx = np.arange(i + 1)
                S_nodes = S * (u ** (i - j_idx)) * (d ** j_idx)
                if is_call:
                    exercise_val = np.maximum(S_nodes - K, 0.0)
                else:
                    exercise_val = np.maximum(K - S_nodes, 0.0)
                exercised = exercise_val > V_new
                early_exercise_count += int(np.sum(exercised))
                V_new = np.maximum(V_new, exercise_val)
            V = V_new

        price = float(V[0])

        steps.append(CalculationStep(
            step_number=3,
            label="Backward induction",
            formula=(
                r"V_{i,j} = e^{-r\Delta t}[p \cdot V_{i+1,j} + (1-p) \cdot V_{i+1,j+1}]"
                + (r"\quad\text{then } V_{i,j} = \max(V_{i,j},\, \text{exercise})"
                   if is_american else "")
            ),
            substitution=(
                f"{'American' if is_american else 'European'} "
                f"{'call' if is_call else 'put'}: "
                f"price at root = {price:.6f}"
                + (f".  Early exercise optimal at {early_exercise_count} nodes"
                   if is_american else "")
            ),
            result=round(price, 6),
            explanation=(
                "Roll back through the tree from expiry to today. "
                + ("At each node, check if immediate exercise beats continuation."
                   if is_american else "No early exercise check for European.")
            ),
        ))

        # Step 4: BSM benchmark
        from scipy.stats import norm
        sqrt_T = math.sqrt(T)
        d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        df_q = math.exp(-q * T)
        df_r = math.exp(-r * T)
        if is_call:
            bsm = S * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
        else:
            bsm = K * df_r * norm.cdf(-d2) - S * df_q * norm.cdf(-d1)

        early_premium = price - bsm if is_american else 0.0

        steps.append(CalculationStep(
            step_number=4,
            label="BSM benchmark comparison",
            formula=r"\text{Early exercise premium} = V_{tree} - V_{BSM}",
            substitution=(
                f"BSM ({exercise} {'call' if is_call else 'put'}) = {bsm:.6f}.  "
                f"Tree price = {price:.6f}.  "
                f"Early exercise premium = {early_premium:.6f}"
            ),
            result=round(early_premium, 6),
            explanation=(
                "For European options the tree should converge to BSM. "
                "For American options the difference is the early exercise premium."
            ),
        ))

        # Step 5: Greeks via finite differences on the tree
        # Rebuild small portion of the tree for Greeks
        # Delta: from step-1 nodes
        S_u = S * u
        S_d = S * d
        # Reprice at S_u and S_d (quick 1-step-smaller trees)
        V_u = self._reprice(S_u, K, T - dt, sigma, r, q, is_call, is_american, N - 1)
        V_d = self._reprice(S_d, K, T - dt, sigma, r, q, is_call, is_american, N - 1)
        delta = (V_u - V_d) / (S_u - S_d)

        # Gamma
        V_uu = self._reprice(S * u * u, K, T - 2 * dt, sigma, r, q, is_call, is_american, max(N - 2, 10))
        V_ud = self._reprice(S, K, T - 2 * dt, sigma, r, q, is_call, is_american, max(N - 2, 10))
        V_dd = self._reprice(S * d * d, K, T - 2 * dt, sigma, r, q, is_call, is_american, max(N - 2, 10))
        delta_u = (V_uu - V_ud) / (S * u * u - S)
        delta_d = (V_ud - V_dd) / (S - S * d * d)
        h_gamma = 0.5 * (S * u * u - S * d * d)
        gamma = (delta_u - delta_d) / h_gamma if h_gamma > 0 else 0.0

        # Theta
        theta = (V_ud - price) / (2 * dt) if T > 2 * dt else 0.0

        # Vega (bump vol +1%)
        V_vup = self._reprice(S, K, T, sigma + 0.01, r, q, is_call, is_american, N)
        vega = V_vup - price

        # Rho (bump r +1bp)
        V_rup = self._reprice(S, K, T, sigma, r + 0.0001, q, is_call, is_american, N)
        rho = (V_rup - price) / 0.0001 * 0.01  # per 1%

        greeks = {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "theta": round(theta / 365, 6),
            "vega": round(vega, 6),
            "rho": round(rho, 6),
        }

        steps.append(CalculationStep(
            step_number=5,
            label="Greeks",
            formula=(
                r"\Delta = \frac{V_u - V_d}{S_u - S_d},\quad"
                r"\Gamma = \frac{\Delta_u - \Delta_d}{h}"
            ),
            substitution=(
                f"Δ={delta:.6f}  Γ={gamma:.6f}  "
                f"Θ={theta / 365:.4f}/day  "
                f"Vega={vega:.4f}/1%vol  ρ={rho:.4f}/1%"
            ),
            result=round(delta, 6),
            explanation="Greeks computed from the tree via finite differences.",
        ))

        intrinsic = max(S - K, 0) if is_call else max(K - S, 0)

        return SimulatorResult(
            fair_value=round(price, 4),
            method=f"CRR Binomial Tree ({N} steps, {exercise})",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "u": round(u, 6),
                "d": round(d, 6),
                "p": round(p, 6),
                "n_steps": N,
                "exercise": exercise,
                "bsm_price": round(bsm, 6),
                "early_exercise_premium": round(early_premium, 6),
                "early_exercise_nodes": early_exercise_count if is_american else 0,
                "intrinsic_value": round(intrinsic, 4),
                "time_value": round(price - intrinsic, 4),
                "tree_vs_bsm_diff": round(price - bsm, 6),
            },
        )

    def _reprice(self, S: float, K: float, T: float, sigma: float,
                 r: float, q: float, is_call: bool, is_american: bool,
                 N: int) -> float:
        """Quick reprice for Greeks computation."""
        if T <= 0 or N <= 0:
            if is_call:
                return max(S - K, 0.0)
            return max(K - S, 0.0)

        dt = T / N
        u = math.exp(sigma * math.sqrt(dt))
        d = 1.0 / u
        disc = math.exp(-r * dt)
        p = (math.exp((r - q) * dt) - d) / (u - d)

        j_arr = np.arange(N + 1)
        S_term = S * (u ** (N - j_arr)) * (d ** j_arr)
        if is_call:
            V = np.maximum(S_term - K, 0.0)
        else:
            V = np.maximum(K - S_term, 0.0)

        for i in range(N - 1, -1, -1):
            V = disc * (p * V[:i + 1] + (1 - p) * V[1:i + 2])
            if is_american:
                j_idx = np.arange(i + 1)
                S_nodes = S * (u ** (i - j_idx)) * (d ** j_idx)
                if is_call:
                    ex = np.maximum(S_nodes - K, 0.0)
                else:
                    ex = np.maximum(K - S_nodes, 0.0)
                V = np.maximum(V, ex)

        return float(V[0])

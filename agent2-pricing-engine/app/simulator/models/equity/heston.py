"""Heston stochastic volatility model — Monte Carlo pricing.

The industry-standard stochastic vol model for equity options.
Captures the volatility smile through correlated vol dynamics.
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


@ModelRegistry.register
class HestonModel(BaseSimulatorModel):

    model_id = "heston"
    model_name = "Heston Stochastic Volatility"
    product_type = "European Vanilla Option"
    asset_class = "equity"

    short_description = (
        "Monte Carlo pricing under Heston stochastic vol with correlated dynamics"
    )
    long_description = (
        "The Heston (1993) model extends Black-Scholes by making volatility itself "
        "stochastic. The variance follows a CIR (mean-reverting square-root) process "
        "correlated with the spot: dv = κ(θ - v)dt + ξ√v dW_v, with ρ = corr(dW_S, dW_v). "
        "This generates a volatility smile/skew endogenously. Negative ρ produces the "
        "equity skew (vol rises when spot falls). The model is priced here via Monte "
        "Carlo simulation with full truncation to keep variance positive."
    )

    when_to_use = [
        "When the volatility smile/skew is important for pricing",
        "Long-dated equity options where vol dynamics matter",
        "When BSM flat-vol assumption is too crude",
        "Calibrating to a range of strikes and maturities simultaneously",
        "As a benchmark stochastic vol model for model comparison",
    ]
    when_not_to_use = [
        "Quick indicative pricing — BSM is faster for simple cases",
        "When a single implied vol suffices (ATM options in liquid markets)",
        "Path-dependent exotics with barriers (local vol may be better)",
        "When calibration data is limited (5 parameters need a rich surface)",
        "Very short-dated options where MC convergence is slow",
    ]
    assumptions = [
        "dS/S = (r - q)dt + √v dW_S",
        "dv = κ(θ - v)dt + ξ√v dW_v",
        "corr(dW_S, dW_v) = ρ",
        "Feller condition: 2κθ > ξ² (ensures variance stays positive)",
        "Constant risk-free rate and dividend yield",
    ]
    limitations = [
        "MC convergence requires many paths for accurate prices",
        "5 parameters to calibrate — can overfit noisy market data",
        "Feller condition often violated in practice (need truncation scheme)",
        "Smile dynamics may not match market (forward smile is model-specific)",
        "Cannot easily handle discrete dividends",
    ]

    formula_latex = (
        r"dS = (r-q)S\,dt + \sqrt{v}\,S\,dW_S"
        r"\quad"
        r"dv = \kappa(\theta - v)\,dt + \xi\sqrt{v}\,dW_v"
        r"\quad"
        r"\rho = \text{corr}(dW_S, dW_v)"
    )
    formula_plain = (
        "dS/S = (r-q)dt + √v dW_S,  dv = κ(θ-v)dt + ξ√v dW_v,  "
        "corr(dW_S, dW_v) = ρ"
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
                "float", 1.0, 0.01, 30.0, 0.01, unit="years",
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
                "v0", "Initial Variance (v₀)", "Current instantaneous variance",
                "float", 0.04, 0.001, 4.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "kappa", "Mean Reversion (κ)", "Speed of variance mean reversion",
                "float", 2.0, 0.01, 20.0, 0.1,
            ),
            ParameterSpec(
                "theta", "Long-Run Variance (θ)", "Long-term variance level",
                "float", 0.04, 0.001, 4.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "xi", "Vol of Vol (ξ)", "Volatility of the variance process",
                "float", 0.3, 0.01, 5.0, 0.01,
            ),
            ParameterSpec(
                "rho", "Correlation (ρ)", "Correlation between spot and vol Brownians",
                "float", -0.7, -0.999, 0.999, 0.01,
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call or Put",
                "select", "call", options=["call", "put"],
            ),
            ParameterSpec(
                "n_paths", "MC Paths", "Number of Monte Carlo paths",
                "int", 100000, 1000, 1000000, 10000,
            ),
            ParameterSpec(
                "n_steps", "Time Steps", "Number of time steps per path",
                "int", 252, 50, 1000, 10,
            ),
            ParameterSpec(
                "seed", "Random Seed", "Random seed (0 = random)",
                "int", 42, 0, 999999, 1,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "ATM Call (equity skew)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "r": 0.05, "q": 0.0, "v0": 0.04, "kappa": 2.0,
                "theta": 0.04, "xi": 0.3, "rho": -0.7,
                "option_type": "call", "n_paths": 100000, "n_steps": 252, "seed": 42,
            },
            "OTM Put (skew effect)": {
                "spot": 100.0, "strike": 90.0, "maturity": 0.5,
                "r": 0.05, "q": 0.0, "v0": 0.04, "kappa": 2.0,
                "theta": 0.04, "xi": 0.3, "rho": -0.7,
                "option_type": "put", "n_paths": 100000, "n_steps": 126, "seed": 42,
            },
            "Long-dated LEAPS Call": {
                "spot": 150.0, "strike": 100.0, "maturity": 2.0,
                "r": 0.05, "q": 0.01, "v0": 0.09, "kappa": 1.5,
                "theta": 0.06, "xi": 0.4, "rho": -0.6,
                "option_type": "call", "n_paths": 100000, "n_steps": 504, "seed": 42,
            },
            "Zero correlation (symmetric smile)": {
                "spot": 100.0, "strike": 100.0, "maturity": 1.0,
                "r": 0.05, "q": 0.0, "v0": 0.04, "kappa": 2.0,
                "theta": 0.04, "xi": 0.3, "rho": 0.0,
                "option_type": "call", "n_paths": 100000, "n_steps": 252, "seed": 42,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S0 = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        v0 = float(params["v0"])
        kappa = float(params["kappa"])
        theta = float(params["theta"])
        xi = float(params["xi"])
        rho = float(params["rho"])
        opt_type = params.get("option_type", "call").lower()
        n_paths = int(params.get("n_paths", 100000))
        n_steps = int(params.get("n_steps", 252))
        seed_val = int(params.get("seed", 42))
        is_call = opt_type == "call"

        steps: list[CalculationStep] = []
        dt = T / n_steps

        # Step 1: model parameters
        feller = 2 * kappa * theta / (xi**2)
        steps.append(CalculationStep(
            step_number=1,
            label="Heston parameters",
            formula=(
                r"\text{Feller ratio} = \frac{2\kappa\theta}{\xi^2}"
            ),
            substitution=(
                f"v₀={v0:.4f} (σ₀={math.sqrt(v0):.3f}), κ={kappa}, θ={theta:.4f} "
                f"(σ_∞={math.sqrt(theta):.3f}), ξ={xi}, ρ={rho}.  "
                f"Feller = {feller:.3f} {'≥ 1 (satisfied)' if feller >= 1 else '< 1 (violated — need truncation)'}"
            ),
            result=round(feller, 3),
            explanation=(
                "The Feller condition 2κθ > ξ² ensures the variance process "
                "never touches zero. When violated, we use full truncation."
            ),
        ))

        # Step 2: simulate paths
        rng = np.random.default_rng(seed_val if seed_val > 0 else None)
        Z1 = rng.standard_normal((n_paths, n_steps))
        Z2 = rng.standard_normal((n_paths, n_steps))
        W_S = Z1
        W_v = rho * Z1 + math.sqrt(1 - rho**2) * Z2

        log_S = np.full(n_paths, math.log(S0))
        v = np.full(n_paths, v0)

        for t in range(n_steps):
            v_pos = np.maximum(v, 0.0)  # full truncation
            sqrt_v = np.sqrt(v_pos)
            log_S += (r - q - 0.5 * v_pos) * dt + sqrt_v * math.sqrt(dt) * W_S[:, t]
            v += kappa * (theta - v_pos) * dt + xi * sqrt_v * math.sqrt(dt) * W_v[:, t]

        S_final = np.exp(log_S)

        steps.append(CalculationStep(
            step_number=2,
            label="Monte Carlo simulation",
            formula=(
                r"\ln S_{t+dt} = \ln S_t + (r-q-v/2)dt + \sqrt{v}\sqrt{dt}\,Z_1"
            ),
            substitution=(
                f"Simulated {n_paths:,} paths × {n_steps} steps.  "
                f"S_final: mean={float(np.mean(S_final)):.2f}, "
                f"std={float(np.std(S_final)):.2f},  "
                f"v_final: mean={float(np.mean(np.maximum(v, 0))):.4f}"
            ),
            result=round(float(np.mean(S_final)), 2),
            explanation=(
                "Euler-Maruyama discretization with full truncation "
                "scheme to handle negative variance."
            ),
        ))

        # Step 3: option payoff
        disc = math.exp(-r * T)
        if is_call:
            payoffs = np.maximum(S_final - K, 0.0)
        else:
            payoffs = np.maximum(K - S_final, 0.0)

        price = disc * float(np.mean(payoffs))
        std_err = disc * float(np.std(payoffs)) / math.sqrt(n_paths)

        steps.append(CalculationStep(
            step_number=3,
            label="Option price",
            formula=r"V = e^{-rT} \cdot \frac{1}{M}\sum_{i=1}^{M} \max(S_T^{(i)} - K, 0)",
            substitution=(
                f"Price = e^(-{r}×{T}) × mean(payoffs) = "
                f"{disc:.6f} × {float(np.mean(payoffs)):.4f} = {price:.4f}.  "
                f"Std error = {std_err:.4f}"
            ),
            result=round(price, 4),
            explanation="Discounted average payoff across all MC paths.",
        ))

        # Step 4: BSM benchmark
        sqrt_T = math.sqrt(T)
        sigma_bsm = math.sqrt(v0)
        d1 = (math.log(S0 / K) + (r - q + 0.5 * v0) * T) / (sigma_bsm * sqrt_T)
        d2 = d1 - sigma_bsm * sqrt_T
        df_q = math.exp(-q * T)
        df_r = math.exp(-r * T)
        if is_call:
            bsm = S0 * df_q * norm.cdf(d1) - K * df_r * norm.cdf(d2)
        else:
            bsm = K * df_r * norm.cdf(-d2) - S0 * df_q * norm.cdf(-d1)

        steps.append(CalculationStep(
            step_number=4,
            label="BSM comparison (at σ₀)",
            formula=r"V_{BSM}(\sigma = \sqrt{v_0})",
            substitution=(
                f"BSM at σ={sigma_bsm:.4f}: {bsm:.4f}.  "
                f"Heston: {price:.4f}.  "
                f"Difference: {price - bsm:.4f} "
                f"({'Heston higher' if price > bsm else 'Heston lower'})"
            ),
            result=round(price - bsm, 4),
            explanation=(
                "Comparison with flat-vol BSM at the initial vol. Differences "
                "arise from stochastic vol, correlation, and vol-of-vol effects."
            ),
        ))

        # Step 5: Greeks via pathwise bumps
        bump_S = 0.01 * S0
        # Delta: bump spot
        log_S_up = np.full(n_paths, math.log(S0 + bump_S))
        log_S_dn = np.full(n_paths, math.log(S0 - bump_S))
        v_up = np.full(n_paths, v0)
        v_dn = np.full(n_paths, v0)
        for t in range(n_steps):
            v_pos_u = np.maximum(v_up, 0.0)
            v_pos_d = np.maximum(v_dn, 0.0)
            log_S_up += (r - q - 0.5 * v_pos_u) * dt + np.sqrt(v_pos_u) * math.sqrt(dt) * W_S[:, t]
            log_S_dn += (r - q - 0.5 * v_pos_d) * dt + np.sqrt(v_pos_d) * math.sqrt(dt) * W_S[:, t]
            v_up += kappa * (theta - v_pos_u) * dt + xi * np.sqrt(v_pos_u) * math.sqrt(dt) * W_v[:, t]
            v_dn += kappa * (theta - v_pos_d) * dt + xi * np.sqrt(v_pos_d) * math.sqrt(dt) * W_v[:, t]

        S_up_f = np.exp(log_S_up)
        S_dn_f = np.exp(log_S_dn)
        if is_call:
            p_up = disc * float(np.mean(np.maximum(S_up_f - K, 0.0)))
            p_dn = disc * float(np.mean(np.maximum(S_dn_f - K, 0.0)))
        else:
            p_up = disc * float(np.mean(np.maximum(K - S_up_f, 0.0)))
            p_dn = disc * float(np.mean(np.maximum(K - S_dn_f, 0.0)))

        delta = (p_up - p_dn) / (2 * bump_S)
        gamma = (p_up - 2 * price + p_dn) / (bump_S**2)

        # Vega: bump vol by 1% (0.01) — matches BSM convention
        sigma0 = math.sqrt(v0)
        sigma_bumped = sigma0 + 0.01
        v0_bumped = sigma_bumped ** 2
        log_S_vup = np.full(n_paths, math.log(S0))
        v_vup = np.full(n_paths, v0_bumped)
        for t in range(n_steps):
            vp = np.maximum(v_vup, 0.0)
            log_S_vup += (r - q - 0.5 * vp) * dt + np.sqrt(vp) * math.sqrt(dt) * W_S[:, t]
            v_vup += kappa * (theta - vp) * dt + xi * np.sqrt(vp) * math.sqrt(dt) * W_v[:, t]
        S_vup_f = np.exp(log_S_vup)
        if is_call:
            p_vup = disc * float(np.mean(np.maximum(S_vup_f - K, 0.0)))
        else:
            p_vup = disc * float(np.mean(np.maximum(K - S_vup_f, 0.0)))
        vega = p_vup - price  # per 1% vol move (σ + 0.01)

        # Theta: reprice with slightly shorter maturity
        theta_bump = 1.0 / 365.0  # 1-day bump
        if T > theta_bump:
            n_steps_th = max(int(n_steps * (T - theta_bump) / T), 1)
            dt_th = (T - theta_bump) / n_steps_th
            disc_th = math.exp(-r * (T - theta_bump))
            log_S_th = np.full(n_paths, math.log(S0))
            v_th = np.full(n_paths, v0)
            for t in range(n_steps_th):
                vp = np.maximum(v_th, 0.0)
                log_S_th += (r - q - 0.5 * vp) * dt_th + np.sqrt(vp) * math.sqrt(dt_th) * W_S[:, t % n_steps]
                v_th += kappa * (theta - vp) * dt_th + xi * np.sqrt(vp) * math.sqrt(dt_th) * W_v[:, t % n_steps]
            S_th_f = np.exp(log_S_th)
            if is_call:
                p_th = disc_th * float(np.mean(np.maximum(S_th_f - K, 0.0)))
            else:
                p_th = disc_th * float(np.mean(np.maximum(K - S_th_f, 0.0)))
            theta_greek = (p_th - price)  # 1-day theta (negative = time decay)
        else:
            theta_greek = -price  # near-expiry: full loss

        # Rho: bump risk-free rate by 1% (0.01)
        r_bumped = r + 0.01
        disc_rho = math.exp(-r_bumped * T)
        log_S_rho = np.full(n_paths, math.log(S0))
        v_rho = np.full(n_paths, v0)
        for t in range(n_steps):
            vp = np.maximum(v_rho, 0.0)
            log_S_rho += (r_bumped - q - 0.5 * vp) * dt + np.sqrt(vp) * math.sqrt(dt) * W_S[:, t]
            v_rho += kappa * (theta - vp) * dt + xi * np.sqrt(vp) * math.sqrt(dt) * W_v[:, t]
        S_rho_f = np.exp(log_S_rho)
        if is_call:
            p_rho = disc_rho * float(np.mean(np.maximum(S_rho_f - K, 0.0)))
        else:
            p_rho = disc_rho * float(np.mean(np.maximum(K - S_rho_f, 0.0)))
        rho_greek = p_rho - price  # per 1% rate move

        greeks = {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
            "vega": round(vega, 6),
            "theta": round(theta_greek, 6),
            "rho": round(rho_greek, 6),
        }

        steps.append(CalculationStep(
            step_number=5,
            label="Greeks (pathwise finite difference)",
            formula=r"\Delta = \frac{V(S+\epsilon) - V(S-\epsilon)}{2\epsilon}",
            substitution=(
                f"Δ={delta:.6f}  Γ={gamma:.6f}  "
                f"V={vega:.4f}/1%  "
                f"Θ={theta_greek:.4f}/day  ρ={rho_greek:.4f}/1%"
            ),
            result=round(delta, 6),
            explanation="Greeks computed via same-seed MC finite differences.",
        ))

        return SimulatorResult(
            fair_value=round(price, 4),
            method=f"Heston MC ({n_paths:,} paths, Euler full truncation)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "heston_price": round(price, 4),
                "bsm_price": round(bsm, 4),
                "heston_minus_bsm": round(price - bsm, 4),
                "std_error": round(std_err, 4),
                "feller_ratio": round(feller, 3),
                "feller_satisfied": feller >= 1,
                "n_paths": n_paths,
                "n_steps": n_steps,
                "mean_terminal_spot": round(float(np.mean(S_final)), 2),
                "mean_terminal_var": round(float(np.mean(np.maximum(v, 0))), 4),
            },
        )

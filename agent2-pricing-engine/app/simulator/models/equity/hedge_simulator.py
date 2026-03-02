"""Delta Hedging Simulator — compare hedging effectiveness across models.

Simulates the P&L of delta-hedging a sold option using deltas computed
from different pricing models (BSM, CEV, Variance Gamma).  Demonstrates
that model misspecification leads to systematic hedging error.

This is the interviewer's Pyxis Systems work: comparing BSM, CEV, and VG
for LEAPS pricing and hedging.
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


# ── BSM helpers ───────────────────────────────────────────────

def _bsm_price(S, K, T, sigma, r, q, is_call=True):
    if T <= 1e-12:
        return max(S - K, 0) if is_call else max(K - S, 0)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return S * math.exp(-q * T) * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * math.exp(-q * T) * norm.cdf(-d1)


def _bsm_delta(S, K, T, sigma, r, q, is_call=True):
    if T <= 1e-12:
        if is_call:
            return 1.0 if S > K else 0.0
        return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    if is_call:
        return math.exp(-q * T) * norm.cdf(d1)
    return -math.exp(-q * T) * norm.cdf(-d1)


# ── GBM path simulation ──────────────────────────────────────

def _simulate_gbm(S0, r, q, sigma, T, n_steps, n_paths, rng):
    dt = T / n_steps
    z = rng.standard_normal((n_paths, n_steps))
    log_returns = (r - q - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z
    log_prices = np.cumsum(log_returns, axis=1)
    log_prices = np.insert(log_prices, 0, 0.0, axis=1)
    return S0 * np.exp(log_prices)


def _simulate_cev(S0, r, q, sigma, beta, T, n_steps, n_paths, rng):
    """Euler-Maruyama discretisation of CEV: dS = μS dt + σ S^β dW."""
    dt = T / n_steps
    mu = r - q
    paths = np.zeros((n_paths, n_steps + 1))
    paths[:, 0] = S0
    for i in range(n_steps):
        S = paths[:, i]
        S_pos = np.maximum(S, 1e-8)
        dW = rng.standard_normal(n_paths) * math.sqrt(dt)
        dS = mu * S_pos * dt + sigma * S_pos**beta * dW
        paths[:, i + 1] = np.maximum(S + dS, 1e-8)
    return paths


def _simulate_vg(S0, r, q, sigma, theta, nu, T, n_steps, n_paths, rng):
    """Simulate VG paths: S(t) = S0 exp((r-q+ω)t + X(t)) where X is VG."""
    dt = T / n_steps
    omega = (1.0 / nu) * math.log(1.0 - theta * nu - 0.5 * sigma**2 * nu)
    drift_per_step = (r - q + omega) * dt

    log_prices = np.zeros((n_paths, n_steps + 1))
    for i in range(n_steps):
        # Gamma time increments: mean=dt, var=nu*dt → shape=dt/nu, scale=nu
        dG = rng.gamma(shape=dt / nu, scale=nu, size=n_paths)
        dX = theta * dG + sigma * np.sqrt(dG) * rng.standard_normal(n_paths)
        log_prices[:, i + 1] = log_prices[:, i] + drift_per_step + dX

    return S0 * np.exp(log_prices)


@ModelRegistry.register
class HedgeSimulatorModel(BaseSimulatorModel):

    model_id = "hedge_simulator"
    model_name = "Delta Hedging Simulator"
    product_type = "Hedging Analysis"
    asset_class = "equity"

    short_description = (
        "Compare hedging P&L across BSM, CEV, and VG delta models"
    )
    long_description = (
        "Simulates the profit & loss of dynamically delta-hedging a sold "
        "European call option. The 'true' stock price process can be GBM, "
        "CEV, or Variance Gamma, while the hedging delta is computed from "
        "a potentially different model. This demonstrates model misspecification "
        "risk: using BSM deltas in a CEV or VG world leads to systematic hedging "
        "error. The simulator runs many paths and reports the P&L distribution — "
        "mean, standard deviation, and percentiles."
    )

    when_to_use = [
        "Understanding the practical impact of model choice on hedging P&L",
        "Quantifying model risk: how wrong can BSM hedging be?",
        "Comparing rebalancing frequency effects on hedge quality",
        "Teaching/interview: demonstrating why model choice matters for Greeks",
        "Stress-testing hedging strategies under different market dynamics",
    ]
    when_not_to_use = [
        "Pricing options (this tool analyses hedging, not pricing)",
        "When you need fast, real-time hedging decisions",
        "Production risk management (this is a simplified educational simulator)",
        "Multi-asset or portfolio hedging (single-option only)",
    ]
    assumptions = [
        "Single European call option sold at model price",
        "Delta-hedging with the underlying only (no vega hedging)",
        "No transaction costs or bid-ask spread",
        "Continuous dividend yield, constant interest rate",
        "Discrete rebalancing at fixed intervals",
    ]
    limitations = [
        "Simplified — no transaction costs, market impact, or liquidity constraints",
        "Only delta hedging (no gamma/vega hedging overlay)",
        "Euler discretisation for CEV paths may have bias for large time steps",
        "Limited number of paths for speed (1000 default)",
    ]

    formula_latex = (
        r"\text{Hedge P\&L} = \sum_{i=0}^{N-1} \Delta_i (S_{i+1} - S_i)"
        r" + B_i(e^{r\,dt} - 1) - \max(S_T - K, 0) + C_0"
    )
    formula_plain = (
        "Hedge P&L = Σ Δᵢ(Sᵢ₊₁ - Sᵢ) + Bᵢ(e^(r·dt) - 1) - payoff + premium"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Price (S)", "Current stock price",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "strike", "Strike Price (K)", "Option strike",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Years",
                "float", 1.0, 0.01, 5.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "sigma", "Volatility (σ)", "Volatility parameter",
                "float", 0.20, 0.01, 2.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate", "Continuous rate",
                "float", 0.05, 0.0, 0.3, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield", "Continuous dividend yield",
                "float", 0.0, 0.0, 0.2, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "true_process", "True Process",
                "The actual process generating stock prices",
                "select", "gbm", options=["gbm", "cev", "variance_gamma"],
            ),
            ParameterSpec(
                "hedge_model", "Hedge Model",
                "Model used to compute hedging deltas",
                "select", "bsm", options=["bsm"],
            ),
            ParameterSpec(
                "cev_beta", "CEV β (if true_process=cev)",
                "CEV elasticity for simulation",
                "float", 0.5, 0.0, 1.5, 0.05,
            ),
            ParameterSpec(
                "vg_theta", "VG θ (if true_process=vg)",
                "VG skew parameter",
                "float", -0.15, -1.0, 1.0, 0.01,
            ),
            ParameterSpec(
                "vg_nu", "VG ν (if true_process=vg)",
                "VG kurtosis parameter",
                "float", 0.25, 0.01, 2.0, 0.01,
            ),
            ParameterSpec(
                "n_paths", "Simulation Paths",
                "Number of Monte Carlo paths",
                "int", 1000, 100, 10000, 100,
            ),
            ParameterSpec(
                "rebalance_freq", "Rebalance Frequency",
                "How often to rebalance the hedge",
                "select", "daily", options=["daily", "weekly", "monthly"],
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "GBM world, BSM hedge (baseline)": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "sigma": 0.20, "r": 0.05, "q": 0.0,
                "true_process": "gbm", "hedge_model": "bsm",
                "cev_beta": 0.5, "vg_theta": -0.15, "vg_nu": 0.25,
                "n_paths": 1000, "rebalance_freq": "daily",
            },
            "CEV world, BSM hedge (model mismatch)": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "sigma": 0.20, "r": 0.05, "q": 0.0,
                "true_process": "cev", "hedge_model": "bsm",
                "cev_beta": 0.5, "vg_theta": -0.15, "vg_nu": 0.25,
                "n_paths": 1000, "rebalance_freq": "daily",
            },
            "VG world, BSM hedge (jump risk)": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "sigma": 0.20, "r": 0.05, "q": 0.0,
                "true_process": "variance_gamma", "hedge_model": "bsm",
                "cev_beta": 0.5, "vg_theta": -0.15, "vg_nu": 0.25,
                "n_paths": 1000, "rebalance_freq": "daily",
            },
            "GBM — weekly rebalancing": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "sigma": 0.20, "r": 0.05, "q": 0.0,
                "true_process": "gbm", "hedge_model": "bsm",
                "cev_beta": 0.5, "vg_theta": -0.15, "vg_nu": 0.25,
                "n_paths": 1000, "rebalance_freq": "weekly",
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S0 = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["sigma"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        true_process = params.get("true_process", "gbm")
        cev_beta = float(params.get("cev_beta", 0.5))
        vg_theta = float(params.get("vg_theta", -0.15))
        vg_nu = float(params.get("vg_nu", 0.25))
        n_paths = int(params.get("n_paths", 1000))
        rebal = params.get("rebalance_freq", "daily")

        freq_map = {"daily": 252, "weekly": 52, "monthly": 12}
        n_steps = freq_map.get(rebal, 252)
        dt = T / n_steps

        steps: list[CalculationStep] = []
        rng = np.random.default_rng(42)

        # ── Step 1: option premium (what we collect for selling the call) ──
        premium = _bsm_price(S0, K, T, sigma, r, q, True)
        steps.append(CalculationStep(
            step_number=1,
            label="Option premium collected",
            formula=r"C_0 = \text{BSM}(S_0, K, T, \sigma, r, q)",
            substitution=f"C₀ = BSM({S0}, {K}, {T}, {sigma}, {r}, {q}) = {premium:.4f}",
            result=round(premium, 4),
            explanation="We sell a call at the BSM price and hedge with BSM deltas.",
        ))

        # ── Step 2: simulate paths ──
        if true_process == "gbm":
            paths = _simulate_gbm(S0, r, q, sigma, T, n_steps, n_paths, rng)
            process_desc = f"GBM(σ={sigma})"
        elif true_process == "cev":
            paths = _simulate_cev(S0, r, q, sigma, cev_beta, T, n_steps, n_paths, rng)
            process_desc = f"CEV(σ₀={sigma}, β={cev_beta})"
        else:
            paths = _simulate_vg(S0, r, q, sigma, vg_theta, vg_nu, T, n_steps, n_paths, rng)
            process_desc = f"VG(σ={sigma}, θ={vg_theta}, ν={vg_nu})"

        steps.append(CalculationStep(
            step_number=2,
            label="Simulate stock paths",
            formula=f"True process: {process_desc}",
            substitution=(
                f"{n_paths} paths, {n_steps} steps ({rebal} rebalancing)\n"
                f"Mean final price: {np.mean(paths[:, -1]):.2f}, "
                f"Std: {np.std(paths[:, -1]):.2f}"
            ),
            result=round(np.mean(paths[:, -1]), 2),
            explanation=f"Stock paths simulated under {true_process.upper()} dynamics.",
        ))

        # ── Step 3: run hedging simulation ──
        # For each path: track hedge portfolio value
        pnl = np.zeros(n_paths)

        for p in range(n_paths):
            cash = premium  # start with premium received
            shares = 0.0

            for i in range(n_steps):
                S_now = paths[p, i]
                t_remaining = T - i * dt

                if t_remaining <= 1e-12:
                    break

                # Compute BSM delta
                delta_new = _bsm_delta(S_now, K, t_remaining, sigma, r, q, True)

                # Rebalance: buy/sell shares
                d_shares = delta_new - shares
                cash -= d_shares * S_now
                shares = delta_new

                # Earn interest on cash
                cash *= math.exp(r * dt)

            # At expiry: liquidate
            S_final = paths[p, -1]
            portfolio_value = shares * S_final + cash
            payoff = max(S_final - K, 0)
            pnl[p] = portfolio_value - payoff

        steps.append(CalculationStep(
            step_number=3,
            label="Delta hedging simulation",
            formula=self.formula_plain,
            substitution=(
                f"Hedge model: BSM (σ={sigma})\n"
                f"Rebalancing: {rebal} ({n_steps} steps)\n"
                f"Paths: {n_paths}"
            ),
            result=round(float(np.mean(pnl)), 4),
            explanation=(
                "At each step: compute BSM delta, rebalance shares, "
                "earn interest on cash. At expiry: compare portfolio with payoff."
            ),
        ))

        # ── Step 4: P&L statistics ──
        mean_pnl = float(np.mean(pnl))
        std_pnl = float(np.std(pnl))
        pct_5 = float(np.percentile(pnl, 5))
        pct_25 = float(np.percentile(pnl, 25))
        pct_50 = float(np.percentile(pnl, 50))
        pct_75 = float(np.percentile(pnl, 75))
        pct_95 = float(np.percentile(pnl, 95))

        steps.append(CalculationStep(
            step_number=4,
            label="Hedge P&L distribution",
            formula=r"\text{Hedge Error} = V_T^{hedge} - \text{Payoff}",
            substitution=(
                f"Mean P&L: {mean_pnl:+.4f}\n"
                f"Std Dev:   {std_pnl:.4f}\n"
                f"5th pct:   {pct_5:+.4f}\n"
                f"Median:    {pct_50:+.4f}\n"
                f"95th pct:  {pct_95:+.4f}"
            ),
            result=round(mean_pnl, 4),
            explanation=(
                "Mean ≈ 0 if the hedge model matches the true process. "
                "Systematic bias indicates model misspecification. "
                "Std dev measures discrete hedging error."
            ),
        ))

        # ── Step 5: interpretation ──
        if abs(mean_pnl) < 0.5 * std_pnl:
            verdict = "GOOD — Mean P&L close to zero, hedge model is well-specified"
        elif mean_pnl < -0.5 * std_pnl:
            verdict = "BIASED — Systematic loss, hedge model underestimates risk"
        else:
            verdict = "BIASED — Systematic gain, hedge model overestimates risk"

        steps.append(CalculationStep(
            step_number=5,
            label="Interpretation",
            formula="",
            substitution=(
                f"Verdict: {verdict}\n"
                f"True process: {process_desc}\n"
                f"Hedge model: BSM(σ={sigma})\n"
                f"Mean/Std ratio: {abs(mean_pnl) / std_pnl:.2f}"
                if std_pnl > 0 else f"Verdict: {verdict}"
            ),
            result=round(abs(mean_pnl) / std_pnl if std_pnl > 0 else 0, 4),
            explanation=(
                "A mean/std ratio near 0 suggests no model mismatch. "
                "A ratio > 0.5 suggests significant misspecification."
            ),
        ))

        # Build histogram buckets for the frontend
        hist_counts, hist_edges = np.histogram(pnl, bins=30)
        histogram = [
            {"bin_start": round(float(hist_edges[i]), 2),
             "bin_end": round(float(hist_edges[i + 1]), 2),
             "count": int(hist_counts[i])}
            for i in range(len(hist_counts))
        ]

        return SimulatorResult(
            fair_value=round(mean_pnl, 4),
            method=f"Hedge Sim ({process_desc} / BSM hedge / {rebal})",
            greeks={},
            calculation_steps=steps,
            diagnostics={
                "premium_collected": round(premium, 4),
                "true_process": true_process,
                "hedge_model": "bsm",
                "rebalance_freq": rebal,
                "n_paths": n_paths,
                "n_steps": n_steps,
                "mean_pnl": round(mean_pnl, 4),
                "std_pnl": round(std_pnl, 4),
                "percentile_5": round(pct_5, 4),
                "percentile_25": round(pct_25, 4),
                "median_pnl": round(pct_50, 4),
                "percentile_75": round(pct_75, 4),
                "percentile_95": round(pct_95, 4),
                "mean_final_spot": round(float(np.mean(paths[:, -1])), 2),
                "pct_itm": round(float(np.mean(paths[:, -1] > K)) * 100, 1),
                "histogram": histogram,
                "verdict": verdict,
            },
        )

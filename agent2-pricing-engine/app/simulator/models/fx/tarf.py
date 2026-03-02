"""Target Accrual Redemption Forward (TARF) — Monte Carlo pricing.

A structured FX product popular in Asia-Pacific corporate hedging.
The client buys foreign currency at a discounted rate, but the total
gain is capped by a target accrual level.  Once cumulative gain
reaches the target, the structure knocks out.  Often leveraged on
the downside (2:1 or 3:1).
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
class TARFModel(BaseSimulatorModel):

    model_id = "tarf"
    model_name = "TARF — Target Accrual Redemption Forward"
    product_type = "Target Redemption Forward"
    asset_class = "fx"

    short_description = (
        "Monte Carlo pricing of leveraged FX forward with target accrual knockout"
    )
    long_description = (
        "A Target Accrual Redemption Forward (TARF) is a series of FX forward "
        "fixings where the client receives a favorable rate (below spot for a "
        "USD buyer) on each fixing date. However, cumulative gains are capped "
        "at a 'target' level — once the accumulated pips profit hits the target, "
        "the structure terminates. On the downside, the client is typically "
        "leveraged (e.g. 2:1), meaning they must buy at the strike for double "
        "the notional if spot is above strike. This asymmetry makes TARFs "
        "heavily dependent on the vol surface, skew, and path dynamics."
    )

    when_to_use = [
        "Structured FX forwards with embedded barriers on accumulated gain",
        "Common in Asia-Pacific corporate hedging (USD/CNH, USD/KRW, etc.)",
        "When client wants leveraged forward with cap on total gain",
        "Pricing path-dependent FX structures with periodic fixings",
    ]
    when_not_to_use = [
        "Simple FX hedging — use vanilla forwards or options",
        "When analytical pricing is needed — TARFs require Monte Carlo",
        "When you don't have reliable vol surface (highly sensitive to smile)",
        "For risk-averse clients — downside leverage creates large loss potential",
    ]
    assumptions = [
        "Spot follows GBM: dS = (r_d - r_f)S dt + σS dW under risk-neutral measure",
        "Constant volatility (flat smile) — in practice calibrate to surface",
        "Discrete fixings (e.g. monthly) — not continuously monitored",
        "No credit risk on the counterparty",
        "Interest rates are deterministic",
    ]
    limitations = [
        "GBM assumption ignores smile/skew — underestimates tail risk",
        "MC convergence requires many paths for accurate pricing",
        "Highly sensitive to vol surface — local vol or stoch vol recommended",
        "Does not model gap risk between fixings",
        "Leverage ratio amplifies model risk on the downside",
    ]

    formula_latex = (
        r"\text{TARF MTM} = \sum_{i=1}^{N} e^{-r_d t_i} \cdot "
        r"\mathbb{E}\left[\text{payoff}_i \cdot \mathbf{1}_{"
        r"\text{cumGain}_{i-1} < \text{Target}}\right]"
    )
    formula_plain = (
        "TARF value = sum over fixings of discounted expected payoff, "
        "conditional on cumulative gain not having reached the target. "
        "Payoff_i = N × max(K - S_i, 0) - L × N × max(S_i - K, 0) "
        "where L is the leverage ratio."
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Rate (S)", "Current FX spot rate (DOM/FOR)",
                "float", 7.2500, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "strike", "Strike (K)", "TARF strike rate (favorable to client)",
                "float", 7.1000, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "vol", "Volatility (σ)", "Annualized implied volatility",
                "float", 0.06, 0.001, 2.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_dom", "Domestic Rate (r_d)", "Domestic risk-free rate",
                "float", 0.03, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_for", "Foreign Rate (r_f)", "Foreign risk-free rate",
                "float", 0.053, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "maturity", "Total Tenor (T)", "Total life of the structure in years",
                "float", 1.0, 0.1, 5.0, 0.1, unit="years",
            ),
            ParameterSpec(
                "n_fixings", "Number of Fixings", "Total fixing dates (e.g. 12 for monthly)",
                "int", 12, 2, 60, 1,
            ),
            ParameterSpec(
                "notional", "Notional per Fixing", "Foreign currency notional per fixing",
                "float", 1_000_000.0, 1.0, None, 100_000.0, unit="FOR",
            ),
            ParameterSpec(
                "leverage", "Leverage Ratio", "Downside leverage (e.g. 2 means 2:1)",
                "float", 2.0, 1.0, 5.0, 0.5,
            ),
            ParameterSpec(
                "target", "Target (pips)", "Cumulative gain knockout level in pips",
                "float", 1500.0, 100.0, 50000.0, 100.0, unit="pips",
            ),
            ParameterSpec(
                "n_paths", "MC Paths", "Number of Monte Carlo simulation paths",
                "int", 50000, 1000, 500000, 1000,
            ),
            ParameterSpec(
                "seed", "Random Seed", "Random seed for reproducibility (0 = random)",
                "int", 42, 0, 999999, 1,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "USD/CNH 1Y Monthly (2:1)": {
                "spot": 7.2500, "strike": 7.1000, "vol": 0.06,
                "r_dom": 0.03, "r_for": 0.053, "maturity": 1.0,
                "n_fixings": 12, "notional": 1_000_000.0,
                "leverage": 2.0, "target": 1500.0,
                "n_paths": 50000, "seed": 42,
            },
            "USD/KRW 1Y Monthly (3:1)": {
                "spot": 1350.0, "strike": 1320.0, "vol": 0.08,
                "r_dom": 0.035, "r_for": 0.053, "maturity": 1.0,
                "n_fixings": 12, "notional": 1_000_000.0,
                "leverage": 3.0, "target": 300000.0,
                "n_paths": 50000, "seed": 42,
            },
            "EURUSD 6M Bi-weekly (2:1)": {
                "spot": 1.0800, "strike": 1.0900, "vol": 0.08,
                "r_dom": 0.053, "r_for": 0.035, "maturity": 0.5,
                "n_fixings": 12, "notional": 500_000.0,
                "leverage": 2.0, "target": 500.0,
                "n_paths": 50000, "seed": 42,
            },
            "USD/INR 1Y Quarterly (2:1)": {
                "spot": 83.50, "strike": 82.00, "vol": 0.05,
                "r_dom": 0.07, "r_for": 0.053, "maturity": 1.0,
                "n_fixings": 4, "notional": 2_000_000.0,
                "leverage": 2.0, "target": 6000.0,
                "n_paths": 50000, "seed": 42,
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S0 = float(params["spot"])
        K = float(params["strike"])
        sigma = float(params["vol"])
        rd = float(params["r_dom"])
        rf = float(params["r_for"])
        T = float(params["maturity"])
        n_fixings = int(params.get("n_fixings", 12))
        notional = float(params.get("notional", 1_000_000.0))
        leverage = float(params.get("leverage", 2.0))
        target_pips = float(params.get("target", 1500.0))
        n_paths = int(params.get("n_paths", 50000))
        seed_val = int(params.get("seed", 42))

        steps: list[CalculationStep] = []

        # Convert target from pips to price units
        target = target_pips / 10000.0

        # Fixing schedule
        dt = T / n_fixings
        fixing_times = [(i + 1) * dt for i in range(n_fixings)]

        steps.append(CalculationStep(
            step_number=1,
            label="Setup: fixing schedule",
            formula=r"t_i = i \cdot \Delta t,\;\; \Delta t = T / N",
            substitution=(
                f"T = {T}Y, N = {n_fixings} fixings, Δt = {dt:.4f}Y "
                f"({dt * 365:.1f} days).  "
                f"Strike = {K}, Leverage = {leverage}:1, "
                f"Target = {target_pips:.0f} pips ({target:.4f} price units)"
            ),
            result=round(dt, 4),
            explanation=(
                "Fixings are equally spaced. On each fixing: if S < K, client "
                "gains (K-S)×N. If S > K, client loses (S-K)×L×N. Structure "
                "terminates when cumulative gain reaches the target."
            ),
        ))

        # Step 2: GBM simulation
        rng = np.random.default_rng(seed_val if seed_val > 0 else None)
        drift = (rd - rf - 0.5 * sigma**2) * dt
        diffusion = sigma * math.sqrt(dt)

        # Generate all random increments: shape (n_paths, n_fixings)
        Z = rng.standard_normal((n_paths, n_fixings))
        log_returns = drift + diffusion * Z
        log_spot_paths = np.log(S0) + np.cumsum(log_returns, axis=1)
        spot_paths = np.exp(log_spot_paths)  # (n_paths, n_fixings)

        steps.append(CalculationStep(
            step_number=2,
            label="GBM path simulation",
            formula=(
                r"S_{t+\Delta t} = S_t \exp\left["
                r"(r_d - r_f - \tfrac{\sigma^2}{2})\Delta t"
                r" + \sigma \sqrt{\Delta t}\, Z\right]"
            ),
            substitution=(
                f"drift = ({rd} - {rf} - {sigma}²/2) × {dt:.4f} = {drift:.6f},  "
                f"diffusion = {sigma} × √{dt:.4f} = {diffusion:.6f},  "
                f"paths = {n_paths:,}"
            ),
            result=n_paths,
            explanation="Simulate spot paths under risk-neutral GBM for all fixing dates.",
        ))

        # Step 3: compute payoffs path by path
        total_pv = np.zeros(n_paths)
        knockout_counts = 0
        avg_knockout_fixing = 0.0
        gain_dist = []
        loss_dist = []

        for p in range(n_paths):
            cum_gain = 0.0
            path_pv = 0.0
            knocked_out = False
            for i in range(n_fixings):
                if knocked_out:
                    break
                S_i = spot_paths[p, i]
                t_i = fixing_times[i]
                df = math.exp(-rd * t_i)

                if S_i <= K:
                    # Client gains: buys at K, market is lower
                    gain = (K - S_i) * notional
                    gain_pips = (K - S_i)
                    # Check if this fixing would exceed target
                    if cum_gain + gain_pips >= target:
                        # Partial fill: only accrue up to target
                        remaining = target - cum_gain
                        gain = remaining * notional
                        path_pv += df * gain
                        knocked_out = True
                        knockout_counts += 1
                        avg_knockout_fixing += (i + 1)
                    else:
                        cum_gain += gain_pips
                        path_pv += df * gain
                    gain_dist.append(gain)
                else:
                    # Client loses: leveraged notional
                    loss = (S_i - K) * leverage * notional
                    path_pv -= df * loss
                    loss_dist.append(loss)

            total_pv[p] = path_pv

        steps.append(CalculationStep(
            step_number=3,
            label="Payoff computation per fixing",
            formula=(
                r"\text{If } S_i \leq K: \text{gain}_i = (K - S_i) \times N"
                r"\quad\text{If } S_i > K: \text{loss}_i = (S_i - K) \times L \times N"
            ),
            substitution=(
                f"Fixings simulated: {n_fixings} × {n_paths:,} paths.  "
                f"Knockout events: {knockout_counts:,} "
                f"({knockout_counts / n_paths * 100:.1f}% of paths)"
            ),
            result=round(knockout_counts / n_paths * 100, 1),
            explanation=(
                "Each fixing: if spot <= strike, client gains at 1:1 notional. "
                "If spot > strike, client loses at leverage:1. Cumulative gains "
                "are tracked; once they hit the target the TARF terminates."
            ),
        ))

        # Step 4: average PV
        mtm = float(np.mean(total_pv))
        std_err = float(np.std(total_pv) / math.sqrt(n_paths))

        steps.append(CalculationStep(
            step_number=4,
            label="Monte Carlo MTM",
            formula=r"\text{MTM} = \frac{1}{M}\sum_{j=1}^{M} PV_j",
            substitution=(
                f"MTM = mean of {n_paths:,} path PVs = {mtm:,.2f} DOM,  "
                f"Std error = {std_err:,.2f}"
            ),
            result=round(mtm, 2),
            explanation=(
                "The mark-to-market from the client's perspective. Positive = "
                "value to client, negative = value to dealer."
            ),
        ))

        # Step 5: statistics
        avg_ko = avg_knockout_fixing / max(knockout_counts, 1)
        pv_array = total_pv
        pct_positive = float(np.mean(pv_array > 0) * 100)
        var_95 = float(np.percentile(pv_array, 5))
        var_99 = float(np.percentile(pv_array, 1))

        steps.append(CalculationStep(
            step_number=5,
            label="Risk statistics",
            formula=r"\text{VaR}_{95} = \text{5th percentile of PV distribution}",
            substitution=(
                f"P(profit) = {pct_positive:.1f}%,  "
                f"Avg knockout fixing = {avg_ko:.1f},  "
                f"VaR(95%) = {var_95:,.0f},  VaR(99%) = {var_99:,.0f}"
            ),
            result=round(var_95, 0),
            explanation=(
                "Risk metrics for the client: probability of overall profit, "
                "average knockout fixing, and Value-at-Risk at 95th and 99th percentiles."
            ),
        ))

        # Sensitivity: bump spot ±1%
        bump = 0.01
        S_up = S0 * (1 + bump)
        S_dn = S0 * (1 - bump)
        # Re-run abbreviated MC for delta (use same random numbers)
        delta_approx = self._quick_reprice(
            S_up, K, sigma, rd, rf, T, n_fixings, notional,
            leverage, target, Z, fixing_times
        ) - self._quick_reprice(
            S_dn, K, sigma, rd, rf, T, n_fixings, notional,
            leverage, target, Z, fixing_times
        )
        delta_per_unit = delta_approx / (2 * bump * S0)

        # Vega: bump vol +1%
        vega_approx = self._quick_reprice(
            S0, K, sigma + 0.01, rd, rf, T, n_fixings, notional,
            leverage, target, Z, fixing_times
        ) - mtm

        steps.append(CalculationStep(
            step_number=6,
            label="Greeks (finite difference)",
            formula=r"\Delta \approx \frac{V(S+\epsilon) - V(S-\epsilon)}{2\epsilon}",
            substitution=(
                f"Δ (per 1% spot) = {delta_approx / 100:,.0f} DOM,  "
                f"Vega (per 1% vol) = {vega_approx:,.0f} DOM"
            ),
            result=round(delta_per_unit, 4),
            explanation=(
                "Greeks estimated via finite differences on the same random "
                "numbers (pathwise) for variance reduction."
            ),
        ))

        return SimulatorResult(
            fair_value=round(mtm, 2),
            method=f"Monte Carlo ({n_paths:,} paths, GBM)",
            greeks={
                "delta_pct": round(delta_approx / 100, 2),
                "delta_per_unit_spot": round(delta_per_unit, 4),
                "vega_1pct": round(vega_approx, 2),
            },
            calculation_steps=steps,
            diagnostics={
                "n_paths": n_paths,
                "n_fixings": n_fixings,
                "knockout_probability": round(knockout_counts / n_paths * 100, 2),
                "avg_knockout_fixing": round(avg_ko, 2),
                "pct_paths_profitable": round(pct_positive, 2),
                "std_error": round(std_err, 2),
                "var_95": round(var_95, 2),
                "var_99": round(var_99, 2),
                "mean_pv": round(mtm, 2),
                "median_pv": round(float(np.median(pv_array)), 2),
                "max_loss": round(float(np.min(pv_array)), 2),
                "max_gain": round(float(np.max(pv_array)), 2),
            },
        )

    def _quick_reprice(
        self, S0: float, K: float, sigma: float, rd: float, rf: float,
        T: float, n_fixings: int, notional: float, leverage: float,
        target: float, Z: np.ndarray, fixing_times: list[float],
    ) -> float:
        """Fast reprice using pre-generated random numbers (for Greeks)."""
        dt = T / n_fixings
        drift = (rd - rf - 0.5 * sigma**2) * dt
        diffusion = sigma * math.sqrt(dt)
        n_paths = Z.shape[0]

        log_returns = drift + diffusion * Z
        log_spot_paths = np.log(S0) + np.cumsum(log_returns, axis=1)
        spot_paths = np.exp(log_spot_paths)

        total_pv = np.zeros(n_paths)
        for p in range(n_paths):
            cum_gain = 0.0
            path_pv = 0.0
            for i in range(n_fixings):
                S_i = spot_paths[p, i]
                df = math.exp(-rd * fixing_times[i])
                if S_i <= K:
                    gain_pips = K - S_i
                    if cum_gain + gain_pips >= target:
                        remaining = target - cum_gain
                        path_pv += df * remaining * notional
                        break
                    else:
                        cum_gain += gain_pips
                        path_pv += df * gain_pips * notional
                else:
                    loss = (S_i - K) * leverage * notional
                    path_pv -= df * loss
            total_pv[p] = path_pv

        return float(np.mean(total_pv))

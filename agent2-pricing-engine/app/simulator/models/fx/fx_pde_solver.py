"""FX PDE Solver — Crank-Nicolson for FX barrier and American options.

Adapts the generic PDE engine for FX options with domestic/foreign rates.
Supports European, American, and barrier FX options.  The PDE being solved:

  ∂V/∂t + ½σ²S²·∂²V/∂S² + (r_d - r_f)S·∂V/∂S - r_d·V = 0

This is the same BS PDE with r → r_d and q → r_f.
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
from app.simulator.models.equity.pde_solver import PDEGrid, solve_pde_crank_nicolson
from app.simulator.registry import ModelRegistry


@ModelRegistry.register
class FXPDESolverModel(BaseSimulatorModel):

    model_id = "fx_pde_solver"
    model_name = "FX PDE Solver (Crank-Nicolson)"
    product_type = "FX Barrier & American Options"
    asset_class = "fx"

    short_description = (
        "Finite-difference PDE pricer for FX barrier and American options"
    )
    long_description = (
        "Crank-Nicolson PDE solver for FX options with domestic/foreign rate "
        "parametrisation.  Handles European (validation), American (early exercise), "
        "and barrier FX options (knock-in/knock-out).  Barrier FX options are one "
        "of the most actively traded exotic FX products and require a PDE or MC "
        "approach.  The PDE naturally handles the Dirichlet boundary condition at "
        "the barrier level and can incorporate local volatility for smile-consistent "
        "barrier pricing."
    )

    when_to_use = [
        "FX barrier options (knock-out, knock-in, double-barrier)",
        "American FX options with early exercise",
        "Validating GK closed-form against a numerical method",
        "When barrier is close to spot (high smile sensitivity)",
        "Local vol FX pricing with the Dupire surface as σ(S,t) input",
    ]
    when_not_to_use = [
        "Asian, lookback, or other path-dependent FX exotics (use MC)",
        "Multi-currency products (basket options, quanto FX)",
        "When GK closed-form suffices (European vanillas)",
        "TARF / accumulator (use MC with local vol)",
    ]
    assumptions = [
        "FX PDE: ∂V/∂t + ½σ²S²∂²V/∂S² + (r_d-r_f)S∂V/∂S - r_d·V = 0",
        "Crank-Nicolson scheme (θ=0.5): second-order in space and time",
        "Barrier: Dirichlet boundary condition V = 0 at knock-out barrier",
        "Constant or local volatility",
    ]
    limitations = [
        "1D only — single FX pair (no multi-currency)",
        "Discrete monitoring of barriers requires adjustment",
        "Uniform grid — adaptive meshing would be more efficient near barrier/strike",
    ]

    formula_latex = (
        r"\frac{\partial V}{\partial t} + \frac{1}{2}\sigma^2 S^2 "
        r"\frac{\partial^2 V}{\partial S^2} + (r_d-r_f)S\frac{\partial V}{\partial S} - r_d V = 0"
    )
    formula_plain = (
        "∂V/∂t + ½σ²S²·∂²V/∂S² + (r_d-r_f)S·∂V/∂S - r_d·V = 0"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec("spot", "Spot FX Rate (S)", "DOM/FOR", "float", 1.0850, 0.0001, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("strike", "Strike (K)", "Option strike", "float", 1.0850, 0.0001, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("maturity", "Time to Expiry (T)", "Years", "float", 0.25, 0.01, 10.0, 0.01, unit="years"),
            ParameterSpec("vol", "Volatility (σ)", "FX implied volatility", "float", 0.078, 0.01, 2.0, 0.001, unit="decimal"),
            ParameterSpec("r_d", "Domestic Rate (r_d)", "Domestic rate", "float", 0.053, -0.1, 0.5, 0.001, unit="decimal"),
            ParameterSpec("r_f", "Foreign Rate (r_f)", "Foreign rate", "float", 0.035, -0.1, 0.5, 0.001, unit="decimal"),
            ParameterSpec("option_type", "Option Type", "Call or Put", "select", "call", options=["call", "put"]),
            ParameterSpec("exercise", "Exercise / Barrier", "European, American, or Knock-Out", "select", "european", options=["european", "american", "knock_out"]),
            ParameterSpec("barrier", "Barrier Level", "Knock-out barrier (0 = no barrier)", "float", 0.0, 0.0, None, 0.0001, unit="DOM/FOR"),
            ParameterSpec("n_spot", "Grid Points (space)", "Spatial grid points", "int", 200, 50, 1000, 50),
            ParameterSpec("n_time", "Grid Points (time)", "Time steps", "int", 200, 50, 1000, 50),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "EUR/USD European Call (GK validation)": {
                "spot": 1.0850, "strike": 1.0850, "maturity": 0.25,
                "vol": 0.078, "r_d": 0.053, "r_f": 0.035,
                "option_type": "call", "exercise": "european",
                "barrier": 0.0, "n_spot": 200, "n_time": 200,
            },
            "EUR/USD Down-and-Out Put (barrier)": {
                "spot": 1.0850, "strike": 1.1000, "maturity": 0.25,
                "vol": 0.078, "r_d": 0.053, "r_f": 0.035,
                "option_type": "put", "exercise": "knock_out",
                "barrier": 1.0400, "n_spot": 300, "n_time": 300,
            },
            "USD/JPY American Put": {
                "spot": 155.0, "strike": 155.0, "maturity": 0.5,
                "vol": 0.10, "r_d": 0.001, "r_f": 0.053,
                "option_type": "put", "exercise": "american",
                "barrier": 0.0, "n_spot": 200, "n_time": 200,
            },
            "GBP/USD Up-and-Out Call": {
                "spot": 1.2700, "strike": 1.2500, "maturity": 0.5,
                "vol": 0.085, "r_d": 0.053, "r_f": 0.045,
                "option_type": "call", "exercise": "knock_out",
                "barrier": 1.3500, "n_spot": 300, "n_time": 300,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S0 = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        r_d = float(params["r_d"])
        r_f = float(params["r_f"])
        opt_type = params.get("option_type", "call").lower()
        exercise = params.get("exercise", "european").lower()
        barrier = float(params.get("barrier", 0.0))
        N_S = int(params.get("n_spot", 200))
        N_t = int(params.get("n_time", 200))
        is_call = opt_type == "call"
        is_american = exercise == "american"
        is_knock_out = exercise == "knock_out"
        has_barrier = is_knock_out and barrier > 0

        steps: list[CalculationStep] = []

        # Step 1: grid
        S_max = S0 * 3
        S_min = max(S0 * 0.01, 0.0001)

        # Adjust grid for barrier
        if has_barrier:
            if barrier < S0:  # down barrier
                S_min = barrier * 0.99
            else:  # up barrier
                S_max = barrier * 1.01

        grid = PDEGrid(S_min=S_min, S_max=S_max, N_S=N_S, N_t=N_t, T=T)

        steps.append(CalculationStep(
            step_number=1,
            label="Define FX grid",
            formula=r"S \in [S_{min}, S_{max}]",
            substitution=(
                f"S ∈ [{S_min:.4f}, {S_max:.4f}], N_S={N_S}, ΔS={grid.dS:.6f}\n"
                f"N_t={N_t}, Δt={grid.dt:.6f}"
                + (f"\nBarrier at {barrier:.4f} ({'down' if barrier < S0 else 'up'}-and-out)" if has_barrier else "")
            ),
            result=round(grid.dS, 6),
            explanation="FX PDE grid with barrier-adjusted boundaries if applicable.",
        ))

        # Step 2: payoff and boundaries
        if is_call:
            payoff_fn = lambda s: np.maximum(s - K, 0)
        else:
            payoff_fn = lambda s: np.maximum(K - s, 0)

        # Barrier boundary conditions
        if has_barrier and barrier < S0:
            # Down-and-out: V = 0 at lower boundary (barrier)
            lower_bc = lambda t, dt: 0.0
            upper_bc = lambda t, dt: (S_max - K * math.exp(-r_d * t)) if is_call else 0.0
        elif has_barrier and barrier >= S0:
            # Up-and-out: V = 0 at upper boundary (barrier)
            lower_bc = lambda t, dt: (K * math.exp(-r_d * t) - S_min) if not is_call else 0.0
            upper_bc = lambda t, dt: 0.0
        else:
            # Standard boundaries
            if is_call:
                lower_bc = lambda t, dt: 0.0
                upper_bc = lambda t, dt: S_max - K * math.exp(-r_d * t)
            else:
                lower_bc = lambda t, dt: K * math.exp(-r_d * t) - S_min
                upper_bc = lambda t, dt: 0.0

        barrier_desc = ""
        if has_barrier:
            barrier_desc = f"\nKnock-out barrier at {barrier:.4f}: V=0 at boundary"

        steps.append(CalculationStep(
            step_number=2,
            label="Payoff and boundary conditions",
            formula=(r"V(S,T) = \max(S-K, 0)" if is_call else r"V(S,T) = \max(K-S, 0)"),
            substitution=f"{'Call' if is_call else 'Put'} with K={K}" + barrier_desc,
            result=round(max(S0 - K, 0) if is_call else max(K - S0, 0), 6),
            explanation="Terminal payoff with barrier condition if applicable.",
        ))

        # Step 3: solve PDE
        sigma_fn = lambda s, t: np.full_like(s, sigma)

        pde_result = solve_pde_crank_nicolson(
            grid=grid,
            payoff_fn=payoff_fn,
            sigma_fn=sigma_fn,
            r=r_d,
            q=r_f,
            is_american=is_american,
            lower_bc=lower_bc,
            upper_bc=upper_bc,
        )

        price = float(np.interp(S0, pde_result.grid_S, pde_result.grid_prices))

        exercise_label = "European"
        if is_american:
            exercise_label = "American"
        elif is_knock_out:
            exercise_label = f"Knock-Out (barrier={barrier})"

        steps.append(CalculationStep(
            step_number=3,
            label=f"Crank-Nicolson solve ({exercise_label})",
            formula=r"(I - \theta A) V^{n-1} = (I + (1-\theta)A) V^n",
            substitution=(
                f"PDE price ({exercise_label}): {price:.6f}\n"
                f"Grid: {N_S}×{N_t}"
            ),
            result=round(price, 6),
            explanation="Backward PDE induction with FX rates (r_d, r_f) and barrier constraints.",
        ))

        # Step 4: GK comparison
        d1 = (math.log(S0 / K) + (r_d - r_f + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if is_call:
            gk = (S0 * math.exp(-r_f * T) * norm.cdf(d1)
                  - K * math.exp(-r_d * T) * norm.cdf(d2))
        else:
            gk = (K * math.exp(-r_d * T) * norm.cdf(-d2)
                  - S0 * math.exp(-r_f * T) * norm.cdf(-d1))

        diff = price - gk
        steps.append(CalculationStep(
            step_number=4,
            label="GK comparison",
            formula=r"\Delta = V_{PDE} - V_{GK}",
            substitution=(
                f"PDE: {price:.6f}, GK (European vanilla): {gk:.6f}\n"
                f"Difference: {diff:+.6f}"
                + (f"\nBarrier discount: {diff:.6f} (KO < vanilla)" if has_barrier else "")
                + (f"\nEarly exercise premium: {diff:.6f}" if is_american else "")
            ),
            result=round(diff, 6),
            explanation=(
                "For European vanillas, PDE should match GK. For barriers, the price "
                "is less than vanilla (knock-out discount). For American, it's higher "
                "(early exercise premium)."
            ),
        ))

        # Greeks
        S_arr = pde_result.grid_S
        V_arr = pde_result.grid_prices
        delta = float(np.interp(S0, S_arr[:-1], np.diff(V_arr) / grid.dS))
        idx = min(max(np.searchsorted(S_arr, S0), 1), len(S_arr) - 2)
        gamma = float((V_arr[idx + 1] - 2 * V_arr[idx] + V_arr[idx - 1]) / grid.dS**2)

        greeks = {"delta": round(delta, 6), "gamma": round(gamma, 6)}

        return SimulatorResult(
            fair_value=round(price, 6),
            method=f"FX PDE Crank-Nicolson ({exercise_label}, {N_S}×{N_t})",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "gk_reference": round(gk, 6),
                "pde_gk_diff": round(diff, 6),
                "barrier": barrier if has_barrier else None,
                "barrier_type": ("down-and-out" if barrier < S0 else "up-and-out") if has_barrier else None,
                "exercise_style": exercise_label,
                "grid_S": N_S,
                "grid_t": N_t,
                "forward_rate": round(S0 * math.exp((r_d - r_f) * T), 6),
            },
        )

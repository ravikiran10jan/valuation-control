"""Generic PDE Solver — Crank-Nicolson finite-difference engine.

A reusable 1D finite-difference PDE solver that any model can plug into.
Supports:
  - European options (terminal condition only)
  - American options (early exercise via projected SOR / penalty)
  - Barrier options (Dirichlet boundary conditions)
  - Arbitrary local volatility σ(S, t)

The Crank-Nicolson scheme is second-order in both space and time,
unconditionally stable, and the industry standard for 1D option pricing PDEs.

The PDE being solved (in the S-direction):

  ∂V/∂t + ½σ²(S,t)S²·∂²V/∂S² + (r-q)S·∂V/∂S - rV = 0

with terminal condition V(S, T) = payoff(S).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


# ── PDE Engine (reusable) ────────────────────────────────────

@dataclass
class PDEGrid:
    """Defines the finite-difference grid."""
    S_min: float
    S_max: float
    N_S: int          # number of spatial points
    N_t: int          # number of time steps
    T: float          # maturity

    @property
    def dS(self) -> float:
        return (self.S_max - self.S_min) / (self.N_S - 1)

    @property
    def dt(self) -> float:
        return self.T / self.N_t

    @property
    def S_grid(self) -> np.ndarray:
        return np.linspace(self.S_min, self.S_max, self.N_S)

    @property
    def t_grid(self) -> np.ndarray:
        return np.linspace(0, self.T, self.N_t + 1)


@dataclass
class PDEResult:
    """Full result from the PDE solver."""
    price: float
    grid_S: np.ndarray
    grid_prices: np.ndarray    # V(S) at t=0
    early_exercise_boundary: list[tuple[float, float]] = field(default_factory=list)
    greeks: dict[str, float] = field(default_factory=dict)


def solve_pde_crank_nicolson(
    grid: PDEGrid,
    payoff_fn: Callable[[np.ndarray], np.ndarray],
    sigma_fn: Callable[[np.ndarray, float], np.ndarray],
    r: float,
    q: float = 0.0,
    is_american: bool = False,
    lower_bc: Callable[[float, float], float] | None = None,
    upper_bc: Callable[[float, float], float] | None = None,
    theta: float = 0.5,
) -> PDEResult:
    """Solve the Black-Scholes PDE via Crank-Nicolson.

    Parameters
    ----------
    grid : PDEGrid
    payoff_fn : callable  S_array -> payoff_array
    sigma_fn : callable   (S_array, t) -> sigma_array  (local vol surface)
    r : float             risk-free rate
    q : float             dividend yield
    is_american : bool    apply early exercise constraint
    lower_bc : callable   (t, dt) -> V(S_min, t)  [Dirichlet at lower boundary]
    upper_bc : callable   (t, dt) -> V(S_max, t)  [Dirichlet at upper boundary]
    theta : float         0.5 = Crank-Nicolson, 1.0 = implicit Euler
    """
    S = grid.S_grid
    dt = grid.dt
    N = grid.N_S
    dS = grid.dS

    # Terminal condition
    V = payoff_fn(S).copy()

    # For American: track early exercise boundary
    ex_boundary: list[tuple[float, float]] = []

    # Time-step backwards from T to 0
    for step in range(grid.N_t):
        t_now = grid.T - step * dt         # current time in backward stepping
        t_prev = t_now - dt                 # time after this step (closer to 0)

        # Local vol at current and next time
        sig_now = sigma_fn(S, t_now)
        sig_prev = sigma_fn(S, max(t_prev, 0))
        sig_avg = 0.5 * (sig_now + sig_prev)

        # Build tridiagonal coefficients for interior points [1..N-2]
        # Using the θ-scheme (Crank-Nicolson for θ=0.5)
        alpha = np.zeros(N)
        beta_coeff = np.zeros(N)
        gamma = np.zeros(N)

        for i in range(1, N - 1):
            s = S[i]
            vol = sig_avg[i]
            v2s2 = vol**2 * s**2
            drift = (r - q) * s

            # Central differences
            a_i = 0.5 * dt * (v2s2 / dS**2 - drift / dS)
            b_i = -dt * (v2s2 / dS**2 + r)
            c_i = 0.5 * dt * (v2s2 / dS**2 + drift / dS)

            alpha[i] = a_i
            beta_coeff[i] = b_i
            gamma[i] = c_i

        # Explicit part: (I + (1-θ)·A) · V^{n}
        # Implicit part: (I - θ·A) · V^{n-1} = RHS
        rhs = np.zeros(N)
        for i in range(1, N - 1):
            rhs[i] = (
                (1 - theta) * alpha[i] * V[i - 1]
                + (1 + (1 - theta) * beta_coeff[i]) * V[i]
                + (1 - theta) * gamma[i] * V[i + 1]
            )

        # Boundary conditions
        if lower_bc is not None:
            rhs[0] = lower_bc(t_prev, dt)
            V_new_0 = rhs[0]
        else:
            V_new_0 = V[0] * math.exp(-r * dt)

        if upper_bc is not None:
            rhs[N - 1] = upper_bc(t_prev, dt)
            V_new_last = rhs[N - 1]
        else:
            V_new_last = V[N - 1]

        # Solve tridiagonal system: (I - θ·A)·V_new = rhs
        # Using Thomas algorithm
        a_tri = np.zeros(N)
        b_tri = np.zeros(N)
        c_tri = np.zeros(N)
        d_tri = rhs.copy()

        b_tri[0] = 1.0
        d_tri[0] = V_new_0
        b_tri[N - 1] = 1.0
        d_tri[N - 1] = V_new_last

        for i in range(1, N - 1):
            a_tri[i] = -theta * alpha[i]
            b_tri[i] = 1 - theta * beta_coeff[i]
            c_tri[i] = -theta * gamma[i]

        # Forward sweep
        for i in range(1, N):
            if abs(b_tri[i - 1]) < 1e-30:
                continue
            w = a_tri[i] / b_tri[i - 1]
            b_tri[i] -= w * c_tri[i - 1]
            d_tri[i] -= w * d_tri[i - 1]

        # Back substitution
        V_new = np.zeros(N)
        V_new[N - 1] = d_tri[N - 1] / b_tri[N - 1] if abs(b_tri[N - 1]) > 1e-30 else 0
        for i in range(N - 2, -1, -1):
            V_new[i] = (d_tri[i] - c_tri[i] * V_new[i + 1]) / b_tri[i] if abs(b_tri[i]) > 1e-30 else 0

        # American early exercise
        if is_american:
            intrinsic = payoff_fn(S)
            exercise_mask = V_new < intrinsic
            V_new = np.maximum(V_new, intrinsic)

            # Track exercise boundary
            if np.any(exercise_mask[1:-1]):
                # Find the spot where exercise starts
                ex_idx = np.where(exercise_mask[1:-1])[0]
                if len(ex_idx) > 0:
                    ex_boundary.append((t_prev, float(S[ex_idx[0] + 1])))

        V = V_new

    # Extract price at current spot (interpolate)
    # Compute Greeks from the grid
    greeks = {}
    # Delta: central difference at midpoint
    mid = N // 2
    if mid > 0 and mid < N - 1:
        greeks["delta"] = float((V[mid + 1] - V[mid - 1]) / (2 * dS))
        greeks["gamma"] = float((V[mid + 1] - 2 * V[mid] + V[mid - 1]) / dS**2)

    return PDEResult(
        price=float(np.interp(grid.S_min + (grid.S_max - grid.S_min) / 2, S, V)),
        grid_S=S,
        grid_prices=V,
        early_exercise_boundary=ex_boundary,
        greeks=greeks,
    )


# ── PDE Simulator Model (European & American Vanilla) ───────

@ModelRegistry.register
class PDESolverModel(BaseSimulatorModel):

    model_id = "pde_solver"
    model_name = "PDE Solver (Crank-Nicolson)"
    product_type = "European & American Vanilla Options"
    asset_class = "equity"

    short_description = (
        "Finite-difference PDE pricer for vanilla and American options"
    )
    long_description = (
        "A generic Crank-Nicolson finite-difference PDE solver for the "
        "Black-Scholes PDE. This is the industry-standard numerical method "
        "for 1D option pricing problems. It handles European options (where "
        "it converges to the BSM closed-form), American options (with early "
        "exercise constraint), and serves as the backbone for local volatility "
        "and barrier option pricing. The Crank-Nicolson scheme is second-order "
        "accurate in both space and time, and unconditionally stable."
    )

    when_to_use = [
        "American options where no closed-form exists",
        "Barrier options with continuous monitoring",
        "Local volatility pricing (plug in σ(S,t))",
        "Validating closed-form solutions (convergence checks)",
        "When you need a full price surface V(S) across all spot levels",
        "1D problems with up to 2 boundaries",
    ]
    when_not_to_use = [
        "High-dimensional problems (>2 factors) — use Monte Carlo instead",
        "Path-dependent payoffs (Asian, lookback) unless reformulated with an extra state variable",
        "When a closed-form exists and speed matters (BSM is 1000x faster)",
        "Complex boundary conditions (use finite elements instead)",
    ]
    assumptions = [
        "Risk-neutral pricing under the Black-Scholes PDE",
        "Finite-difference approximation on a uniform grid",
        "Crank-Nicolson θ-scheme (θ=0.5): second-order in space and time",
        "Constant or time-dependent but deterministic risk-free rate",
        "Boundary conditions: Dirichlet (fixed) or linearity at far boundaries",
    ]
    limitations = [
        "Uniform grid may waste points — non-uniform grids would be more efficient near the strike",
        "Convergence requires sufficient grid resolution (N_S ≥ 100, N_t ≥ 100)",
        "Cannot handle high-dimensional problems efficiently",
        "American exercise boundary may have small discretisation error",
    ]

    formula_latex = (
        r"\frac{\partial V}{\partial t} + \frac{1}{2}\sigma^2 S^2 "
        r"\frac{\partial^2 V}{\partial S^2} + (r-q)S\frac{\partial V}{\partial S} - rV = 0"
    )
    formula_plain = (
        "∂V/∂t + ½σ²S²·∂²V/∂S² + (r-q)S·∂V/∂S - rV = 0, "
        "solved backwards from V(S,T) = payoff(S)"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Price (S)", "Current price", "float",
                100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "strike", "Strike Price (K)", "Option strike", "float",
                100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "maturity", "Time to Expiry (T)", "Years", "float",
                1.0, 0.01, 10.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "vol", "Volatility (σ)", "Constant Black-Scholes vol", "float",
                0.20, 0.01, 3.0, 0.01, unit="decimal",
            ),
            ParameterSpec(
                "r", "Risk-Free Rate (r)", "Continuous rate", "float",
                0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "q", "Dividend Yield (q)", "Continuous yield", "float",
                0.0, 0.0, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "option_type", "Option Type", "Call or Put",
                "select", "call", options=["call", "put"],
            ),
            ParameterSpec(
                "exercise", "Exercise Style", "European or American",
                "select", "european", options=["european", "american"],
            ),
            ParameterSpec(
                "n_spot", "Grid Points (space)", "Number of spatial grid points",
                "int", 200, 50, 1000, 50,
            ),
            ParameterSpec(
                "n_time", "Grid Points (time)", "Number of time steps",
                "int", 200, 50, 1000, 50,
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "European Call (BSM validation)": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "vol": 0.20, "r": 0.05, "q": 0.0,
                "option_type": "call", "exercise": "european",
                "n_spot": 200, "n_time": 200,
            },
            "American Put (early exercise)": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "vol": 0.20, "r": 0.05, "q": 0.0,
                "option_type": "put", "exercise": "american",
                "n_spot": 200, "n_time": 200,
            },
            "Deep ITM American Put": {
                "spot": 80, "strike": 100, "maturity": 1.0,
                "vol": 0.30, "r": 0.08, "q": 0.0,
                "option_type": "put", "exercise": "american",
                "n_spot": 300, "n_time": 300,
            },
            "American Call with dividend": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "vol": 0.25, "r": 0.05, "q": 0.03,
                "option_type": "call", "exercise": "american",
                "n_spot": 200, "n_time": 200,
            },
            "High-resolution European": {
                "spot": 100, "strike": 100, "maturity": 1.0,
                "vol": 0.20, "r": 0.05, "q": 0.0,
                "option_type": "call", "exercise": "european",
                "n_spot": 500, "n_time": 500,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S0 = float(params["spot"])
        K = float(params["strike"])
        T = float(params["maturity"])
        sigma = float(params["vol"])
        r = float(params["r"])
        q = float(params.get("q", 0.0))
        opt_type = params.get("option_type", "call").lower()
        exercise = params.get("exercise", "european").lower()
        N_S = int(params.get("n_spot", 200))
        N_t = int(params.get("n_time", 200))
        is_call = opt_type == "call"
        is_american = exercise == "american"

        steps: list[CalculationStep] = []

        # Step 1: define grid
        S_max = S0 * 4
        S_min = max(S0 * 0.01, 0.01)
        grid = PDEGrid(S_min=S_min, S_max=S_max, N_S=N_S, N_t=N_t, T=T)

        steps.append(CalculationStep(
            step_number=1,
            label="Define spatial grid",
            formula=r"S \in [S_{min}, S_{max}], \quad \Delta S = (S_{max} - S_{min}) / (N_S - 1)",
            substitution=(
                f"S ∈ [{S_min:.2f}, {S_max:.2f}], N_S={N_S}, ΔS={grid.dS:.4f}\n"
                f"N_t={N_t}, Δt={grid.dt:.6f}"
            ),
            result=round(grid.dS, 4),
            explanation="The spatial grid spans from near-zero to 4× spot. More points → higher accuracy.",
        ))

        # Step 2: terminal condition
        if is_call:
            payoff_fn = lambda s: np.maximum(s - K, 0)
        else:
            payoff_fn = lambda s: np.maximum(K - s, 0)

        steps.append(CalculationStep(
            step_number=2,
            label="Terminal condition (payoff at expiry)",
            formula=r"V(S, T) = \max(S - K, 0)" if is_call else r"V(S, T) = \max(K - S, 0)",
            substitution=f"{'Call' if is_call else 'Put'} payoff with K={K}",
            result=round(max(S0 - K, 0) if is_call else max(K - S0, 0), 4),
            explanation="At expiry, the option is worth its intrinsic value.",
        ))

        # Step 3: boundary conditions
        if is_call:
            lower_bc = lambda t, dt: 0.0
            upper_bc = lambda t, dt: S_max - K * math.exp(-r * t)
        else:
            lower_bc = lambda t, dt: K * math.exp(-r * t) - S_min
            upper_bc = lambda t, dt: 0.0

        steps.append(CalculationStep(
            step_number=3,
            label="Boundary conditions",
            formula=(
                r"V(S_{min}, t) \approx 0, \; V(S_{max}, t) \approx S_{max} - Ke^{-rt}"
                if is_call else
                r"V(S_{min}, t) \approx Ke^{-rt} - S_{min}, \; V(S_{max}, t) \approx 0"
            ),
            substitution=f"{'Call' if is_call else 'Put'} boundaries at S_min={S_min:.2f}, S_max={S_max:.2f}",
            result=0.0,
            explanation="Far boundary conditions: deep ITM approximation at one end, zero at the other.",
        ))

        # Step 4: solve
        sigma_fn = lambda s, t: np.full_like(s, sigma)

        pde_result = solve_pde_crank_nicolson(
            grid=grid,
            payoff_fn=payoff_fn,
            sigma_fn=sigma_fn,
            r=r,
            q=q,
            is_american=is_american,
            lower_bc=lower_bc,
            upper_bc=upper_bc,
        )

        # Interpolate at S0
        price = float(np.interp(S0, pde_result.grid_S, pde_result.grid_prices))

        steps.append(CalculationStep(
            step_number=4,
            label="Crank-Nicolson backward induction",
            formula=(
                r"\text{At each step: solve } (I - \theta A) V^{n-1} = (I + (1-\theta)A) V^n"
            ),
            substitution=(
                f"Scheme: Crank-Nicolson (θ=0.5)\n"
                f"Time steps: {N_t}, stepping Δt={grid.dt:.6f}\n"
                f"{'American exercise constraint applied at each step' if is_american else 'European (no early exercise)'}"
            ),
            result=round(price, 4),
            explanation=(
                "Crank-Nicolson averages explicit and implicit schemes for second-order "
                "accuracy. The tridiagonal system is solved via Thomas algorithm at each step."
            ),
        ))

        # Step 5: extract price and Greeks
        delta = float(np.interp(S0, pde_result.grid_S[:-1],
                                np.diff(pde_result.grid_prices) / grid.dS))
        # Gamma from second difference
        S_arr = pde_result.grid_S
        V_arr = pde_result.grid_prices
        idx = np.searchsorted(S_arr, S0)
        idx = min(max(idx, 1), len(S_arr) - 2)
        gamma = float((V_arr[idx + 1] - 2 * V_arr[idx] + V_arr[idx - 1]) / grid.dS**2)

        steps.append(CalculationStep(
            step_number=5,
            label="Extract price and Greeks at S₀",
            formula=r"\Delta = \frac{V(S+\Delta S) - V(S-\Delta S)}{2\Delta S}, \quad \Gamma = \frac{V(S+) - 2V(S) + V(S-)}{(\Delta S)^2}",
            substitution=(
                f"Price at S={S0}: {price:.4f}\n"
                f"Delta (finite diff): {delta:.6f}\n"
                f"Gamma (finite diff): {gamma:.6f}"
            ),
            result=round(price, 4),
            explanation="Greeks extracted from the numerical solution grid via finite differences.",
        ))

        # Step 6: BSM comparison
        from scipy.stats import norm as norm_dist
        d1 = (math.log(S0 / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if is_call:
            bsm = (S0 * math.exp(-q * T) * norm_dist.cdf(d1)
                    - K * math.exp(-r * T) * norm_dist.cdf(d2))
        else:
            bsm = (K * math.exp(-r * T) * norm_dist.cdf(-d2)
                    - S0 * math.exp(-q * T) * norm_dist.cdf(-d1))

        diff = price - bsm
        early_ex_premium = diff if is_american else 0

        steps.append(CalculationStep(
            step_number=6,
            label="BSM comparison" + (" & early exercise premium" if is_american else ""),
            formula=r"\text{Early Exercise Premium} = V_{American} - V_{European}",
            substitution=(
                f"PDE price: {price:.4f}\n"
                f"BSM (European, analytical): {bsm:.4f}\n"
                f"Difference: {diff:+.4f}"
                + (f"\nEarly exercise premium ≈ {early_ex_premium:.4f}" if is_american else
                   f"\nPDE-BSM error: {diff:.6f} (should be ~0 for European)")
            ),
            result=round(diff, 6),
            explanation=(
                "For European options, the PDE should converge to BSM — the error shows grid accuracy. "
                "For American options, the positive difference is the early exercise premium."
                if not is_american else
                "The American price exceeds the European BSM price by the early exercise premium."
            ),
        ))

        # Theta via re-solve with slightly less time
        greeks = {
            "delta": round(delta, 6),
            "gamma": round(gamma, 6),
        }

        return SimulatorResult(
            fair_value=round(price, 4),
            method=f"PDE Crank-Nicolson ({'American' if is_american else 'European'}, {N_S}×{N_t} grid)",
            greeks=greeks,
            calculation_steps=steps,
            diagnostics={
                "bsm_reference": round(bsm, 4),
                "pde_bsm_error": round(diff, 6),
                "early_exercise_premium": round(early_ex_premium, 4) if is_american else 0,
                "grid_points_S": N_S,
                "grid_points_t": N_t,
                "S_min": round(S_min, 2),
                "S_max": round(S_max, 2),
                "dS": round(grid.dS, 4),
                "dt": round(grid.dt, 6),
            },
        )

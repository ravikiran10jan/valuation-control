"""PDE Finite-Difference solver for FX Barrier options.

Implements the Crank-Nicolson scheme for the Black-Scholes PDE
with absorbing boundary conditions at the barrier levels.

Also provides a Local-Vol (Dupire) surface pricer that uses a
calibrated local volatility grid instead of constant vol.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.linalg import solve_banded


class FXBarrierPDE:
    """Crank-Nicolson finite-difference pricer for double-barrier options."""

    def __init__(
        self,
        spot: float,
        lower_barrier: float,
        upper_barrier: float,
        maturity: float,
        notional: float,
        vol: float,
        r_dom: float,
        r_for: float,
        barrier_type: str = "DNT",
        n_spot: int = 200,
        n_time: int = 500,
    ):
        self.spot = spot
        self.lower_barrier = lower_barrier
        self.upper_barrier = upper_barrier
        self.maturity = maturity
        self.notional = notional
        self.vol = vol
        self.r_dom = r_dom
        self.r_for = r_for
        self.barrier_type = barrier_type.upper()
        self.n_spot = n_spot
        self.n_time = n_time

    def price(self) -> float:
        """Solve the BS PDE using Crank-Nicolson on a uniform log-spot grid."""
        L = self.lower_barrier
        U = self.upper_barrier
        S0 = self.spot
        T = self.maturity
        sigma = self.vol
        r = self.r_dom
        q = self.r_for
        N_s = self.n_spot
        N_t = self.n_time

        # Grid in log-spot space: x = ln(S)
        x_min = math.log(L)
        x_max = math.log(U)
        dx = (x_max - x_min) / N_s
        dt = T / N_t

        x = np.linspace(x_min, x_max, N_s + 1)

        # Terminal condition: DNT pays notional if surviving to T
        if self.barrier_type == "DNT":
            V = np.ones(N_s + 1) * self.notional
        elif self.barrier_type == "DOT":
            V = np.zeros(N_s + 1)
        else:
            V = np.ones(N_s + 1) * self.notional

        # Boundary conditions: value = 0 at barriers (absorbed)
        V[0] = 0.0
        V[-1] = 0.0

        # PDE coefficients for transformed BS in log-spot:
        # dV/dt + 0.5*sigma^2 * d^2V/dx^2 + (r - q - 0.5*sigma^2)*dV/dx - r*V = 0
        mu = r - q - 0.5 * sigma**2
        alpha = 0.5 * sigma**2 * dt / (dx**2)
        beta = mu * dt / (2 * dx)

        # Crank-Nicolson: 0.5*(implicit + explicit)
        # Interior points: i = 1..N_s-1
        n_interior = N_s - 1

        # Tridiagonal matrix coefficients for implicit step (LHS)
        # -0.5*a_j * V_{j-1}^{n+1} + (1 + 0.5*b_j) * V_j^{n+1} - 0.5*c_j * V_{j+1}^{n+1} = RHS
        a = -0.5 * (alpha - beta)  # lower diagonal
        b = 1 + alpha + 0.5 * r * dt  # main diagonal
        c = -0.5 * (alpha + beta)  # upper diagonal

        # Explicit step coefficients (RHS)
        a_e = 0.5 * (alpha - beta)
        b_e = 1 - alpha - 0.5 * r * dt
        c_e = 0.5 * (alpha + beta)

        # Build banded matrix for scipy.linalg.solve_banded
        # Format: (1, 1) -> banded[0]=upper, banded[1]=main, banded[2]=lower
        ab = np.zeros((3, n_interior))
        ab[0, 1:] = c      # upper diagonal (shifted)
        ab[1, :] = b        # main diagonal
        ab[2, :-1] = a      # lower diagonal (shifted)

        # Time-stepping: backward from T to 0
        for _ in range(N_t):
            # Explicit (RHS) computation for interior points
            rhs = np.zeros(n_interior)
            V_int = V[1:-1]

            for j in range(n_interior):
                val = b_e * V_int[j]
                if j > 0:
                    val += a_e * V_int[j - 1]
                if j < n_interior - 1:
                    val += c_e * V_int[j + 1]
                rhs[j] = val

            # Solve tridiagonal system
            V_int_new = solve_banded((1, 1), ab, rhs)

            V[1:-1] = V_int_new
            V[0] = 0.0
            V[-1] = 0.0

        # Interpolate to get value at S0
        x0 = math.log(S0)
        idx = np.searchsorted(x, x0) - 1
        idx = max(0, min(idx, N_s - 1))

        if idx >= N_s:
            return float(V[-1])

        # Linear interpolation
        w = (x0 - x[idx]) / dx if dx > 0 else 0
        value = V[idx] * (1 - w) + V[idx + 1] * w

        return float(value)


class LocalVolDupirePricer:
    """Local-vol Dupire FX barrier pricer.

    Uses a calibrated local-volatility surface sigma_L(S, t) instead of
    a constant vol. Falls back to Crank-Nicolson PDE with a
    space-time-varying diffusion coefficient.
    """

    def __init__(
        self,
        spot: float,
        lower_barrier: float,
        upper_barrier: float,
        maturity: float,
        notional: float,
        r_dom: float,
        r_for: float,
        vol_surface: list[dict[str, float]] | None = None,
        flat_vol: float = 0.10,
        barrier_type: str = "DNT",
        n_spot: int = 200,
        n_time: int = 500,
    ):
        """
        Args:
            vol_surface: list of {"spot": S, "time": t, "vol": sigma_L}
                         If None, uses flat_vol everywhere.
        """
        self.spot = spot
        self.lower_barrier = lower_barrier
        self.upper_barrier = upper_barrier
        self.maturity = maturity
        self.notional = notional
        self.r_dom = r_dom
        self.r_for = r_for
        self.barrier_type = barrier_type.upper()
        self.n_spot = n_spot
        self.n_time = n_time
        self.flat_vol = flat_vol

        # Build local-vol grid from surface points
        self._vol_data = vol_surface

    def _local_vol(self, S: float, t: float) -> float:
        """Retrieve local vol at (S, t) via nearest-neighbor interpolation.

        For a production system this would use a Dupire-calibrated surface.
        Here we support either a provided grid or flat vol.
        """
        if self._vol_data is None or len(self._vol_data) == 0:
            return self.flat_vol

        # Simple nearest-neighbor in (S, t) space
        best_dist = float("inf")
        best_vol = self.flat_vol
        for pt in self._vol_data:
            d = ((pt["spot"] - S) / S) ** 2 + ((pt["time"] - t) / max(t, 0.01)) ** 2
            if d < best_dist:
                best_dist = d
                best_vol = pt["vol"]
        return best_vol

    def price(self) -> float:
        """Crank-Nicolson PDE with local-vol diffusion."""
        L = self.lower_barrier
        U = self.upper_barrier
        S0 = self.spot
        T = self.maturity
        r = self.r_dom
        q = self.r_for
        N_s = self.n_spot
        N_t = self.n_time

        x_min = math.log(L)
        x_max = math.log(U)
        dx = (x_max - x_min) / N_s
        dt = T / N_t

        x_grid = np.linspace(x_min, x_max, N_s + 1)
        S_grid = np.exp(x_grid)

        # Terminal condition
        if self.barrier_type == "DNT":
            V = np.ones(N_s + 1) * self.notional
        else:
            V = np.zeros(N_s + 1)

        V[0] = 0.0
        V[-1] = 0.0

        n_interior = N_s - 1

        for step in range(N_t):
            t = T - step * dt  # current time (backward)

            # Build tridiagonal with local vol at each node
            ab = np.zeros((3, n_interior))
            rhs = np.zeros(n_interior)

            for j in range(n_interior):
                S_j = S_grid[j + 1]
                sigma_j = self._local_vol(S_j, t)
                mu_j = r - q - 0.5 * sigma_j**2

                alpha_j = 0.5 * sigma_j**2 * dt / (dx**2)
                beta_j = mu_j * dt / (2 * dx)

                # Implicit (LHS)
                a_j = -0.5 * (alpha_j - beta_j)
                b_j = 1 + alpha_j + 0.5 * r * dt
                c_j = -0.5 * (alpha_j + beta_j)

                ab[1, j] = b_j
                if j < n_interior - 1:
                    ab[0, j + 1] = c_j
                if j > 0:
                    ab[2, j - 1] = a_j

                # Explicit (RHS)
                a_e = 0.5 * (alpha_j - beta_j)
                b_e = 1 - alpha_j - 0.5 * r * dt
                c_e = 0.5 * (alpha_j + beta_j)

                val = b_e * V[j + 1]
                if j > 0:
                    val += a_e * V[j]
                if j < n_interior - 1:
                    val += c_e * V[j + 2]
                rhs[j] = val

            V_int = solve_banded((1, 1), ab, rhs)
            V[1:-1] = V_int
            V[0] = 0.0
            V[-1] = 0.0

        # Interpolate at S0
        x0 = math.log(S0)
        idx = np.searchsorted(x_grid, x0) - 1
        idx = max(0, min(idx, N_s - 1))
        w = (x0 - x_grid[idx]) / dx if dx > 0 else 0
        value = V[idx] * (1 - w) + V[idx + 1] * w

        return float(value)

"""PnL Attribution and Decomposition Engine.

Breaks down daily portfolio P&L into risk-factor components using
Taylor expansion of option value changes:

    Total PnL = Delta PnL + Gamma PnL + Vega PnL + Theta PnL
              + Rho PnL + Cross Gamma PnL + Unexplained

Each component isolates a specific risk dimension:
  - Delta PnL:      directional spot risk
  - Gamma PnL:      convexity / non-linear spot risk
  - Vega PnL:       implied-volatility risk
  - Theta PnL:      time-decay
  - Rho PnL:        interest-rate risk
  - Cross Gamma:    spot-vol cross effects
  - Unexplained:    residual (higher-order terms, discrete hedging, etc.)

Reference: Excel Greeks_PnL_Attribution sheet.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class PnLComponentType(str, Enum):
    DELTA = "delta_pnl"
    GAMMA = "gamma_pnl"
    VEGA = "vega_pnl"
    THETA = "theta_pnl"
    RHO = "rho_pnl"
    CROSS_GAMMA = "cross_gamma_pnl"
    UNEXPLAINED = "unexplained_pnl"


@dataclass
class GreeksSnapshot:
    """Greeks values at a point in time."""

    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    theta: float = 0.0
    rho: float = 0.0
    vanna: float = 0.0
    volga: float = 0.0
    charm: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "delta": self.delta,
            "gamma": self.gamma,
            "vega": self.vega,
            "theta": self.theta,
            "rho": self.rho,
            "vanna": self.vanna,
            "volga": self.volga,
            "charm": self.charm,
        }


@dataclass
class MarketDataSnapshot:
    """Market data at a point in time."""

    spot: float
    vol: float
    r_dom: float
    r_for: float
    observation_date: Optional[str] = None


@dataclass
class PnLComponent:
    """Single P&L component with attribution details."""

    component_type: str
    value: float
    description: str
    percentage_of_total: float = 0.0


@dataclass
class PnLAttributionResult:
    """Complete P&L decomposition result."""

    total_pnl: float
    delta_pnl: float
    gamma_pnl: float
    vega_pnl: float
    theta_pnl: float
    rho_pnl: float
    cross_gamma_pnl: float
    unexplained_pnl: float
    explained_pnl: float
    explanation_ratio: float
    components: list[dict[str, Any]]
    market_moves: dict[str, float]
    greeks_used: dict[str, float]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_pnl": round(self.total_pnl, 2),
            "delta_pnl": round(self.delta_pnl, 2),
            "gamma_pnl": round(self.gamma_pnl, 2),
            "vega_pnl": round(self.vega_pnl, 2),
            "theta_pnl": round(self.theta_pnl, 2),
            "rho_pnl": round(self.rho_pnl, 2),
            "cross_gamma_pnl": round(self.cross_gamma_pnl, 2),
            "unexplained_pnl": round(self.unexplained_pnl, 2),
            "explained_pnl": round(self.explained_pnl, 2),
            "explanation_ratio": round(self.explanation_ratio, 4),
            "components": self.components,
            "market_moves": {k: round(v, 8) for k, v in self.market_moves.items()},
            "greeks_used": {k: round(v, 6) for k, v in self.greeks_used.items()},
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# Barrier-specific Greeks reference values (EUR/USD DNT from Excel)
# ---------------------------------------------------------------------------

@dataclass
class BarrierGreeksReference:
    """Reference Greeks for barrier options from the Excel specification.

    EUR/USD DNT barrier option:
      - Delta:  $1,500,000 per 1 pip spot move
      - Gamma:  increases near barriers (high convexity)
      - Vega:   $500,000 per 1% vol move
      - Theta:  -$900/day (time decay)

    Bump calibration from Excel:
      - Spot bump +1 pip (1.0823 -> 1.0824):
          FV: $310,000 -> $309,850  =>  Delta = -$150 per pip
          Scaled to notional: $1,500,000 per pip
      - Vol bump +100bps (6.8% -> 7.8%):
          FV: $310,000 -> $289,000  =>  Vega = -$21,000 per 1%
    """

    delta_per_pip: float = 1_500_000.0
    vega_per_pct: float = 500_000.0
    theta_per_day: float = -900.0

    # Bump sensitivities from Excel calibration
    spot_bump_delta_per_pip: float = -150.0
    vol_bump_vega_per_pct: float = -21_000.0
    base_fair_value: float = 310_000.0
    spot_bumped_fv: float = 309_850.0
    vol_bumped_fv: float = 289_000.0


# ---------------------------------------------------------------------------
# PnL Attribution Engine
# ---------------------------------------------------------------------------

class PnLAttributionEngine:
    """Decompose daily P&L into risk-factor components.

    Uses Taylor expansion of option value V(S, sigma, r, t):

        dV ~ (dV/dS)*dS
           + 0.5*(d2V/dS2)*(dS)^2
           + (dV/dsigma)*dsigma
           + (dV/dt)*dt
           + (dV/dr)*dr
           + (d2V/dS*dsigma)*dS*dsigma
           + higher-order terms (captured as unexplained)
    """

    def __init__(
        self,
        notional: float = 1_000_000.0,
        pip_size: float = 0.0001,
    ):
        self.notional = notional
        self.pip_size = pip_size

    def decompose(
        self,
        greeks: GreeksSnapshot,
        market_data_t0: MarketDataSnapshot,
        market_data_t1: MarketDataSnapshot,
        total_pnl: float,
        time_elapsed_days: float = 1.0,
    ) -> PnLAttributionResult:
        """Full P&L decomposition from Greeks and market moves.

        Parameters
        ----------
        greeks : GreeksSnapshot
            Start-of-day Greeks (delta, gamma, vega, theta, rho, etc.).
        market_data_t0 : MarketDataSnapshot
            Start-of-day market data.
        market_data_t1 : MarketDataSnapshot
            End-of-day market data.
        total_pnl : float
            Actual observed P&L for the period.
        time_elapsed_days : float
            Number of calendar days elapsed (default 1).

        Returns
        -------
        PnLAttributionResult
            Full decomposition with all components.
        """
        # Market moves
        delta_s = market_data_t1.spot - market_data_t0.spot
        delta_vol = market_data_t1.vol - market_data_t0.vol
        delta_r = market_data_t1.r_dom - market_data_t0.r_dom
        delta_t = time_elapsed_days / 365.0

        spot_move_pips = delta_s / self.pip_size if self.pip_size != 0 else 0.0
        vol_move_pct = delta_vol * 100.0  # convert decimal to percentage points

        # --- P&L Components (Taylor expansion) ---

        # Delta P&L = Delta * dS
        # Delta is dV/dS, so Delta PnL captures first-order spot sensitivity
        delta_pnl = greeks.delta * delta_s

        # Gamma P&L = 0.5 * Gamma * (dS)^2
        # Gamma is d2V/dS2, so this captures convexity (non-linear spot risk)
        gamma_pnl = 0.5 * greeks.gamma * delta_s ** 2

        # Vega P&L = Vega * d(sigma)
        # Vega is dV/d(sigma), so captures implied vol sensitivity
        vega_pnl = greeks.vega * delta_vol

        # Theta P&L = Theta * dt
        # Theta is dV/dt (time decay), typically negative for long options
        theta_pnl = greeks.theta * delta_t

        # Rho P&L = Rho * dr
        # Rho is dV/dr, captures interest rate sensitivity
        rho_pnl = greeks.rho * delta_r

        # Cross Gamma (Vanna term) = Vanna * dS * d(sigma)
        # Captures the interaction between spot and vol moves
        cross_gamma_pnl = greeks.vanna * delta_s * delta_vol

        # Volga contribution = 0.5 * Volga * (d_sigma)^2
        # Second-order vol sensitivity
        volga_pnl = 0.5 * greeks.volga * delta_vol ** 2

        # Charm contribution = Charm * dS * dt
        # Captures delta change over time
        charm_pnl = greeks.charm * delta_s * delta_t

        # Include higher-order terms in cross gamma for reporting simplicity
        cross_gamma_total = cross_gamma_pnl + volga_pnl + charm_pnl

        # Sum of all explained components
        explained_pnl = (
            delta_pnl
            + gamma_pnl
            + vega_pnl
            + theta_pnl
            + rho_pnl
            + cross_gamma_total
        )

        # Unexplained = Total PnL - Explained
        unexplained_pnl = total_pnl - explained_pnl

        # Explanation ratio (how well Greeks explain total PnL)
        if abs(total_pnl) > 1e-10:
            explanation_ratio = explained_pnl / total_pnl
        else:
            explanation_ratio = 1.0 if abs(explained_pnl) < 1e-10 else 0.0

        # Build component list with percentages
        components = []
        for comp_type, comp_value, desc in [
            (PnLComponentType.DELTA, delta_pnl,
             f"Delta * dS = {greeks.delta:.2f} * {delta_s:.6f}"),
            (PnLComponentType.GAMMA, gamma_pnl,
             f"0.5 * Gamma * dS^2 = 0.5 * {greeks.gamma:.2f} * {delta_s:.6f}^2"),
            (PnLComponentType.VEGA, vega_pnl,
             f"Vega * d_vol = {greeks.vega:.2f} * {delta_vol:.6f}"),
            (PnLComponentType.THETA, theta_pnl,
             f"Theta * dt = {greeks.theta:.2f} * {delta_t:.6f}"),
            (PnLComponentType.RHO, rho_pnl,
             f"Rho * dr = {greeks.rho:.2f} * {delta_r:.6f}"),
            (PnLComponentType.CROSS_GAMMA, cross_gamma_total,
             f"Cross effects (vanna + volga + charm)"),
            (PnLComponentType.UNEXPLAINED, unexplained_pnl,
             "Total PnL - Sum(explained components)"),
        ]:
            pct_of_total = (
                (comp_value / total_pnl * 100.0)
                if abs(total_pnl) > 1e-10
                else 0.0
            )
            components.append({
                "component_type": comp_type.value,
                "value": round(comp_value, 2),
                "description": desc,
                "percentage_of_total": round(pct_of_total, 2),
            })

        market_moves = {
            "spot_move": delta_s,
            "spot_move_pips": spot_move_pips,
            "vol_move": delta_vol,
            "vol_move_pct": vol_move_pct,
            "rate_move": delta_r,
            "time_elapsed_days": time_elapsed_days,
        }

        greeks_used = greeks.to_dict()

        # Diagnostics
        diagnostics = {
            "notional": self.notional,
            "pip_size": self.pip_size,
            "explanation_quality": self._classify_explanation(explanation_ratio),
            "largest_component": self._find_largest_component(components),
            "cross_gamma_breakdown": {
                "vanna_pnl": round(cross_gamma_pnl, 2),
                "volga_pnl": round(volga_pnl, 2),
                "charm_pnl": round(charm_pnl, 2),
            },
        }

        return PnLAttributionResult(
            total_pnl=total_pnl,
            delta_pnl=delta_pnl,
            gamma_pnl=gamma_pnl,
            vega_pnl=vega_pnl,
            theta_pnl=theta_pnl,
            rho_pnl=rho_pnl,
            cross_gamma_pnl=cross_gamma_total,
            unexplained_pnl=unexplained_pnl,
            explained_pnl=explained_pnl,
            explanation_ratio=explanation_ratio,
            components=components,
            market_moves=market_moves,
            greeks_used=greeks_used,
            diagnostics=diagnostics,
        )

    def decompose_from_pricer(
        self,
        pricer: object,
        price_fn: callable,
        market_data_t0: MarketDataSnapshot,
        market_data_t1: MarketDataSnapshot,
        total_pnl: float,
        time_elapsed_days: float = 1.0,
        spot_attr: str = "spot",
        vol_attr: str = "vol",
        maturity_attr: str = "maturity",
        rate_attr: str = "r_dom",
    ) -> PnLAttributionResult:
        """Compute P&L decomposition by first calculating Greeks from a pricer.

        Uses the GreeksCalculator to bump-and-reprice, then feeds
        the resulting Greeks into the standard decomposition.
        """
        from app.greeks.calculator import GreeksCalculator

        calc = GreeksCalculator(pricer, price_fn)
        raw_greeks = calc.all(
            spot_attr=spot_attr,
            vol_attr=vol_attr,
            maturity_attr=maturity_attr,
            rate_attr=rate_attr,
        )

        greeks = GreeksSnapshot(
            delta=raw_greeks.get("delta", 0.0),
            gamma=raw_greeks.get("gamma", 0.0),
            vega=raw_greeks.get("vega", 0.0),
            theta=raw_greeks.get("theta", 0.0),
            rho=raw_greeks.get("rho", 0.0),
        )

        return self.decompose(
            greeks=greeks,
            market_data_t0=market_data_t0,
            market_data_t1=market_data_t1,
            total_pnl=total_pnl,
            time_elapsed_days=time_elapsed_days,
        )

    # ------------------------------------------------------------------
    # Barrier option specific P&L attribution
    # ------------------------------------------------------------------

    def decompose_barrier(
        self,
        greeks: GreeksSnapshot,
        market_data_t0: MarketDataSnapshot,
        market_data_t1: MarketDataSnapshot,
        total_pnl: float,
        lower_barrier: float,
        upper_barrier: float,
        time_elapsed_days: float = 1.0,
    ) -> PnLAttributionResult:
        """P&L decomposition with barrier-specific adjustments.

        Near barriers, gamma explodes and standard Taylor expansion
        becomes less accurate.  This method adds barrier-proximity
        diagnostics and adjusts the unexplained bucket accordingly.

        From the Excel specification:
          - Delta: $1,500,000 per 1 pip spot move
          - Gamma: increases near barriers (high convexity)
          - Vega:  $500,000 per 1% vol move
          - Theta: -$900/day

        Bump calibration:
          - Spot +1 pip (1.0823->1.0824): FV $310,000->$309,850
            => Delta = -$150/pip, scaled to notional = $1,500,000/pip
          - Vol +100bps (6.8%->7.8%): FV $310,000->$289,000
            => Vega = -$21,000 per 1%
        """
        # Run standard decomposition first
        result = self.decompose(
            greeks=greeks,
            market_data_t0=market_data_t0,
            market_data_t1=market_data_t1,
            total_pnl=total_pnl,
            time_elapsed_days=time_elapsed_days,
        )

        # Add barrier-specific diagnostics
        spot = market_data_t1.spot
        dist_to_lower = spot - lower_barrier
        dist_to_upper = upper_barrier - spot
        barrier_width = upper_barrier - lower_barrier

        proximity_lower = dist_to_lower / barrier_width if barrier_width > 0 else 0
        proximity_upper = dist_to_upper / barrier_width if barrier_width > 0 else 0
        min_proximity = min(proximity_lower, proximity_upper)

        # Barrier proximity warning thresholds
        if min_proximity < 0.05:
            proximity_level = "CRITICAL"
        elif min_proximity < 0.10:
            proximity_level = "HIGH"
        elif min_proximity < 0.20:
            proximity_level = "ELEVATED"
        else:
            proximity_level = "NORMAL"

        # Gamma amplification factor near barriers
        # As spot approaches a barrier, gamma can increase dramatically
        # Use a simple model: amplification ~ 1 / (min_distance_to_barrier)^2
        gamma_amplification = 1.0
        if min_proximity > 0:
            gamma_amplification = max(1.0, 1.0 / (min_proximity ** 0.5))

        result.diagnostics.update({
            "barrier_analysis": {
                "lower_barrier": lower_barrier,
                "upper_barrier": upper_barrier,
                "barrier_width": round(barrier_width, 6),
                "distance_to_lower": round(dist_to_lower, 6),
                "distance_to_upper": round(dist_to_upper, 6),
                "proximity_lower_pct": round(proximity_lower * 100, 2),
                "proximity_upper_pct": round(proximity_upper * 100, 2),
                "proximity_level": proximity_level,
                "gamma_amplification_factor": round(gamma_amplification, 4),
            },
            "barrier_greeks_reference": {
                "delta_per_pip_notional": 1_500_000.0,
                "vega_per_pct_notional": 500_000.0,
                "theta_per_day": -900.0,
                "excel_spot_bump": {
                    "from": 1.0823,
                    "to": 1.0824,
                    "fv_before": 310_000.0,
                    "fv_after": 309_850.0,
                    "delta_per_pip": -150.0,
                },
                "excel_vol_bump": {
                    "from_pct": 6.8,
                    "to_pct": 7.8,
                    "fv_before": 310_000.0,
                    "fv_after": 289_000.0,
                    "vega_per_pct": -21_000.0,
                },
            },
        })

        return result

    # ------------------------------------------------------------------
    # Multi-position aggregation
    # ------------------------------------------------------------------

    def aggregate_positions(
        self,
        position_results: list[PnLAttributionResult],
    ) -> PnLAttributionResult:
        """Aggregate P&L attribution across multiple positions.

        Each position's decomposition is summed component-wise to
        produce a portfolio-level attribution.
        """
        if not position_results:
            return PnLAttributionResult(
                total_pnl=0.0,
                delta_pnl=0.0,
                gamma_pnl=0.0,
                vega_pnl=0.0,
                theta_pnl=0.0,
                rho_pnl=0.0,
                cross_gamma_pnl=0.0,
                unexplained_pnl=0.0,
                explained_pnl=0.0,
                explanation_ratio=1.0,
                components=[],
                market_moves={},
                greeks_used={},
                diagnostics={"position_count": 0},
            )

        total_pnl = sum(r.total_pnl for r in position_results)
        delta_pnl = sum(r.delta_pnl for r in position_results)
        gamma_pnl = sum(r.gamma_pnl for r in position_results)
        vega_pnl = sum(r.vega_pnl for r in position_results)
        theta_pnl = sum(r.theta_pnl for r in position_results)
        rho_pnl = sum(r.rho_pnl for r in position_results)
        cross_gamma_pnl = sum(r.cross_gamma_pnl for r in position_results)
        unexplained_pnl = sum(r.unexplained_pnl for r in position_results)
        explained_pnl = sum(r.explained_pnl for r in position_results)

        if abs(total_pnl) > 1e-10:
            explanation_ratio = explained_pnl / total_pnl
        else:
            explanation_ratio = 1.0 if abs(explained_pnl) < 1e-10 else 0.0

        components = []
        for comp_type, comp_value in [
            (PnLComponentType.DELTA, delta_pnl),
            (PnLComponentType.GAMMA, gamma_pnl),
            (PnLComponentType.VEGA, vega_pnl),
            (PnLComponentType.THETA, theta_pnl),
            (PnLComponentType.RHO, rho_pnl),
            (PnLComponentType.CROSS_GAMMA, cross_gamma_pnl),
            (PnLComponentType.UNEXPLAINED, unexplained_pnl),
        ]:
            pct = (comp_value / total_pnl * 100.0) if abs(total_pnl) > 1e-10 else 0.0
            components.append({
                "component_type": comp_type.value,
                "value": round(comp_value, 2),
                "description": f"Aggregate across {len(position_results)} positions",
                "percentage_of_total": round(pct, 2),
            })

        return PnLAttributionResult(
            total_pnl=total_pnl,
            delta_pnl=delta_pnl,
            gamma_pnl=gamma_pnl,
            vega_pnl=vega_pnl,
            theta_pnl=theta_pnl,
            rho_pnl=rho_pnl,
            cross_gamma_pnl=cross_gamma_pnl,
            unexplained_pnl=unexplained_pnl,
            explained_pnl=explained_pnl,
            explanation_ratio=explanation_ratio,
            components=components,
            market_moves={},
            greeks_used={},
            diagnostics={
                "position_count": len(position_results),
                "explanation_quality": self._classify_explanation(explanation_ratio),
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_explanation(ratio: float) -> str:
        """Classify how well the Greeks explain total P&L."""
        abs_ratio = abs(ratio)
        if abs_ratio >= 0.95:
            return "EXCELLENT"
        elif abs_ratio >= 0.90:
            return "GOOD"
        elif abs_ratio >= 0.80:
            return "ACCEPTABLE"
        elif abs_ratio >= 0.70:
            return "POOR"
        else:
            return "INVESTIGATE"

    @staticmethod
    def _find_largest_component(
        components: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Identify the largest absolute contributor to P&L."""
        if not components:
            return {}
        largest = max(components, key=lambda c: abs(c.get("value", 0.0)))
        return {
            "component": largest.get("component_type", ""),
            "value": largest.get("value", 0.0),
            "percentage": largest.get("percentage_of_total", 0.0),
        }

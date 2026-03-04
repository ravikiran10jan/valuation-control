"""Greeks P&L Attribution — Interactive Simulator Model.

Decomposes option P&L into risk-factor components using Taylor expansion:

    Total PnL = Delta PnL + Gamma PnL + Vega PnL + Theta PnL
              + Rho PnL + Vanna PnL + Volga PnL + Charm PnL
              + Unexplained

Each component isolates a specific risk dimension, allowing traders
and risk managers to understand *why* the book made or lost money.

Reference: Hull Ch.19, Taleb (Dynamic Hedging), Excel Greeks_PnL_Attribution sheet.
"""

from __future__ import annotations

import math
from typing import Any

from app.simulator.base import (
    BaseSimulatorModel,
    CalculationStep,
    ParameterSpec,
    SimulatorResult,
)
from app.simulator.registry import ModelRegistry


@ModelRegistry.register
class GreeksPnLAttributionModel(BaseSimulatorModel):

    model_id = "greeks_pnl_attribution"
    model_name = "Greeks P&L Attribution"
    product_type = "P&L Decomposition"
    asset_class = "greeks"

    short_description = (
        "Decompose daily P&L into Delta, Gamma, Vega, Theta, Rho, Vanna, "
        "Volga, and Charm components with full Taylor expansion"
    )
    long_description = (
        "The Greeks P&L Attribution engine uses a second-order Taylor expansion "
        "of the option value function V(S, sigma, r, t) to decompose observed P&L "
        "into contributions from each risk factor:\n\n"
        "  dV ~ Delta*dS + 0.5*Gamma*dS^2 + Vega*d_sigma + Theta*dt + Rho*dr\n"
        "     + Vanna*dS*d_sigma + 0.5*Volga*d_sigma^2 + Charm*dS*dt\n"
        "     + Unexplained (higher-order terms)\n\n"
        "This is the standard approach used by bank Valuation Control (VC) teams "
        "to validate front-office P&L. A high explanation ratio (>95%) indicates "
        "the Greeks are consistent with observed P&L; a low ratio flags potential "
        "issues with market data, model parameters, or trade population."
    )

    when_to_use = [
        "Daily P&L attribution for options trading desks",
        "Validating that front-office Greeks explain observed P&L",
        "Identifying which risk factor drove the day's P&L",
        "Investigating unexplained P&L (breaks between desk and VC)",
        "Stress testing: understanding P&L impact of large market moves",
    ]
    when_not_to_use = [
        "Real-time intraday P&L (this is an EOD attribution tool)",
        "Linear products (bonds, FX spot) — Greeks attribution adds no value",
        "When Greeks themselves are disputed (use variance analysis first)",
    ]
    assumptions = [
        "Greeks are computed at start-of-day (SOD) and held constant",
        "Market moves are small enough for Taylor expansion to converge",
        "No intraday trading — position is static during the period",
        "Cross-gamma captures Vanna + Volga + Charm interaction terms",
    ]
    limitations = [
        "Breaks down for large intraday moves (higher-order terms dominate)",
        "Does not handle new trades booked during the day",
        "Unexplained bucket grows near barriers or discontinuities",
        "Assumes Greeks are accurate — garbage in, garbage out",
    ]

    formula_latex = (
        r"dV \approx \Delta \cdot dS + \tfrac{1}{2}\Gamma \cdot dS^2 "
        r"+ \mathcal{V} \cdot d\sigma + \Theta \cdot dt + \rho \cdot dr "
        r"+ \text{Vanna} \cdot dS \cdot d\sigma "
        r"+ \tfrac{1}{2}\text{Volga} \cdot d\sigma^2 "
        r"+ \text{Charm} \cdot dS \cdot dt"
    )
    formula_plain = (
        "dV ~ Delta*dS + 0.5*Gamma*dS^2 + Vega*d_sigma + Theta*dt + Rho*dr "
        "+ Vanna*dS*d_sigma + 0.5*Volga*d_sigma^2 + Charm*dS*dt + Unexplained"
    )

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            # Greeks (SOD values)
            ParameterSpec(
                "delta", "Delta", "dV/dS — first-order spot sensitivity",
                "float", 0.55, -10.0, 10.0, 0.01,
            ),
            ParameterSpec(
                "gamma", "Gamma", "d2V/dS2 — convexity / non-linear spot risk",
                "float", 0.025, -5.0, 5.0, 0.001,
            ),
            ParameterSpec(
                "vega", "Vega", "dV/d_sigma — sensitivity to implied volatility",
                "float", 15.0, -500.0, 500.0, 0.1, unit="$/1%vol",
            ),
            ParameterSpec(
                "theta", "Theta", "dV/dt — time decay per year",
                "float", -8.0, -500.0, 500.0, 0.1, unit="$/year",
            ),
            ParameterSpec(
                "rho", "Rho", "dV/dr — interest rate sensitivity",
                "float", 12.0, -500.0, 500.0, 0.1, unit="$/1%rate",
            ),
            ParameterSpec(
                "vanna", "Vanna", "d2V/(dS*d_sigma) — spot-vol cross Greek",
                "float", 0.5, -50.0, 50.0, 0.01,
            ),
            ParameterSpec(
                "volga", "Volga", "d2V/d_sigma^2 — vol convexity",
                "float", 0.3, -50.0, 50.0, 0.01,
            ),
            ParameterSpec(
                "charm", "Charm", "d2V/(dS*dt) — delta decay",
                "float", -0.02, -10.0, 10.0, 0.001,
            ),
            # Market data (SOD)
            ParameterSpec(
                "spot_t0", "Spot (SOD)", "Start-of-day spot price",
                "float", 100.0, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "vol_t0", "Vol (SOD)", "Start-of-day implied volatility",
                "float", 0.20, 0.001, 2.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "rate_t0", "Rate (SOD)", "Start-of-day risk-free rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            # Market data (EOD)
            ParameterSpec(
                "spot_t1", "Spot (EOD)", "End-of-day spot price",
                "float", 101.5, 0.01, None, 0.01, unit="$",
            ),
            ParameterSpec(
                "vol_t1", "Vol (EOD)", "End-of-day implied volatility",
                "float", 0.205, 0.001, 2.0, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "rate_t1", "Rate (EOD)", "End-of-day risk-free rate",
                "float", 0.051, -0.1, 0.5, 0.001, unit="decimal",
            ),
            # Observed total P&L
            ParameterSpec(
                "total_pnl", "Total P&L (Observed)", "Actual observed P&L for the day",
                "float", 1.2, None, None, 0.01, unit="$",
            ),
            # Time elapsed
            ParameterSpec(
                "time_elapsed_days", "Days Elapsed", "Calendar days (typically 1)",
                "float", 1.0, 0.0, 30.0, 1.0, unit="days",
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "Equity Call — normal day": {
                "delta": 0.55, "gamma": 0.025, "vega": 15.0,
                "theta": -8.0, "rho": 12.0,
                "vanna": 0.5, "volga": 0.3, "charm": -0.02,
                "spot_t0": 100.0, "vol_t0": 0.20, "rate_t0": 0.05,
                "spot_t1": 101.5, "vol_t1": 0.205, "rate_t1": 0.051,
                "total_pnl": 1.2, "time_elapsed_days": 1.0,
            },
            "FX Barrier — vol spike": {
                "delta": 1500000.0, "gamma": 8500000.0, "vega": 500000.0,
                "theta": -900.0, "rho": 25000.0,
                "vanna": 120000.0, "volga": 85000.0, "charm": -5000.0,
                "spot_t0": 1.0823, "vol_t0": 0.068, "rate_t0": 0.05,
                "spot_t1": 1.0810, "vol_t1": 0.075, "rate_t1": 0.0505,
                "total_pnl": -52000.0, "time_elapsed_days": 1.0,
            },
            "Rate Swaption — rate move": {
                "delta": 4500.0, "gamma": 12000.0, "vega": 8500.0,
                "theta": -350.0, "rho": 95000.0,
                "vanna": 200.0, "volga": 150.0, "charm": -10.0,
                "spot_t0": 0.042, "vol_t0": 0.45, "rate_t0": 0.042,
                "spot_t1": 0.044, "vol_t1": 0.44, "rate_t1": 0.044,
                "total_pnl": 2150.0, "time_elapsed_days": 1.0,
            },
            "Weekend decay (2 days)": {
                "delta": 0.50, "gamma": 0.030, "vega": 20.0,
                "theta": -12.0, "rho": 8.0,
                "vanna": 0.4, "volga": 0.2, "charm": -0.03,
                "spot_t0": 150.0, "vol_t0": 0.25, "rate_t0": 0.045,
                "spot_t1": 150.5, "vol_t1": 0.248, "rate_t1": 0.045,
                "total_pnl": -0.04, "time_elapsed_days": 2.0,
            },
        }

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        p = self.params_with_defaults(params)

        # Extract Greeks (SOD)
        delta = float(p["delta"])
        gamma = float(p["gamma"])
        vega = float(p["vega"])
        theta = float(p["theta"])
        rho = float(p["rho"])
        vanna = float(p["vanna"])
        volga = float(p["volga"])
        charm = float(p["charm"])

        # Market moves
        spot_t0 = float(p["spot_t0"])
        spot_t1 = float(p["spot_t1"])
        vol_t0 = float(p["vol_t0"])
        vol_t1 = float(p["vol_t1"])
        rate_t0 = float(p["rate_t0"])
        rate_t1 = float(p["rate_t1"])
        total_pnl = float(p["total_pnl"])
        days = float(p["time_elapsed_days"])

        dS = spot_t1 - spot_t0
        d_sigma = vol_t1 - vol_t0
        dr = rate_t1 - rate_t0
        dt = days / 365.0

        steps: list[CalculationStep] = []

        # Step 1: Market moves summary
        spot_pct = (dS / spot_t0 * 100) if spot_t0 != 0 else 0.0
        vol_bps = d_sigma * 10000
        rate_bps = dr * 10000

        steps.append(CalculationStep(
            step_number=1,
            label="Market moves",
            formula="dS = S1 - S0,  d_sigma = sigma1 - sigma0,  dr = r1 - r0",
            substitution=(
                f"dS = {spot_t1} - {spot_t0} = {dS:+.6f} ({spot_pct:+.2f}%)\n"
                f"d_sigma = {vol_t1} - {vol_t0} = {d_sigma:+.6f} ({vol_bps:+.1f} bps)\n"
                f"dr = {rate_t1} - {rate_t0} = {dr:+.6f} ({rate_bps:+.1f} bps)\n"
                f"dt = {days} day(s) = {dt:.6f} years"
            ),
            result=round(dS, 6),
            explanation=(
                "Raw market data changes between SOD and EOD. These drive "
                "the P&L attribution via the Greeks."
            ),
        ))

        # Step 2: First-order terms
        delta_pnl = delta * dS
        vega_pnl = vega * d_sigma
        theta_pnl = theta * dt
        rho_pnl = rho * dr

        steps.append(CalculationStep(
            step_number=2,
            label="First-order P&L components",
            formula=(
                "Delta PnL = Delta * dS\n"
                "Vega PnL = Vega * d_sigma\n"
                "Theta PnL = Theta * dt\n"
                "Rho PnL = Rho * dr"
            ),
            substitution=(
                f"Delta PnL = {delta} * {dS:+.6f} = {delta_pnl:+.4f}\n"
                f"Vega PnL  = {vega} * {d_sigma:+.6f} = {vega_pnl:+.4f}\n"
                f"Theta PnL = {theta} * {dt:.6f} = {theta_pnl:+.4f}\n"
                f"Rho PnL   = {rho} * {dr:+.6f} = {rho_pnl:+.4f}"
            ),
            result=round(delta_pnl + vega_pnl + theta_pnl + rho_pnl, 4),
            explanation=(
                "First-order terms capture linear sensitivities. Delta PnL is "
                "usually the largest contributor for directional portfolios."
            ),
        ))

        # Step 3: Second-order terms
        gamma_pnl = 0.5 * gamma * dS ** 2
        vanna_pnl = vanna * dS * d_sigma
        volga_pnl = 0.5 * volga * d_sigma ** 2
        charm_pnl = charm * dS * dt

        steps.append(CalculationStep(
            step_number=3,
            label="Second-order P&L components",
            formula=(
                "Gamma PnL = 0.5 * Gamma * dS^2\n"
                "Vanna PnL = Vanna * dS * d_sigma\n"
                "Volga PnL = 0.5 * Volga * d_sigma^2\n"
                "Charm PnL = Charm * dS * dt"
            ),
            substitution=(
                f"Gamma PnL = 0.5 * {gamma} * {dS:.6f}^2 = {gamma_pnl:+.6f}\n"
                f"Vanna PnL = {vanna} * {dS:.6f} * {d_sigma:.6f} = {vanna_pnl:+.6f}\n"
                f"Volga PnL = 0.5 * {volga} * {d_sigma:.6f}^2 = {volga_pnl:+.6f}\n"
                f"Charm PnL = {charm} * {dS:.6f} * {dt:.6f} = {charm_pnl:+.6f}"
            ),
            result=round(gamma_pnl + vanna_pnl + volga_pnl + charm_pnl, 6),
            explanation=(
                "Second-order terms capture convexity effects. Gamma P&L is always "
                "positive for long gamma positions (profitable on large moves). "
                "Vanna and Volga are cross-gamma effects often bundled together."
            ),
        ))

        # Step 4: Total explained vs unexplained
        explained = (
            delta_pnl + gamma_pnl + vega_pnl + theta_pnl
            + rho_pnl + vanna_pnl + volga_pnl + charm_pnl
        )
        unexplained = total_pnl - explained

        if abs(total_pnl) > 1e-10:
            explanation_ratio = explained / total_pnl
        else:
            explanation_ratio = 1.0 if abs(explained) < 1e-10 else 0.0

        # Classify explanation quality
        abs_ratio = abs(explanation_ratio)
        if abs_ratio >= 0.95:
            quality = "EXCELLENT"
        elif abs_ratio >= 0.90:
            quality = "GOOD"
        elif abs_ratio >= 0.80:
            quality = "ACCEPTABLE"
        elif abs_ratio >= 0.70:
            quality = "POOR"
        else:
            quality = "INVESTIGATE"

        steps.append(CalculationStep(
            step_number=4,
            label="P&L attribution summary",
            formula="Explained = sum(all components);  Unexplained = Total - Explained",
            substitution=(
                f"Explained PnL = {explained:+.4f}\n"
                f"Total PnL (observed) = {total_pnl:+.4f}\n"
                f"Unexplained = {total_pnl} - {explained:.4f} = {unexplained:+.4f}\n"
                f"Explanation ratio = {explained:.4f} / {total_pnl} = {explanation_ratio:.4f} ({explanation_ratio*100:.1f}%)\n"
                f"Quality: {quality}"
            ),
            result=round(explanation_ratio, 4),
            explanation=(
                f"Explanation ratio of {explanation_ratio*100:.1f}% is rated '{quality}'. "
                f"Values above 95% indicate Greeks fully explain the observed P&L. "
                f"Below 80% warrants investigation into market data, model, or trade population."
            ),
        ))

        # Step 5: Waterfall (largest to smallest)
        components = [
            ("Delta PnL", delta_pnl),
            ("Gamma PnL", gamma_pnl),
            ("Vega PnL", vega_pnl),
            ("Theta PnL", theta_pnl),
            ("Rho PnL", rho_pnl),
            ("Vanna PnL", vanna_pnl),
            ("Volga PnL", volga_pnl),
            ("Charm PnL", charm_pnl),
            ("Unexplained", unexplained),
        ]
        sorted_components = sorted(components, key=lambda x: abs(x[1]), reverse=True)

        waterfall_lines = []
        for name, val in sorted_components:
            pct = (val / total_pnl * 100) if abs(total_pnl) > 1e-10 else 0.0
            bar_len = min(int(abs(pct) / 2), 30)
            bar = ("+" if val >= 0 else "-") * max(bar_len, 1)
            waterfall_lines.append(f"  {name:15s} {val:>+12.4f}  ({pct:>+7.1f}%)  {bar}")

        steps.append(CalculationStep(
            step_number=5,
            label="P&L waterfall (sorted by magnitude)",
            formula="Component breakdown sorted by |contribution|",
            substitution="\n".join(waterfall_lines),
            result=round(total_pnl, 4),
            explanation=(
                "Waterfall view shows which risk factors drove the day's P&L. "
                "The largest absolute contributor is the primary risk driver."
            ),
        ))

        # Build component dict for greeks output
        greeks_output = {
            "delta_pnl": round(delta_pnl, 4),
            "gamma_pnl": round(gamma_pnl, 4),
            "vega_pnl": round(vega_pnl, 4),
            "theta_pnl": round(theta_pnl, 4),
            "rho_pnl": round(rho_pnl, 4),
            "vanna_pnl": round(vanna_pnl, 6),
            "volga_pnl": round(volga_pnl, 6),
            "charm_pnl": round(charm_pnl, 6),
            "explained_pnl": round(explained, 4),
            "unexplained_pnl": round(unexplained, 4),
        }

        return SimulatorResult(
            fair_value=round(explained, 4),
            method="Taylor Expansion P&L Attribution (2nd order)",
            greeks=greeks_output,
            calculation_steps=steps,
            diagnostics={
                "total_pnl": round(total_pnl, 4),
                "explained_pnl": round(explained, 4),
                "unexplained_pnl": round(unexplained, 4),
                "explanation_ratio": round(explanation_ratio, 4),
                "explanation_quality": quality,
                "market_moves": {
                    "spot_change": round(dS, 6),
                    "spot_change_pct": round(spot_pct, 4),
                    "vol_change": round(d_sigma, 6),
                    "vol_change_bps": round(vol_bps, 2),
                    "rate_change": round(dr, 6),
                    "rate_change_bps": round(rate_bps, 2),
                    "time_elapsed_days": days,
                },
                "component_breakdown": {
                    name: round(val, 6)
                    for name, val in components
                },
                "largest_contributor": sorted_components[0][0],
                "largest_contributor_value": round(sorted_components[0][1], 4),
            },
        )

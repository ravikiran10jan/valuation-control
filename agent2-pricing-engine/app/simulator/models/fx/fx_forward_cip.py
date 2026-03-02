"""FX Forward pricing via Covered Interest Rate Parity (CIP).

The most fundamental relationship in FX markets: the forward rate is
fully determined by the spot rate and the interest rate differential.
Any deviation from CIP creates a risk-free arbitrage opportunity.
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
class FXForwardCIPModel(BaseSimulatorModel):

    model_id = "fx_forward_cip"
    model_name = "FX Forward — Covered Interest Parity"
    product_type = "FX Forward / FX Swap"
    asset_class = "fx"

    short_description = "No-arbitrage FX forward rate from interest rate differentials"
    long_description = (
        "The Covered Interest Rate Parity (CIP) relationship determines the fair "
        "forward FX rate from the spot rate and the domestic/foreign interest rate "
        "differential. F = S × exp((r_d - r_f) × T) in continuous compounding, or "
        "equivalently F = S × (1 + r_d × T) / (1 + r_f × T) in simple compounding. "
        "This is the no-arbitrage condition: borrowing in one currency, converting "
        "spot, investing in the other, and hedging with a forward must yield zero "
        "profit. Deviations (the 'cross-currency basis') indicate funding stress."
    )

    when_to_use = [
        "Pricing FX forwards and FX swaps",
        "Computing forward points for any currency pair and tenor",
        "Verifying forward rates quoted by counterparties",
        "Building the forward curve for FX option pricing",
        "Understanding carry trades and interest rate differentials",
    ]
    when_not_to_use = [
        "If cross-currency basis is significant — adjust for basis spread",
        "For NDF (non-deliverable forward) currencies — use NDF-specific conventions",
        "When rates have significant day-count or compounding convention differences",
        "For very long tenors where rate curve shape matters — use full curve bootstrap",
    ]
    assumptions = [
        "Covered Interest Rate Parity holds (no cross-currency basis)",
        "Continuous compounding for both rates (or simple, selectable)",
        "No credit risk on the forward contract",
        "Rates are constant over the forward period",
        "No capital controls or convertibility restrictions",
    ]
    limitations = [
        "Does not capture cross-currency basis (post-2008 persistent deviation)",
        "Assumes flat rate curves — real forwards use interpolated curves",
        "Ignores bid-ask spread on rates and spot",
        "Simple/continuous compounding may differ from market day-count conventions",
    ]

    formula_latex = (
        r"F = S \cdot e^{(r_d - r_f) \cdot T}"
        r"\quad\text{or}\quad"
        r"F = S \cdot \frac{1 + r_d \cdot T}{1 + r_f \cdot T}"
    )
    formula_plain = (
        "F = S × exp((r_dom - r_for) × T)  [continuous],  "
        "F = S × (1 + r_dom × T) / (1 + r_for × T)  [simple]"
    )

    # ── Parameters ──────────────────────────────────────────────

    def get_parameters(self) -> list[ParameterSpec]:
        return [
            ParameterSpec(
                "spot", "Spot Rate (S)", "Spot FX rate (domestic per foreign)",
                "float", 1.0800, 0.0001, None, 0.0001, unit="DOM/FOR",
            ),
            ParameterSpec(
                "r_dom", "Domestic Rate (r_d)", "Domestic risk-free rate",
                "float", 0.05, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "r_for", "Foreign Rate (r_f)", "Foreign risk-free rate",
                "float", 0.03, -0.1, 0.5, 0.001, unit="decimal",
            ),
            ParameterSpec(
                "maturity", "Tenor (T)", "Forward tenor in years",
                "float", 0.25, 0.001, 30.0, 0.01, unit="years",
            ),
            ParameterSpec(
                "notional", "Notional (foreign)", "Foreign currency notional amount",
                "float", 1_000_000.0, 1.0, None, 1000.0, unit="FOR",
            ),
            ParameterSpec(
                "compounding", "Compounding", "Interest rate compounding convention",
                "select", "continuous", options=["continuous", "simple"],
            ),
        ]

    def get_samples(self) -> dict[str, dict[str, Any]]:
        return {
            "EURUSD 3M Forward": {
                "spot": 1.0800, "r_dom": 0.053, "r_for": 0.035,
                "maturity": 0.25, "notional": 1_000_000.0,
                "compounding": "continuous",
            },
            "USDJPY 6M Forward": {
                "spot": 155.50, "r_dom": 0.001, "r_for": 0.053,
                "maturity": 0.5, "notional": 10_000_000.0,
                "compounding": "continuous",
            },
            "GBPUSD 1Y Forward": {
                "spot": 1.2700, "r_dom": 0.053, "r_for": 0.05,
                "maturity": 1.0, "notional": 5_000_000.0,
                "compounding": "continuous",
            },
            "USDMXN 3M Forward (simple)": {
                "spot": 17.25, "r_dom": 0.11, "r_for": 0.053,
                "maturity": 0.25, "notional": 1_000_000.0,
                "compounding": "simple",
            },
        }

    # ── Calculation ────────────────────────────────────────────

    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        S = float(params["spot"])
        rd = float(params["r_dom"])
        rf = float(params["r_for"])
        T = float(params["maturity"])
        notional = float(params.get("notional", 1_000_000.0))
        compounding = params.get("compounding", "continuous").lower()

        steps: list[CalculationStep] = []

        # Step 1: rate differential
        diff = rd - rf
        steps.append(CalculationStep(
            step_number=1,
            label="Interest rate differential",
            formula=r"\Delta r = r_d - r_f",
            substitution=f"Δr = {rd} - {rf} = {diff:.6f}",
            result=round(diff, 6),
            explanation=(
                "Positive differential means domestic rate > foreign rate; "
                "forward will trade at a premium to spot (foreign currency at discount)."
            ),
        ))

        # Step 2: forward rate
        if compounding == "continuous":
            F = S * math.exp(diff * T)
            steps.append(CalculationStep(
                step_number=2,
                label="Forward rate (continuous)",
                formula=r"F = S \cdot e^{(r_d - r_f) \cdot T}",
                substitution=(
                    f"F = {S} × e^({diff:.6f} × {T})"
                    f" = {S} × {math.exp(diff * T):.6f}"
                ),
                result=round(F, 6),
                explanation="Forward rate using continuous compounding CIP formula.",
            ))
        else:
            F = S * (1 + rd * T) / (1 + rf * T)
            steps.append(CalculationStep(
                step_number=2,
                label="Forward rate (simple)",
                formula=r"F = S \cdot \frac{1 + r_d \cdot T}{1 + r_f \cdot T}",
                substitution=(
                    f"F = {S} × (1 + {rd} × {T}) / (1 + {rf} × {T})"
                    f" = {S} × {1 + rd * T:.6f} / {1 + rf * T:.6f}"
                ),
                result=round(F, 6),
                explanation="Forward rate using simple compounding CIP formula.",
            ))

        # Step 3: forward points
        fwd_points = F - S
        fwd_pips = fwd_points * 10000
        steps.append(CalculationStep(
            step_number=3,
            label="Forward points",
            formula=r"\text{Fwd pts} = F - S,\quad \text{pips} = (F - S) \times 10000",
            substitution=(
                f"Fwd pts = {F:.6f} - {S} = {fwd_points:.6f},  "
                f"Pips = {fwd_pips:.2f}"
            ),
            result=round(fwd_pips, 2),
            explanation=(
                "Forward points are the difference between forward and spot, "
                "typically quoted in pips (×10000 for most pairs)."
            ),
        ))

        # Step 4: domestic value of forward
        dom_value = (F - S) * notional
        steps.append(CalculationStep(
            step_number=4,
            label="Mark-to-market (at inception)",
            formula=r"\text{MTM}_0 = 0 \text{ (at-market forward)}",
            substitution=f"Contract at F = {F:.6f}: MTM at inception = 0 by construction",
            result=0.0,
            explanation=(
                "An at-market forward has zero value at inception. "
                "The P&L on the notional at maturity is (F - K) × N for a long forward."
            ),
        ))

        # Step 5: implied annualized carry
        carry_pct = diff * 100
        carry_annual = fwd_points / S * 100
        steps.append(CalculationStep(
            step_number=5,
            label="Implied carry",
            formula=r"\text{Carry} = (r_d - r_f) \text{ annualized}",
            substitution=(
                f"Rate differential = {carry_pct:.3f}% annualized,  "
                f"Forward premium/discount = {carry_annual:.4f}% for {T}Y"
            ),
            result=round(carry_pct, 3),
            explanation=(
                "The carry is the cost (or benefit) of holding the foreign currency "
                "position. Positive carry_pct means the domestic investor pays more "
                "to borrow domestically than they earn on the foreign deposit."
            ),
        ))

        # Step 6: arbitrage check
        # Compute what you'd get from borrowing domestic, converting, investing foreign
        invest_foreign = (S / S) * math.exp(rf * T) if compounding == "continuous" else (1 + rf * T)
        convert_back = invest_foreign * F
        borrow_cost = math.exp(rd * T) if compounding == "continuous" else (1 + rd * T)
        arb_profit = convert_back - borrow_cost
        steps.append(CalculationStep(
            step_number=6,
            label="CIP arbitrage check",
            formula=(
                r"\text{Borrow 1 DOM} \to \text{Convert to FOR at } S"
                r" \to \text{Invest at } r_f \to \text{Sell forward at } F"
            ),
            substitution=(
                f"Invest 1/S FOR at r_f for T → get {invest_foreign:.6f} FOR → "
                f"sell at F={F:.6f} → {convert_back:.6f} DOM.  "
                f"Borrow cost = {borrow_cost:.6f} DOM.  "
                f"Arbitrage P&L = {arb_profit:.8f}"
            ),
            result=round(arb_profit, 8),
            explanation=(
                "If CIP holds exactly, the arbitrage P&L should be zero. "
                "Any non-zero value (beyond numerical noise) indicates a "
                "cross-currency basis."
            ),
        ))

        return SimulatorResult(
            fair_value=round(F, 6),
            method=f"Covered Interest Parity ({compounding} compounding)",
            greeks={
                "delta_spot": 1.0,
                "delta_r_dom": round(S * T * math.exp(diff * T) / 10000, 6),
                "delta_r_for": round(-S * T * math.exp(diff * T) / 10000, 6),
            },
            calculation_steps=steps,
            diagnostics={
                "spot": S,
                "forward_rate": round(F, 6),
                "forward_points": round(fwd_points, 6),
                "forward_pips": round(fwd_pips, 2),
                "rate_differential": round(diff, 6),
                "compounding": compounding,
                "notional_foreign": notional,
                "notional_domestic_at_forward": round(F * notional, 2),
                "arb_check": round(arb_profit, 10),
            },
        )

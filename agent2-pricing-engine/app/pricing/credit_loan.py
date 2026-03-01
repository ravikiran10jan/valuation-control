"""Distressed-loan pricer using scenario-weighted recovery analysis.

Three scenarios:
  1. Restructuring — NPV of new debt + equity stub
  2. Liquidation  — orderly-liquidation-value of collateral
  3. Market comps — secondary-market comparable-trade analysis
"""

from __future__ import annotations

import math
from typing import Any

from app.pricing.base import BasePricer, PricingResult


class DistressedLoanPricer(BasePricer):
    """Value a distressed loan using a scenario-weighted framework."""

    def __init__(
        self,
        notional: float,
        collateral: dict[str, float],
        financials: dict[str, float],
        time_horizon: float = 1.5,
        currency: str = "USD",
        scenario_weights: dict[str, float] | None = None,
        discount_rate: float = 0.15,
        *,
        # Restructuring assumptions
        new_debt_pct: float = 0.40,
        new_debt_price: float = 0.90,
        ebitda_haircut: float = 0.20,
        reorg_multiple: float = 3.0,
        equity_stub_pct: float = 0.15,
        # Liquidation assumptions
        liquidation_discounts: dict[str, float] | None = None,
        admin_cost_pct: float = 0.05,
        # Comps assumptions
        comps_recovery_rate: float | None = None,
    ):
        self.notional = notional
        self.collateral = collateral
        self.financials = financials
        self.time_horizon = time_horizon
        self.currency = currency
        self.discount_rate = discount_rate

        self.scenario_weights = scenario_weights or {
            "restructuring": 0.50,
            "liquidation": 0.20,
            "comps": 0.30,
        }

        # Restructuring
        self.new_debt_pct = new_debt_pct
        self.new_debt_price = new_debt_price
        self.ebitda_haircut = ebitda_haircut
        self.reorg_multiple = reorg_multiple
        self.equity_stub_pct = equity_stub_pct

        # Liquidation
        self._default_liq_discounts = {
            "cash": 1.00,
            "receivables": 0.80,
            "inventory": 0.50,
            "ppe": 0.30,
            "real_estate": 0.60,
            "intangibles": 0.10,
        }
        self.liquidation_discounts = liquidation_discounts or self._default_liq_discounts
        self.admin_cost_pct = admin_cost_pct

        # Comps
        self.comps_recovery_rate = comps_recovery_rate

    # ── validation ──────────────────────────────────────────────
    def validate_inputs(self) -> list[str]:
        errors: list[str] = []
        if self.notional <= 0:
            errors.append("notional must be > 0")
        w_sum = sum(self.scenario_weights.values())
        if abs(w_sum - 1.0) > 1e-6:
            errors.append(f"scenario weights must sum to 1.0 (got {w_sum})")
        if "ebitda" not in self.financials:
            errors.append("financials must contain 'ebitda'")
        return errors

    # ── Scenario 1: Restructuring ───────────────────────────────
    def restructuring_scenario(self) -> float:
        new_loan_pv = self.new_debt_pct * self.notional * self.new_debt_price

        post_reorg_ebitda = self.financials["ebitda"] * (1 - self.ebitda_haircut)
        ev = post_reorg_ebitda * self.reorg_multiple
        new_debt_amount = self.new_debt_pct * self.notional
        equity_value = max(ev - new_debt_amount, 0.0)
        equity_stub = self.equity_stub_pct * equity_value

        total_pv = (new_loan_pv + equity_stub) * math.exp(
            -self.discount_rate * self.time_horizon
        )
        return total_pv

    # ── Scenario 2: Liquidation ─────────────────────────────────
    def liquidation_scenario(self) -> float:
        gross = 0.0
        for asset_type, value in self.collateral.items():
            discount = self.liquidation_discounts.get(
                asset_type, 0.30
            )
            gross += value * discount

        net = gross * (1 - self.admin_cost_pct)
        pv = net * math.exp(-self.discount_rate * self.time_horizon)
        return min(pv, self.notional)

    # ── Scenario 3: Market comps ────────────────────────────────
    def market_comps_scenario(self) -> float:
        if self.comps_recovery_rate is not None:
            return self.comps_recovery_rate * self.notional

        # Default heuristic: EBITDA / Total Debt ratio as proxy
        total_debt = self.financials.get("total_debt", self.notional)
        ebitda = self.financials["ebitda"]
        leverage = total_debt / max(ebitda, 1)

        # Rough mapping: leverage -> recovery
        if leverage <= 3:
            recovery = 0.80
        elif leverage <= 5:
            recovery = 0.60
        elif leverage <= 7:
            recovery = 0.40
        else:
            recovery = 0.25

        return recovery * self.notional

    # ── primary interface ───────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        scenarios = {
            "restructuring": self.restructuring_scenario(),
            "liquidation": self.liquidation_scenario(),
            "comps": self.market_comps_scenario(),
        }

        fair_value = sum(
            scenarios[s] * self.scenario_weights.get(s, 0) for s in scenarios
        )
        recovery_rate = fair_value / self.notional

        return PricingResult(
            fair_value=fair_value,
            method="scenario_weighted",
            currency=self.currency,
            greeks=self.calculate_greeks(),
            diagnostics={
                "recovery_rate": round(recovery_rate, 4),
                "scenario_values": {k: round(v, 2) for k, v in scenarios.items()},
                "scenario_weights": self.scenario_weights,
            },
            methods=scenarios,
        )

    # ── Greeks (sensitivity to assumptions) ─────────────────────
    def calculate_greeks(self) -> dict[str, float]:
        base = self._combined_value()

        # Sensitivity to discount rate (+1%)
        orig = self.discount_rate
        self.discount_rate = orig + 0.01
        up = self._combined_value()
        self.discount_rate = orig
        rate_sens = up - base

        # Sensitivity to EBITDA (+10%)
        orig_ebitda = self.financials["ebitda"]
        self.financials["ebitda"] = orig_ebitda * 1.10
        up_ebitda = self._combined_value()
        self.financials["ebitda"] = orig_ebitda
        ebitda_sens = up_ebitda - base

        return {
            "discount_rate_sensitivity": rate_sens,
            "ebitda_sensitivity_10pct": ebitda_sens,
        }

    def _combined_value(self) -> float:
        scenarios = {
            "restructuring": self.restructuring_scenario(),
            "liquidation": self.liquidation_scenario(),
            "comps": self.market_comps_scenario(),
        }
        return sum(scenarios[s] * self.scenario_weights.get(s, 0) for s in scenarios)

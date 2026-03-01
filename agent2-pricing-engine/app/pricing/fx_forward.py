"""FX Forward pricing via covered interest rate parity.

    F(T) = S * exp((r_dom - r_for) * T)

For discrete compounding:
    F(T) = S * (1 + r_dom * T) / (1 + r_for * T)

Supports:
  - Outright forward rate
  - Forward points (pips)
  - NDF (non-deliverable forward) fair value
  - Full term-structure of forwards
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.greeks.calculator import GreeksCalculator
from app.pricing.base import BasePricer, PricingResult


class FXForwardPricer(BasePricer):
    """Price FX forwards using interest rate parity."""

    def __init__(
        self,
        spot: float,
        r_dom: float,
        r_for: float,
        maturity: float,
        notional: float = 1_000_000,
        strike: float | None = None,
        currency_pair: str = "EURUSD",
        currency: str = "USD",
        compounding: str = "continuous",
    ):
        """
        Args:
            spot: current FX spot rate
            r_dom: domestic (quote-currency) interest rate
            r_for: foreign (base-currency) interest rate
            maturity: time to delivery in years
            notional: notional in base currency
            strike: contracted forward rate (for mark-to-market of existing position)
            currency_pair: e.g. "EURUSD"
            compounding: "continuous" or "simple"
        """
        self.spot = spot
        self.r_dom = r_dom
        self.r_for = r_for
        self.maturity = maturity
        self.notional = notional
        self.strike = strike
        self.currency_pair = currency_pair.upper().replace("/", "")
        self.currency = currency
        self.compounding = compounding

        # alias for greeks calc
        self.vol = 0.0  # no vol dimension, but needed by GreeksCalculator

    # ── validation ──────────────────────────────────────────────
    def validate_inputs(self) -> list[str]:
        errors: list[str] = []
        if self.spot <= 0:
            errors.append("spot must be > 0")
        if self.maturity < 0:
            errors.append("maturity must be >= 0")
        if self.compounding == "simple" and (1 + self.r_for * self.maturity) <= 0:
            errors.append("(1 + r_for * T) must be > 0 for simple compounding")
        return errors

    # ── core pricing ────────────────────────────────────────────
    def forward_rate(self) -> float:
        """Theoretical outright forward rate via interest rate parity."""
        if self.compounding == "continuous":
            return self.spot * math.exp((self.r_dom - self.r_for) * self.maturity)
        else:
            return self.spot * (1 + self.r_dom * self.maturity) / (1 + self.r_for * self.maturity)

    def forward_points(self) -> float:
        """Forward points = F - S, typically quoted in pips (×10,000)."""
        return self.forward_rate() - self.spot

    def forward_points_pips(self) -> float:
        return self.forward_points() * 10_000

    def mark_to_market(self) -> float:
        """PV of an existing forward position (long base currency).

        MTM = notional * (F_current - K) * DF_dom
        where F_current is the current theoretical forward rate
        and K is the contracted strike.
        """
        if self.strike is None:
            return 0.0
        fwd = self.forward_rate()
        if self.compounding == "continuous":
            df = math.exp(-self.r_dom * self.maturity)
        else:
            df = 1.0 / (1 + self.r_dom * self.maturity)
        return self.notional * (fwd - self.strike) * df

    def term_structure(
        self, tenors: list[float] | None = None
    ) -> list[dict[str, float]]:
        """Build a term structure of forward rates."""
        tenors = tenors or [
            1 / 365, 7 / 365, 1 / 12, 2 / 12, 3 / 12, 6 / 12, 9 / 12, 1.0, 2.0,
        ]
        result = []
        for T in tenors:
            if self.compounding == "continuous":
                fwd = self.spot * math.exp((self.r_dom - self.r_for) * T)
            else:
                denom = 1 + self.r_for * T
                if denom <= 0:
                    continue
                fwd = self.spot * (1 + self.r_dom * T) / denom
            points = (fwd - self.spot) * 10_000
            result.append({
                "tenor_years": round(T, 6),
                "forward_rate": round(fwd, 6),
                "forward_points_pips": round(points, 2),
            })
        return result

    # ── BasePricer interface ────────────────────────────────────
    def price(self) -> PricingResult:
        errors = self.validate_inputs()
        if errors:
            raise ValueError(f"Input validation failed: {errors}")

        fwd = self.forward_rate()
        mtm = self.mark_to_market()
        points_pips = self.forward_points_pips()

        fair_value = mtm if self.strike is not None else fwd

        greeks = self.calculate_greeks()

        return PricingResult(
            fair_value=fair_value,
            method="interest_rate_parity",
            currency=self.currency,
            greeks=greeks,
            diagnostics={
                "currency_pair": self.currency_pair,
                "forward_rate": round(fwd, 6),
                "forward_points_pips": round(points_pips, 2),
                "spot": self.spot,
                "r_dom": self.r_dom,
                "r_for": self.r_for,
                "compounding": self.compounding,
            },
            methods={
                "interest_rate_parity": fair_value,
            },
        )

    # ── Greeks ──────────────────────────────────────────────────
    def calculate_greeks(self) -> dict[str, float]:
        """Forward-specific sensitivities."""
        fwd = self.forward_rate()

        # Delta: dF/dS (exact for continuous)
        if self.compounding == "continuous":
            delta = math.exp((self.r_dom - self.r_for) * self.maturity)
        else:
            delta = (1 + self.r_dom * self.maturity) / (1 + self.r_for * self.maturity)

        # Rho domestic: dF/d(r_dom)
        if self.compounding == "continuous":
            rho_dom = self.spot * self.maturity * math.exp(
                (self.r_dom - self.r_for) * self.maturity
            )
        else:
            rho_dom = self.spot * self.maturity / (1 + self.r_for * self.maturity)

        # Rho foreign: dF/d(r_for)
        if self.compounding == "continuous":
            rho_for = -self.spot * self.maturity * math.exp(
                (self.r_dom - self.r_for) * self.maturity
            )
        else:
            rho_for = (
                -self.spot
                * (1 + self.r_dom * self.maturity)
                * self.maturity
                / (1 + self.r_for * self.maturity) ** 2
            )

        result: dict[str, float] = {
            "delta": delta * self.notional,
            "rho_domestic": rho_dom * self.notional / 10_000,  # per 1bp
            "rho_foreign": rho_for * self.notional / 10_000,
        }

        if self.strike is not None:
            # MTM sensitivities
            if self.compounding == "continuous":
                df = math.exp(-self.r_dom * self.maturity)
            else:
                df = 1.0 / (1 + self.r_dom * self.maturity)
            result["mtm_delta"] = delta * df * self.notional

        return result

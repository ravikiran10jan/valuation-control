"""Finite-difference Greeks calculator that wraps any pricer."""

from __future__ import annotations

import copy
from typing import Callable

from app.core.config import settings


def _bump(obj: object, attr: str, amount: float, relative: bool) -> float:
    """Bump an attribute, return the original value."""
    original = getattr(obj, attr)
    new_val = original * (1 + amount) if relative else original + amount
    setattr(obj, attr, new_val)
    return original


def _reset(obj: object, attr: str, original: float) -> None:
    setattr(obj, attr, original)


class GreeksCalculator:
    """
    Compute finite-difference Greeks for any pricer that exposes a
    ``price_value() -> float`` callable and mutable market-data attributes.
    """

    def __init__(
        self,
        pricer: object,
        price_fn: Callable[[], float],
        *,
        delta_bump: float | None = None,
        vega_bump: float | None = None,
        gamma_bump: float | None = None,
        theta_days: int | None = None,
        rho_bump: float | None = None,
    ):
        self.pricer = pricer
        self.price_fn = price_fn
        self.delta_bump = delta_bump or settings.delta_bump_pct
        self.vega_bump = vega_bump or settings.vega_bump_abs
        self.gamma_bump = gamma_bump or settings.gamma_bump_pct
        self.theta_days = theta_days or settings.theta_bump_days
        self.rho_bump = rho_bump or settings.rho_bump_abs

    # ── individual Greeks ──────────────────────────────────────
    def delta(self, spot_attr: str = "spot") -> float:
        """Central difference dV/dS."""
        base = self.price_fn()
        S = getattr(self.pricer, spot_attr)
        bump = S * self.delta_bump

        setattr(self.pricer, spot_attr, S + bump)
        v_up = self.price_fn()
        setattr(self.pricer, spot_attr, S - bump)
        v_dn = self.price_fn()
        setattr(self.pricer, spot_attr, S)

        return (v_up - v_dn) / (2 * bump)

    def gamma(self, spot_attr: str = "spot") -> float:
        """Central difference d²V/dS²."""
        base = self.price_fn()
        S = getattr(self.pricer, spot_attr)
        bump = S * self.gamma_bump

        setattr(self.pricer, spot_attr, S + bump)
        v_up = self.price_fn()
        setattr(self.pricer, spot_attr, S - bump)
        v_dn = self.price_fn()
        setattr(self.pricer, spot_attr, S)

        return (v_up - 2 * base + v_dn) / (bump**2)

    def vega(self, vol_attr: str = "vol") -> float:
        """Forward difference dV/dσ (per 1 vol-point bump)."""
        base = self.price_fn()
        orig = getattr(self.pricer, vol_attr)

        setattr(self.pricer, vol_attr, orig + self.vega_bump)
        v_up = self.price_fn()
        setattr(self.pricer, vol_attr, orig)

        return v_up - base

    def theta(self, maturity_attr: str = "maturity") -> float:
        """Forward difference dV/dt (1-day decay)."""
        base = self.price_fn()
        T = getattr(self.pricer, maturity_attr)
        day_frac = self.theta_days / 365.0

        setattr(self.pricer, maturity_attr, T - day_frac)
        v_new = self.price_fn()
        setattr(self.pricer, maturity_attr, T)

        return v_new - base

    def rho(self, rate_attr: str = "r_dom") -> float:
        """Forward difference dV/dr (per 1bp bump)."""
        base = self.price_fn()
        orig = getattr(self.pricer, rate_attr)

        setattr(self.pricer, rate_attr, orig + self.rho_bump)
        v_up = self.price_fn()
        setattr(self.pricer, rate_attr, orig)

        return v_up - base

    # ── convenience: compute all at once ────────────────────────
    def all(
        self,
        spot_attr: str = "spot",
        vol_attr: str = "vol",
        maturity_attr: str = "maturity",
        rate_attr: str = "r_dom",
    ) -> dict[str, float]:
        return {
            "delta": self.delta(spot_attr),
            "gamma": self.gamma(spot_attr),
            "vega": self.vega(vol_attr),
            "theta": self.theta(maturity_attr),
            "rho": self.rho(rate_attr),
        }

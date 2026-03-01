"""Abstract base class for all pricers."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PricingResult:
    """Standard result returned by every pricer."""

    fair_value: float
    method: str
    currency: str = "USD"
    greeks: dict[str, float] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    methods: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fair_value": round(self.fair_value, 2),
            "method": self.method,
            "currency": self.currency,
            "greeks": {k: round(v, 2) for k, v in self.greeks.items()},
            "diagnostics": self.diagnostics,
            "methods": {k: round(v, 2) for k, v in self.methods.items()},
        }


class BasePricer(abc.ABC):
    """Every asset-class pricer inherits from this."""

    @abc.abstractmethod
    def price(self) -> PricingResult:
        """Return the primary fair value."""

    @abc.abstractmethod
    def calculate_greeks(self) -> dict[str, float]:
        """Return a dict of Greeks (delta, gamma, vega, theta, rho …)."""

    def validate_inputs(self) -> list[str]:
        """Return a list of validation error strings (empty = OK)."""
        return []

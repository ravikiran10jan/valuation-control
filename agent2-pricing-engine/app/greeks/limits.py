"""Greeks Limits Monitoring and Breach Detection.

Tracks Greek utilization against predefined limits and triggers
escalation actions when thresholds are breached.

Alert levels (from Excel Greeks_PnL_Attribution sheet):
    <70%  utilization  =>  GREEN   (no action)
    70-90% utilization =>  AMBER   (heightened monitoring)
    >90%  utilization  =>  RED     (pre-breach alert)

Breach handling:
    100-110%  =>  Email notification to risk management
    110-125%  =>  Reduce position within 2 hours
    125-150%  =>  Immediate hedging required
    >150%     =>  STOP — halt all new trades, escalate to senior management
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and constants
# ---------------------------------------------------------------------------

class AlertLevel(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class BreachAction(str, Enum):
    NONE = "NONE"
    EMAIL_NOTIFICATION = "EMAIL_NOTIFICATION"
    REDUCE_IN_2H = "REDUCE_IN_2H"
    IMMEDIATE_HEDGE = "IMMEDIATE_HEDGE"
    STOP_TRADING = "STOP_TRADING"


# Utilization-to-alert mapping
ALERT_THRESHOLDS = {
    AlertLevel.GREEN: (0.0, 0.70),    # 0% - 70%
    AlertLevel.AMBER: (0.70, 0.90),   # 70% - 90%
    AlertLevel.RED: (0.90, 1.00),     # 90% - 100%
}

# Breach-to-action mapping
BREACH_ACTIONS = {
    (1.00, 1.10): BreachAction.EMAIL_NOTIFICATION,
    (1.10, 1.25): BreachAction.REDUCE_IN_2H,
    (1.25, 1.50): BreachAction.IMMEDIATE_HEDGE,
    (1.50, float("inf")): BreachAction.STOP_TRADING,
}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class GreekLimit:
    """Definition of a single Greek limit."""

    greek_name: str
    limit_value: float
    unit: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "greek_name": self.greek_name,
            "limit_value": self.limit_value,
            "unit": self.unit,
            "description": self.description,
        }


@dataclass
class GreekLimitSet:
    """Complete set of Greek limits for a desk/portfolio."""

    desk_name: str
    currency_pair: str
    limits: dict[str, GreekLimit] = field(default_factory=dict)
    effective_date: Optional[str] = None
    approved_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "desk_name": self.desk_name,
            "currency_pair": self.currency_pair,
            "limits": {k: v.to_dict() for k, v in self.limits.items()},
            "effective_date": self.effective_date,
            "approved_by": self.approved_by,
        }


@dataclass
class UtilizationResult:
    """Result of checking a single Greek against its limit."""

    greek_name: str
    current_value: float
    limit_value: float
    utilization_pct: float
    alert_level: str
    is_breached: bool
    breach_action: str
    breach_action_description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "greek_name": self.greek_name,
            "current_value": round(self.current_value, 6),
            "limit_value": round(self.limit_value, 6),
            "utilization_pct": round(self.utilization_pct, 2),
            "alert_level": self.alert_level,
            "is_breached": self.is_breached,
            "breach_action": self.breach_action,
            "breach_action_description": self.breach_action_description,
        }


@dataclass
class LimitsCheckResult:
    """Aggregate result of checking all Greeks against limits."""

    desk_name: str
    currency_pair: str
    check_timestamp: str
    overall_status: str
    highest_alert: str
    has_breaches: bool
    breach_count: int
    utilizations: list[dict[str, Any]]
    breaches: list[dict[str, Any]]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "desk_name": self.desk_name,
            "currency_pair": self.currency_pair,
            "check_timestamp": self.check_timestamp,
            "overall_status": self.overall_status,
            "highest_alert": self.highest_alert,
            "has_breaches": self.has_breaches,
            "breach_count": self.breach_count,
            "utilizations": self.utilizations,
            "breaches": self.breaches,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# Default limit definitions
# ---------------------------------------------------------------------------

def get_default_fx_limits(currency_pair: str = "EURUSD") -> GreekLimitSet:
    """Return default FX desk Greek limits.

    These represent typical institutional FX options desk limits.
    In production, these would be loaded from a database or
    configuration service.
    """
    return GreekLimitSet(
        desk_name="FX Options Desk",
        currency_pair=currency_pair,
        limits={
            "delta": GreekLimit(
                greek_name="delta",
                limit_value=50_000_000.0,
                unit="USD",
                description="Maximum delta exposure (USD equivalent)",
            ),
            "gamma": GreekLimit(
                greek_name="gamma",
                limit_value=5_000_000.0,
                unit="USD per 1% spot move",
                description="Maximum gamma exposure",
            ),
            "vega": GreekLimit(
                greek_name="vega",
                limit_value=10_000_000.0,
                unit="USD per 1% vol move",
                description="Maximum vega exposure",
            ),
            "theta": GreekLimit(
                greek_name="theta",
                limit_value=500_000.0,
                unit="USD per day",
                description="Maximum daily time decay",
            ),
            "rho": GreekLimit(
                greek_name="rho",
                limit_value=20_000_000.0,
                unit="USD per 1% rate move",
                description="Maximum interest rate sensitivity",
            ),
        },
        approved_by="Risk Committee",
    )


def get_default_barrier_limits(currency_pair: str = "EURUSD") -> GreekLimitSet:
    """Return default limits specifically for barrier option books.

    Barrier options require tighter limits due to discontinuous
    payoff profiles and gamma amplification near barriers.
    """
    return GreekLimitSet(
        desk_name="FX Exotics Desk — Barriers",
        currency_pair=currency_pair,
        limits={
            "delta": GreekLimit(
                greek_name="delta",
                limit_value=25_000_000.0,
                unit="USD",
                description="Max delta for barrier book (tighter than vanilla)",
            ),
            "gamma": GreekLimit(
                greek_name="gamma",
                limit_value=2_000_000.0,
                unit="USD per 1% spot move",
                description="Max gamma (barrier gamma can spike near barriers)",
            ),
            "vega": GreekLimit(
                greek_name="vega",
                limit_value=5_000_000.0,
                unit="USD per 1% vol move",
                description="Max vega for barrier book",
            ),
            "theta": GreekLimit(
                greek_name="theta",
                limit_value=200_000.0,
                unit="USD per day",
                description="Max daily theta for barrier book",
            ),
            "rho": GreekLimit(
                greek_name="rho",
                limit_value=10_000_000.0,
                unit="USD per 1% rate move",
                description="Max rho for barrier book",
            ),
        },
        approved_by="Risk Committee",
    )


# ---------------------------------------------------------------------------
# Limits Monitor
# ---------------------------------------------------------------------------

class GreeksLimitsMonitor:
    """Monitor Greek utilization against limits and detect breaches."""

    def __init__(self, limit_set: Optional[GreekLimitSet] = None):
        self.limit_set = limit_set or get_default_fx_limits()

    def check_single_greek(
        self,
        greek_name: str,
        current_value: float,
        limit_value: Optional[float] = None,
    ) -> UtilizationResult:
        """Check a single Greek's utilization against its limit.

        Parameters
        ----------
        greek_name : str
            Name of the Greek (delta, gamma, vega, theta, rho).
        current_value : float
            Current absolute value of the Greek.
        limit_value : float, optional
            Override limit value. If None, uses the limit set.

        Returns
        -------
        UtilizationResult
        """
        if limit_value is None:
            limit_def = self.limit_set.limits.get(greek_name)
            if limit_def is None:
                return UtilizationResult(
                    greek_name=greek_name,
                    current_value=current_value,
                    limit_value=0.0,
                    utilization_pct=0.0,
                    alert_level=AlertLevel.GREEN.value,
                    is_breached=False,
                    breach_action=BreachAction.NONE.value,
                    breach_action_description="No limit defined for this Greek",
                )
            limit_value = limit_def.limit_value

        # Utilization is based on absolute value
        abs_current = abs(current_value)
        if limit_value > 0:
            utilization = abs_current / limit_value
        else:
            utilization = 0.0

        utilization_pct = utilization * 100.0

        # Determine alert level
        alert_level = self._get_alert_level(utilization)

        # Determine if breached and what action to take
        is_breached = utilization >= 1.0
        breach_action, breach_desc = self._get_breach_action(utilization)

        return UtilizationResult(
            greek_name=greek_name,
            current_value=current_value,
            limit_value=limit_value,
            utilization_pct=utilization_pct,
            alert_level=alert_level.value,
            is_breached=is_breached,
            breach_action=breach_action.value,
            breach_action_description=breach_desc,
        )

    def check_all_greeks(
        self,
        greeks: dict[str, float],
        desk_name: Optional[str] = None,
        currency_pair: Optional[str] = None,
    ) -> LimitsCheckResult:
        """Check all Greeks against their limits.

        Parameters
        ----------
        greeks : dict[str, float]
            Dictionary of Greek name -> current value.
        desk_name : str, optional
            Override desk name.
        currency_pair : str, optional
            Override currency pair.

        Returns
        -------
        LimitsCheckResult
        """
        desk = desk_name or self.limit_set.desk_name
        ccy = currency_pair or self.limit_set.currency_pair
        timestamp = datetime.utcnow().isoformat() + "Z"

        utilizations = []
        breaches = []
        alert_levels = []

        for greek_name, current_value in greeks.items():
            result = self.check_single_greek(greek_name, current_value)
            utilizations.append(result.to_dict())
            alert_levels.append(result.alert_level)

            if result.is_breached:
                breaches.append(result.to_dict())

        # Determine highest alert level
        highest_alert = self._highest_alert(alert_levels)

        # Overall status
        if breaches:
            overall_status = "BREACH"
        elif highest_alert == AlertLevel.RED.value:
            overall_status = "PRE_BREACH"
        elif highest_alert == AlertLevel.AMBER.value:
            overall_status = "ELEVATED"
        else:
            overall_status = "NORMAL"

        # Build summary
        green_count = sum(
            1 for u in utilizations if u["alert_level"] == AlertLevel.GREEN.value
        )
        amber_count = sum(
            1 for u in utilizations if u["alert_level"] == AlertLevel.AMBER.value
        )
        red_count = sum(
            1 for u in utilizations if u["alert_level"] == AlertLevel.RED.value
        )

        summary = {
            "total_greeks_monitored": len(utilizations),
            "green_count": green_count,
            "amber_count": amber_count,
            "red_count": red_count,
            "breach_count": len(breaches),
            "highest_utilization": (
                max((u["utilization_pct"] for u in utilizations), default=0.0)
            ),
            "most_utilized_greek": (
                max(utilizations, key=lambda u: u["utilization_pct"])["greek_name"]
                if utilizations
                else ""
            ),
        }

        return LimitsCheckResult(
            desk_name=desk,
            currency_pair=ccy,
            check_timestamp=timestamp,
            overall_status=overall_status,
            highest_alert=highest_alert,
            has_breaches=bool(breaches),
            breach_count=len(breaches),
            utilizations=utilizations,
            breaches=breaches,
            summary=summary,
        )

    def get_limit_definitions(self) -> dict[str, Any]:
        """Return the current limit definitions."""
        return {
            "limit_set": self.limit_set.to_dict(),
            "alert_thresholds": {
                level.value: {
                    "min_pct": round(bounds[0] * 100, 1),
                    "max_pct": round(bounds[1] * 100, 1),
                }
                for level, bounds in ALERT_THRESHOLDS.items()
            },
            "breach_actions": [
                {
                    "utilization_range": f"{lo * 100:.0f}%-{hi * 100:.0f}%"
                    if hi != float("inf")
                    else f">{lo * 100:.0f}%",
                    "action": action.value,
                    "description": self._breach_action_description(action),
                }
                for (lo, hi), action in BREACH_ACTIONS.items()
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_alert_level(utilization: float) -> AlertLevel:
        """Map utilization ratio to alert level."""
        if utilization < 0.70:
            return AlertLevel.GREEN
        elif utilization < 0.90:
            return AlertLevel.AMBER
        else:
            return AlertLevel.RED

    @staticmethod
    def _get_breach_action(utilization: float) -> tuple[BreachAction, str]:
        """Map utilization ratio to breach action and description."""
        if utilization < 1.0:
            return BreachAction.NONE, "Within limits — no action required"

        for (lo, hi), action in BREACH_ACTIONS.items():
            if lo <= utilization < hi:
                desc = GreeksLimitsMonitor._breach_action_description(action)
                return action, desc

        # Fallback for extreme breaches
        return (
            BreachAction.STOP_TRADING,
            "CRITICAL: Utilization >150% — STOP all trading, escalate to senior management",
        )

    @staticmethod
    def _breach_action_description(action: BreachAction) -> str:
        """Human-readable description of a breach action."""
        descriptions = {
            BreachAction.NONE: "Within limits — no action required",
            BreachAction.EMAIL_NOTIFICATION: (
                "100-110% breach: Send email notification to risk management"
            ),
            BreachAction.REDUCE_IN_2H: (
                "110-125% breach: Reduce position to within limits within 2 hours"
            ),
            BreachAction.IMMEDIATE_HEDGE: (
                "125-150% breach: Immediate hedging required to reduce exposure"
            ),
            BreachAction.STOP_TRADING: (
                ">150% breach: STOP all new trades immediately, "
                "escalate to senior management, close or hedge within 30 minutes"
            ),
        }
        return descriptions.get(action, "Unknown action")

    @staticmethod
    def _highest_alert(alert_levels: list[str]) -> str:
        """Return the highest alert level from a list."""
        priority = {
            AlertLevel.RED.value: 3,
            AlertLevel.AMBER.value: 2,
            AlertLevel.GREEN.value: 1,
        }
        if not alert_levels:
            return AlertLevel.GREEN.value

        return max(alert_levels, key=lambda a: priority.get(a, 0))

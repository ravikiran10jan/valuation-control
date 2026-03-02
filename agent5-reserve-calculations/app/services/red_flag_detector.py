"""Day 1 P&L Red Flag Detector — Earnings Manipulation Prevention.

Implements the 6 red flags from the FX IPV Model's Day1_PnL_RedFlags sheet.
Each red flag has severity levels (SEVERE, HIGH, MEDIUM) and specific warning signs.

Red Flags:
1. Client Overpaid for Derivative (Premium > 20% above market consensus)
2. No Observable Market for Product (Level 3, zero/few quotes)
3. Bank Has Information Advantage (asymmetric information)
4. Earnings Manipulation Risk (desk gaming Day 1 P&L)
5. Volume Spike at Period End (clustering of Day 1 trades)
6. Frequent Re-marks (positions repeatedly revalued)

Two interfaces:
  - Day1RedFlagDetector class: legacy dataclass-based interface for detailed assessment
  - detect_red_flags() function: Pydantic-based interface integrated with schemas
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

import structlog

from app.models.schemas import (
    PositionInput,
    RedFlag as PydanticRedFlag,
    RedFlagReport as PydanticRedFlagReport,
    RedFlagSeverity as PydanticRedFlagSeverity,
)

log = structlog.get_logger()


# ── Dataclass-based types (legacy interface) ─────────────────────

class RedFlagSeverity(str, Enum):
    SEVERE = "SEVERE"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class RedFlagCategory(str, Enum):
    CLIENT_OVERPAID = "CLIENT_OVERPAID"
    NO_OBSERVABLE_MARKET = "NO_OBSERVABLE_MARKET"
    INFORMATION_ADVANTAGE = "INFORMATION_ADVANTAGE"
    EARNINGS_MANIPULATION = "EARNINGS_MANIPULATION"
    VOLUME_SPIKE = "VOLUME_SPIKE"
    FREQUENT_REMARKS = "FREQUENT_REMARKS"


@dataclass
class WarningSign:
    description: str
    severity: RedFlagSeverity
    triggered: bool
    evidence: str = ""


@dataclass
class RedFlag:
    flag_number: int
    category: RedFlagCategory
    title: str
    description: str
    severity: RedFlagSeverity
    triggered: bool
    warning_signs: list[WarningSign] = field(default_factory=list)
    action_required: str = ""
    example: str = ""

    def to_dict(self) -> dict:
        return {
            "flag_number": self.flag_number,
            "category": self.category.value,
            "title": self.title,
            "description": self.description,
            "severity": self.severity.value,
            "triggered": self.triggered,
            "warning_signs": [
                {
                    "description": ws.description,
                    "severity": ws.severity.value,
                    "triggered": ws.triggered,
                    "evidence": ws.evidence,
                }
                for ws in self.warning_signs
            ],
            "action_required": self.action_required,
        }


@dataclass
class RedFlagReport:
    position_id: str
    assessment_date: str
    total_flags: int
    triggered_flags: int
    max_severity: str
    flags: list[RedFlag] = field(default_factory=list)
    overall_action: str = ""

    def to_dict(self) -> dict:
        return {
            "position_id": self.position_id,
            "assessment_date": self.assessment_date,
            "total_flags": self.total_flags,
            "triggered_flags": self.triggered_flags,
            "max_severity": self.max_severity,
            "flags": [f.to_dict() for f in self.flags],
            "overall_action": self.overall_action,
        }


# ── Pydantic-based red flag detection (new interface) ────────────

# Threshold constants
_OVERPAYMENT_THRESHOLD_PCT = Decimal("0.20")  # 20% threshold for client overpayment
_OVERPAYMENT_SEVERE_PCT = Decimal("0.30")  # 30% triggers SEVERE
_PERIOD_END_DAYS = 5  # Last 5 days of quarter considered "period end"
_REMARK_THRESHOLD = 3  # More than 3 re-marks in 30 days is a red flag


def _check_client_overpayment(
    position: PositionInput,
    transaction_price: Decimal,
    fair_value: Decimal,
) -> PydanticRedFlag:
    """Red Flag 1: Client overpaid >20%.

    The most critical red flag. If a client pays significantly more
    than fair value, it suggests the bank may have taken advantage
    of information asymmetry.

    Severity:
      - >30%: SEVERE (mandatory escalation)
      - >20%: HIGH
      - >10%: MEDIUM (informational warning)
      - <=10%: not triggered
    """
    if fair_value == 0:
        return PydanticRedFlag(
            flag_id="RF001",
            flag_name="Client Overpayment",
            severity=PydanticRedFlagSeverity.HIGH,
            description="Cannot assess overpayment: fair value is zero",
            triggered=True,
            threshold=f">{float(_OVERPAYMENT_THRESHOLD_PCT * 100):.0f}%",
            actual_value="FV=0 (indeterminate)",
        )

    overpayment = transaction_price - fair_value
    overpayment_pct = overpayment / abs(fair_value)

    if overpayment_pct > _OVERPAYMENT_SEVERE_PCT:
        return PydanticRedFlag(
            flag_id="RF001",
            flag_name="Client Overpayment",
            severity=PydanticRedFlagSeverity.SEVERE,
            description=(
                f"Client overpaid by {float(overpayment_pct * 100):.1f}% "
                f"(${float(overpayment):,.0f}). Exceeds 30% SEVERE threshold. "
                f"Transaction price ${float(transaction_price):,.0f} vs "
                f"Fair value ${float(fair_value):,.0f}."
            ),
            triggered=True,
            details={
                "overpayment_amount": float(overpayment),
                "overpayment_pct": float(overpayment_pct * 100),
                "transaction_price": float(transaction_price),
                "fair_value": float(fair_value),
            },
            threshold=f">{float(_OVERPAYMENT_SEVERE_PCT * 100):.0f}%",
            actual_value=f"{float(overpayment_pct * 100):.1f}%",
        )

    if overpayment_pct > _OVERPAYMENT_THRESHOLD_PCT:
        return PydanticRedFlag(
            flag_id="RF001",
            flag_name="Client Overpayment",
            severity=PydanticRedFlagSeverity.HIGH,
            description=(
                f"Client overpaid by {float(overpayment_pct * 100):.1f}% "
                f"(${float(overpayment):,.0f}). Exceeds 20% threshold. "
                f"Transaction price ${float(transaction_price):,.0f} vs "
                f"Fair value ${float(fair_value):,.0f}."
            ),
            triggered=True,
            details={
                "overpayment_amount": float(overpayment),
                "overpayment_pct": float(overpayment_pct * 100),
                "transaction_price": float(transaction_price),
                "fair_value": float(fair_value),
            },
            threshold=f">{float(_OVERPAYMENT_THRESHOLD_PCT * 100):.0f}%",
            actual_value=f"{float(overpayment_pct * 100):.1f}%",
        )

    if overpayment_pct > Decimal("0.10"):
        return PydanticRedFlag(
            flag_id="RF001",
            flag_name="Client Overpayment",
            severity=PydanticRedFlagSeverity.MEDIUM,
            description=(
                f"Client overpaid by {float(overpayment_pct * 100):.1f}% "
                f"(${float(overpayment):,.0f}). Below 20% threshold but "
                f"exceeds 10% warning level."
            ),
            triggered=True,
            details={
                "overpayment_amount": float(overpayment),
                "overpayment_pct": float(overpayment_pct * 100),
            },
            threshold=f">{float(_OVERPAYMENT_THRESHOLD_PCT * 100):.0f}%",
            actual_value=f"{float(overpayment_pct * 100):.1f}%",
        )

    return PydanticRedFlag(
        flag_id="RF001",
        flag_name="Client Overpayment",
        severity=PydanticRedFlagSeverity.LOW,
        description=(
            f"Overpayment {float(overpayment_pct * 100):.1f}% is within "
            f"acceptable range (<10%)."
        ),
        triggered=False,
        threshold=f">{float(_OVERPAYMENT_THRESHOLD_PCT * 100):.0f}%",
        actual_value=f"{float(overpayment_pct * 100):.1f}%",
    )


def _check_no_observable_market(
    position: PositionInput,
) -> PydanticRedFlag:
    """Red Flag 2: No observable market (Level 3).

    Level 3 instruments have no observable market prices, making
    fair value determination subjective. This creates opportunity
    for mark manipulation.
    """
    if position.classification == "Level3":
        return PydanticRedFlag(
            flag_id="RF002",
            flag_name="No Observable Market",
            severity=PydanticRedFlagSeverity.HIGH,
            description=(
                f"Position classified as Level 3 — no observable market inputs. "
                f"Fair value relies on unobservable assumptions and internal models. "
                f"Product type: {position.product_type or 'Unknown'}."
            ),
            triggered=True,
            details={
                "classification": position.classification,
                "product_type": position.product_type,
                "asset_class": position.asset_class,
            },
            threshold="Level 1 or Level 2",
            actual_value="Level 3",
        )

    return PydanticRedFlag(
        flag_id="RF002",
        flag_name="No Observable Market",
        severity=PydanticRedFlagSeverity.LOW,
        description=f"Position is {position.classification} — observable market data available.",
        triggered=False,
        threshold="Level 1 or Level 2",
        actual_value=position.classification,
    )


def _check_information_advantage(
    position: PositionInput,
    transaction_price: Decimal,
    fair_value: Decimal,
) -> PydanticRedFlag:
    """Red Flag 3: Bank has information advantage.

    Detects situations where the bank may have superior information
    compared to the client. Indicators:
      - Large Day 1 P&L on complex, illiquid products
      - Combination of Level 3 + significant price discrepancy
    """
    day1_pnl = transaction_price - fair_value
    pnl_pct = abs(day1_pnl / fair_value) if fair_value != 0 else Decimal(0)

    is_complex = position.product_type in {
        "FX_Barrier", "Exotic_Option", "Structured_Note",
        "CLO", "CDO", "Swaption", "Variance_Swap",
        "Autocallable", "Accumulator", "TRF",
        "Barrier", "Exotic", "CLN", "PRDC", "Cliquet",
    }
    is_level3 = position.classification == "Level3"

    if is_complex and is_level3 and pnl_pct > Decimal("0.10"):
        return PydanticRedFlag(
            flag_id="RF003",
            flag_name="Information Advantage",
            severity=PydanticRedFlagSeverity.HIGH,
            description=(
                f"Bank likely has information advantage: complex {position.product_type} "
                f"product, Level 3 classification, with {float(pnl_pct * 100):.1f}% "
                f"price discrepancy. Day 1 P&L = ${float(day1_pnl):,.0f}."
            ),
            triggered=True,
            details={
                "is_complex": True,
                "is_level3": True,
                "day1_pnl": float(day1_pnl),
                "pnl_pct": float(pnl_pct * 100),
                "product_type": position.product_type,
            },
            threshold="Complex + Level 3 + >10% discrepancy",
            actual_value=f"{position.product_type}, {position.classification}, {float(pnl_pct * 100):.1f}%",
        )

    if is_complex and pnl_pct > Decimal("0.15"):
        return PydanticRedFlag(
            flag_id="RF003",
            flag_name="Information Advantage",
            severity=PydanticRedFlagSeverity.MEDIUM,
            description=(
                f"Potential information advantage: complex product with "
                f"{float(pnl_pct * 100):.1f}% price discrepancy."
            ),
            triggered=True,
            details={
                "is_complex": True,
                "is_level3": is_level3,
                "pnl_pct": float(pnl_pct * 100),
            },
            threshold="Complex + >15% discrepancy",
            actual_value=f"{float(pnl_pct * 100):.1f}%",
        )

    return PydanticRedFlag(
        flag_id="RF003",
        flag_name="Information Advantage",
        severity=PydanticRedFlagSeverity.LOW,
        description="No information advantage indicators detected.",
        triggered=False,
        threshold="Complex + Level 3 + >10% discrepancy",
        actual_value=f"{float(pnl_pct * 100):.1f}% discrepancy",
    )


def _check_earnings_manipulation(
    position: PositionInput,
    day1_pnl: Decimal,
) -> PydanticRedFlag:
    """Red Flag 4: Earnings manipulation risk.

    Detects patterns consistent with earnings management:
      - Large Day 1 P&L recognized immediately (Level 1/2) near quarter-end
      - Deferred Day 1 P&L on Level 3 where deferral benefits current quarter
    """
    abs_pnl = abs(day1_pnl)
    notional = position.notional or Decimal(0)
    pnl_notional_pct = (abs_pnl / notional) if notional > 0 else Decimal(0)

    quarter_end_proximity = False
    if position.trade_date:
        trade_month = position.trade_date.month
        is_quarter_end_month = trade_month in (3, 6, 9, 12)
        is_late_in_month = position.trade_date.day >= 25
        quarter_end_proximity = is_quarter_end_month and is_late_in_month

    if quarter_end_proximity and abs_pnl > Decimal("50000"):
        severity = PydanticRedFlagSeverity.HIGH if abs_pnl > Decimal("100000") else PydanticRedFlagSeverity.MEDIUM
        return PydanticRedFlag(
            flag_id="RF004",
            flag_name="Earnings Manipulation Risk",
            severity=severity,
            description=(
                f"Large Day 1 P&L of ${float(day1_pnl):,.0f} recognized near quarter-end. "
                f"Trade date {position.trade_date} is within reporting period close. "
                f"P&L is {float(pnl_notional_pct * 100):.2f}% of notional."
            ),
            triggered=True,
            details={
                "day1_pnl": float(day1_pnl),
                "trade_date": str(position.trade_date),
                "quarter_end_proximity": True,
                "pnl_notional_pct": float(pnl_notional_pct * 100),
            },
            threshold="Day 1 P&L > $50k near quarter-end",
            actual_value=f"${float(abs_pnl):,.0f}",
        )

    if abs_pnl > Decimal("200000"):
        return PydanticRedFlag(
            flag_id="RF004",
            flag_name="Earnings Manipulation Risk",
            severity=PydanticRedFlagSeverity.MEDIUM,
            description=(
                f"Day 1 P&L of ${float(day1_pnl):,.0f} is unusually large. "
                f"Not near quarter-end but warrants review."
            ),
            triggered=True,
            details={
                "day1_pnl": float(day1_pnl),
                "quarter_end_proximity": False,
            },
            threshold="Day 1 P&L > $200k",
            actual_value=f"${float(abs_pnl):,.0f}",
        )

    return PydanticRedFlag(
        flag_id="RF004",
        flag_name="Earnings Manipulation Risk",
        severity=PydanticRedFlagSeverity.LOW,
        description="No earnings manipulation indicators detected.",
        triggered=False,
        threshold="Day 1 P&L > $50k near quarter-end or > $200k anytime",
        actual_value=f"${float(abs_pnl):,.0f}",
    )


def _check_volume_spike(
    position: PositionInput,
    recent_trade_count: int | None = None,
    average_trade_count: int | None = None,
) -> PydanticRedFlag:
    """Red Flag 5: Volume spike at period end.

    Detects unusual trading volume near reporting period ends.
    """
    is_period_end = False
    if position.trade_date:
        trade_month = position.trade_date.month
        is_quarter_end_month = trade_month in (3, 6, 9, 12)
        is_late_in_month = position.trade_date.day >= (31 - _PERIOD_END_DAYS)
        is_period_end = is_quarter_end_month and is_late_in_month

    if recent_trade_count is not None and average_trade_count is not None and average_trade_count > 0:
        volume_ratio = Decimal(recent_trade_count) / Decimal(average_trade_count)
        if volume_ratio > Decimal("2.0") and is_period_end:
            return PydanticRedFlag(
                flag_id="RF005",
                flag_name="Volume Spike at Period End",
                severity=PydanticRedFlagSeverity.HIGH,
                description=(
                    f"Trading volume is {float(volume_ratio):.1f}x the average "
                    f"({recent_trade_count} vs avg {average_trade_count}) "
                    f"near quarter-end ({position.trade_date}). "
                    f"Potential window dressing or P&L padding."
                ),
                triggered=True,
                details={
                    "recent_trade_count": recent_trade_count,
                    "average_trade_count": average_trade_count,
                    "volume_ratio": float(volume_ratio),
                    "is_period_end": True,
                },
                threshold="Volume > 2x average at period end",
                actual_value=f"{float(volume_ratio):.1f}x average",
            )

        if volume_ratio > Decimal("3.0"):
            return PydanticRedFlag(
                flag_id="RF005",
                flag_name="Volume Spike at Period End",
                severity=PydanticRedFlagSeverity.MEDIUM,
                description=(
                    f"Trading volume is {float(volume_ratio):.1f}x the average. "
                    f"Not at period end but significant spike."
                ),
                triggered=True,
                details={
                    "recent_trade_count": recent_trade_count,
                    "average_trade_count": average_trade_count,
                    "volume_ratio": float(volume_ratio),
                    "is_period_end": is_period_end,
                },
                threshold="Volume > 3x average anytime",
                actual_value=f"{float(volume_ratio):.1f}x average",
            )

    elif is_period_end:
        return PydanticRedFlag(
            flag_id="RF005",
            flag_name="Volume Spike at Period End",
            severity=PydanticRedFlagSeverity.MEDIUM,
            description=(
                f"Trade executed near quarter-end ({position.trade_date}). "
                f"Volume data not available for comparison. "
                f"Manual review recommended."
            ),
            triggered=True,
            details={
                "trade_date": str(position.trade_date),
                "is_period_end": True,
                "volume_data_available": False,
            },
            threshold="Trade at period end (volume data unavailable)",
            actual_value=f"Period end: {position.trade_date}",
        )

    return PydanticRedFlag(
        flag_id="RF005",
        flag_name="Volume Spike at Period End",
        severity=PydanticRedFlagSeverity.LOW,
        description="No unusual volume patterns detected.",
        triggered=False,
        threshold="Volume > 2x average at period end",
        actual_value="Normal volume" if not is_period_end else "Period end, no volume data",
    )


def _check_frequent_remarks(
    position: PositionInput,
    remark_count: int | None = None,
    remark_period_days: int = 30,
) -> PydanticRedFlag:
    """Red Flag 6: Frequent re-marks.

    Detects positions that have been re-marked multiple times in a short period.
    """
    if remark_count is not None and remark_count > _REMARK_THRESHOLD:
        severity = (
            PydanticRedFlagSeverity.HIGH
            if remark_count > _REMARK_THRESHOLD * 2
            else PydanticRedFlagSeverity.MEDIUM
        )
        return PydanticRedFlag(
            flag_id="RF006",
            flag_name="Frequent Re-marks",
            severity=severity,
            description=(
                f"Position has been re-marked {remark_count} times in the last "
                f"{remark_period_days} days. Threshold is {_REMARK_THRESHOLD}. "
                f"Frequent valuation changes may indicate uncertainty or manipulation."
            ),
            triggered=True,
            details={
                "remark_count": remark_count,
                "remark_period_days": remark_period_days,
                "threshold": _REMARK_THRESHOLD,
            },
            threshold=f">{_REMARK_THRESHOLD} re-marks in {remark_period_days} days",
            actual_value=f"{remark_count} re-marks",
        )

    return PydanticRedFlag(
        flag_id="RF006",
        flag_name="Frequent Re-marks",
        severity=PydanticRedFlagSeverity.LOW,
        description=(
            f"Re-mark count ({remark_count or 0}) is within acceptable range "
            f"(<={_REMARK_THRESHOLD} in {remark_period_days} days)."
        ),
        triggered=False,
        threshold=f">{_REMARK_THRESHOLD} re-marks in {remark_period_days} days",
        actual_value=f"{remark_count or 0} re-marks",
    )


def detect_red_flags(
    position: PositionInput,
    transaction_price: Decimal | None = None,
    fair_value: Decimal | None = None,
    recent_trade_count: int | None = None,
    average_trade_count: int | None = None,
    remark_count: int | None = None,
    remark_period_days: int = 30,
) -> PydanticRedFlagReport:
    """Run all 6 red flag checks and produce a consolidated Pydantic-based report.

    This is the main entry point for red flag detection using the Pydantic schema interface.
    All checks are run regardless of whether data is available; missing data results
    in the check returning untriggered with an informational message.
    """
    txn_price = transaction_price or (position.transaction_price or Decimal(0))
    fv = fair_value or (position.vc_fair_value or Decimal(0))
    day1_pnl = txn_price - fv

    flags: list[PydanticRedFlag] = [
        _check_client_overpayment(position, txn_price, fv),
        _check_no_observable_market(position),
        _check_information_advantage(position, txn_price, fv),
        _check_earnings_manipulation(position, day1_pnl),
        _check_volume_spike(position, recent_trade_count, average_trade_count),
        _check_frequent_remarks(position, remark_count, remark_period_days),
    ]

    triggered_flags = [f for f in flags if f.triggered]
    total_triggered = len(triggered_flags)

    severity_order = {
        PydanticRedFlagSeverity.SEVERE: 4,
        PydanticRedFlagSeverity.HIGH: 3,
        PydanticRedFlagSeverity.MEDIUM: 2,
        PydanticRedFlagSeverity.LOW: 1,
    }

    max_severity = None
    if triggered_flags:
        max_severity = max(triggered_flags, key=lambda f: severity_order.get(f.severity, 0)).severity

    requires_escalation = any(f.severity == PydanticRedFlagSeverity.SEVERE for f in triggered_flags)
    escalation_reason = None
    if requires_escalation:
        severe_flags = [f for f in triggered_flags if f.severity == PydanticRedFlagSeverity.SEVERE]
        escalation_reason = (
            f"SEVERE flag(s) triggered: {', '.join(f.flag_name for f in severe_flags)}. "
            f"Mandatory escalation to senior management required."
        )

    report = PydanticRedFlagReport(
        position_id=position.position_id,
        trade_id=position.trade_id,
        total_flags_triggered=total_triggered,
        max_severity=max_severity,
        flags=flags,
        assessment_date=date.today(),
        requires_escalation=requires_escalation,
        escalation_reason=escalation_reason,
    )

    log.info(
        "red_flags_assessed",
        position_id=position.position_id,
        total_triggered=total_triggered,
        max_severity=max_severity.value if max_severity else "NONE",
        requires_escalation=requires_escalation,
    )

    return report


# ── Legacy dataclass-based detector ──────────────────────────────

class Day1RedFlagDetector:
    """Detect Day 1 P&L red flags for earnings manipulation prevention.

    This is the original dataclass-based interface. For new code, prefer
    the detect_red_flags() function which uses Pydantic schemas.
    """

    # Thresholds
    OVERPAYMENT_SEVERE_PCT = 20.0
    OVERPAYMENT_HIGH_PCT = 10.0
    OVERPAYMENT_MEDIUM_PCT = 5.0
    MIN_DEALER_QUOTES = 3
    PERIOD_END_WINDOW_DAYS = 5
    REMARK_THRESHOLD = 3  # Number of remarks to trigger

    def assess_position(
        self,
        position_id: str,
        transaction_price: float,
        fair_value: float,
        fair_value_level: str,
        product_type: str,
        num_dealer_quotes: int = 0,
        has_bloomberg_pricing: bool = False,
        desk_has_proprietary_data: bool = False,
        client_type: str = "institutional",
        trade_date: Optional[date] = None,
        remark_count: int = 0,
        period_end_trade_count: int = 0,
        model_comparison_values: Optional[list[float]] = None,
    ) -> RedFlagReport:
        """Run all 6 red flag checks against a position.

        Args:
            position_id: Position identifier.
            transaction_price: Price paid by client.
            fair_value: VC fair value estimate.
            fair_value_level: L1, L2, or L3.
            product_type: Product classification.
            num_dealer_quotes: Number of independent quotes.
            has_bloomberg_pricing: Whether Bloomberg prices the product.
            desk_has_proprietary_data: Whether desk has info client can't access.
            client_type: institutional, corporate, retail, municipality.
            trade_date: When the trade was executed.
            remark_count: Number of times position has been re-marked.
            period_end_trade_count: Trades in last 5 days of period.
            model_comparison_values: List of model valuations for comparison.

        Returns:
            RedFlagReport with all flag assessments.
        """
        flags = []

        # Red Flag 1: Client Overpaid
        flags.append(self._check_client_overpaid(
            position_id, transaction_price, fair_value, client_type, product_type
        ))

        # Red Flag 2: No Observable Market
        flags.append(self._check_no_observable_market(
            position_id, fair_value_level, num_dealer_quotes,
            has_bloomberg_pricing, product_type
        ))

        # Red Flag 3: Information Advantage
        flags.append(self._check_information_advantage(
            position_id, desk_has_proprietary_data, fair_value_level,
            client_type, model_comparison_values
        ))

        # Red Flag 4: Earnings Manipulation
        flags.append(self._check_earnings_manipulation(
            position_id, transaction_price, fair_value, fair_value_level,
            trade_date, remark_count
        ))

        # Red Flag 5: Volume Spike at Period End
        flags.append(self._check_volume_spike(
            position_id, trade_date, period_end_trade_count
        ))

        # Red Flag 6: Frequent Re-marks
        flags.append(self._check_frequent_remarks(
            position_id, remark_count
        ))

        triggered = [f for f in flags if f.triggered]
        triggered_count = len(triggered)

        # Determine max severity
        severity_order = [
            RedFlagSeverity.SEVERE,
            RedFlagSeverity.HIGH,
            RedFlagSeverity.MEDIUM,
            RedFlagSeverity.LOW,
        ]
        max_severity = RedFlagSeverity.LOW
        for sev in severity_order:
            if any(f.severity == sev for f in triggered):
                max_severity = sev
                break

        # Determine overall action
        if max_severity == RedFlagSeverity.SEVERE:
            overall_action = "DEFER Day 1 P&L immediately. Escalate to Compliance and VC Committee. Full investigation required."
        elif max_severity == RedFlagSeverity.HIGH:
            overall_action = "DEFER Day 1 P&L. Investigate within 24 hours. Notify VC Manager."
        elif max_severity == RedFlagSeverity.MEDIUM:
            overall_action = "Flag for review. Enhanced monitoring. Document rationale if P&L recognized."
        else:
            overall_action = "Standard processing. No additional action required."

        report = RedFlagReport(
            position_id=position_id,
            assessment_date=datetime.utcnow().isoformat(),
            total_flags=len(flags),
            triggered_flags=triggered_count,
            max_severity=max_severity.value,
            flags=flags,
            overall_action=overall_action,
        )

        log.info(
            "red_flag_assessment_complete",
            position_id=position_id,
            triggered_flags=triggered_count,
            max_severity=max_severity.value,
        )

        return report

    def _check_client_overpaid(
        self,
        position_id: str,
        transaction_price: float,
        fair_value: float,
        client_type: str,
        product_type: str,
    ) -> RedFlag:
        """Red Flag 1: Client overpaid for derivative."""
        overpayment_pct = 0.0
        if fair_value > 0:
            overpayment_pct = ((transaction_price - fair_value) / fair_value) * 100

        warning_signs = []

        # Check premium > 20% above consensus
        ws_severe = WarningSign(
            description="Premium >20% above market consensus",
            severity=RedFlagSeverity.SEVERE,
            triggered=overpayment_pct > self.OVERPAYMENT_SEVERE_PCT,
            evidence=f"Overpayment: {overpayment_pct:.1f}%",
        )
        warning_signs.append(ws_severe)

        # Check unsophisticated client
        unsophisticated = client_type in ["retail", "municipality", "small_corporate"]
        ws_client = WarningSign(
            description="Unsophisticated client (small corporate, municipality)",
            severity=RedFlagSeverity.HIGH,
            triggered=unsophisticated,
            evidence=f"Client type: {client_type}",
        )
        warning_signs.append(ws_client)

        # Check complex structure
        complex_products = ["Barrier", "Exotic", "CLN", "PRDC", "Cliquet", "Autocallable"]
        is_complex = any(cp.lower() in product_type.lower() for cp in complex_products)
        ws_complex = WarningSign(
            description="Complex exotic structure client may not understand",
            severity=RedFlagSeverity.HIGH,
            triggered=is_complex and unsophisticated,
            evidence=f"Product: {product_type}, Client: {client_type}",
        )
        warning_signs.append(ws_complex)

        # Determine overall flag status
        triggered = overpayment_pct > self.OVERPAYMENT_MEDIUM_PCT
        if overpayment_pct > self.OVERPAYMENT_SEVERE_PCT:
            severity = RedFlagSeverity.SEVERE
        elif overpayment_pct > self.OVERPAYMENT_HIGH_PCT:
            severity = RedFlagSeverity.HIGH
        elif overpayment_pct > self.OVERPAYMENT_MEDIUM_PCT:
            severity = RedFlagSeverity.MEDIUM
        else:
            severity = RedFlagSeverity.LOW

        return RedFlag(
            flag_number=1,
            category=RedFlagCategory.CLIENT_OVERPAID,
            title="Client Overpaid for Derivative",
            description="Client paid significantly more than fair market value",
            severity=severity,
            triggered=triggered,
            warning_signs=warning_signs,
            action_required="DEFER Day 1 P&L; Investigate mis-selling; Report to compliance" if triggered else "No action",
        )

    def _check_no_observable_market(
        self,
        position_id: str,
        fair_value_level: str,
        num_dealer_quotes: int,
        has_bloomberg_pricing: bool,
        product_type: str,
    ) -> RedFlag:
        """Red Flag 2: No observable market for product."""
        warning_signs = []

        # Zero dealer quotes
        ws_zero_quotes = WarningSign(
            description="Zero dealer quotes available (too exotic)",
            severity=RedFlagSeverity.SEVERE,
            triggered=num_dealer_quotes == 0,
            evidence=f"Dealer quotes: {num_dealer_quotes}",
        )
        warning_signs.append(ws_zero_quotes)

        # Only 1-2 dealers quote
        ws_few_quotes = WarningSign(
            description="Only 1-2 dealers quote (insufficient price discovery)",
            severity=RedFlagSeverity.HIGH,
            triggered=0 < num_dealer_quotes < 3,
            evidence=f"Dealer quotes: {num_dealer_quotes}",
        )
        warning_signs.append(ws_few_quotes)

        # No Bloomberg pricing
        ws_no_bbg = WarningSign(
            description="No Bloomberg OVML pricing available",
            severity=RedFlagSeverity.MEDIUM,
            triggered=not has_bloomberg_pricing,
            evidence=f"Bloomberg available: {has_bloomberg_pricing}",
        )
        warning_signs.append(ws_no_bbg)

        # Requires proprietary vol surface
        is_exotic = any(
            x in product_type.lower()
            for x in ["barrier", "exotic", "cliquet", "autocallable"]
        )
        ws_proprietary = WarningSign(
            description="Requires proprietary volatility surface",
            severity=RedFlagSeverity.HIGH,
            triggered=is_exotic and fair_value_level == "L3",
            evidence=f"Product: {product_type}, Level: {fair_value_level}",
        )
        warning_signs.append(ws_proprietary)

        # Determine if triggered
        is_l3 = fair_value_level in ["L3", "Level 3"]
        triggered = is_l3 and (num_dealer_quotes < self.MIN_DEALER_QUOTES or not has_bloomberg_pricing)

        if num_dealer_quotes == 0 and is_l3:
            severity = RedFlagSeverity.SEVERE
        elif is_l3:
            severity = RedFlagSeverity.HIGH
        elif num_dealer_quotes < 3:
            severity = RedFlagSeverity.MEDIUM
        else:
            severity = RedFlagSeverity.LOW

        return RedFlag(
            flag_number=2,
            category=RedFlagCategory.NO_OBSERVABLE_MARKET,
            title="No Observable Market for Product",
            description="Unable to obtain independent pricing from active market",
            severity=severity,
            triggered=triggered,
            warning_signs=warning_signs,
            action_required="Level 3 classification; DEFER Day 1 P&L; Enhanced model validation" if triggered else "No action",
        )

    def _check_information_advantage(
        self,
        position_id: str,
        desk_has_proprietary_data: bool,
        fair_value_level: str,
        client_type: str,
        model_comparison_values: Optional[list[float]] = None,
    ) -> RedFlag:
        """Red Flag 3: Bank has information advantage."""
        warning_signs = []

        # Proprietary data
        ws_proprietary = WarningSign(
            description="Bank has proprietary data client cannot access",
            severity=RedFlagSeverity.SEVERE,
            triggered=desk_has_proprietary_data,
            evidence=f"Proprietary data: {desk_has_proprietary_data}",
        )
        warning_signs.append(ws_proprietary)

        # Client relies solely on bank
        client_dependent = client_type in ["retail", "municipality", "small_corporate"]
        ws_client_dependent = WarningSign(
            description="Client relies solely on bank for valuation",
            severity=RedFlagSeverity.HIGH,
            triggered=client_dependent,
            evidence=f"Client type: {client_type}",
        )
        warning_signs.append(ws_client_dependent)

        # Model-based pricing gives bank advantage
        is_l3 = fair_value_level in ["L3", "Level 3"]
        ws_model = WarningSign(
            description="Product linked to internal model client cannot verify",
            severity=RedFlagSeverity.HIGH,
            triggered=is_l3,
            evidence=f"Level: {fair_value_level}",
        )
        warning_signs.append(ws_model)

        # Wide model spread suggests information asymmetry
        wide_spread = False
        if model_comparison_values and len(model_comparison_values) >= 2:
            spread = max(model_comparison_values) - min(model_comparison_values)
            avg = sum(model_comparison_values) / len(model_comparison_values)
            if avg > 0:
                spread_pct = (spread / avg) * 100
                wide_spread = spread_pct > 10
        ws_spread = WarningSign(
            description="Correlation assumptions favor bank (hard to verify)",
            severity=RedFlagSeverity.HIGH,
            triggered=wide_spread,
            evidence="Model spread >10% between methods" if wide_spread else "Model spread within tolerance",
        )
        warning_signs.append(ws_spread)

        triggered = desk_has_proprietary_data or (is_l3 and client_dependent)
        severity = RedFlagSeverity.SEVERE if desk_has_proprietary_data else (
            RedFlagSeverity.HIGH if triggered else RedFlagSeverity.LOW
        )

        return RedFlag(
            flag_number=3,
            category=RedFlagCategory.INFORMATION_ADVANTAGE,
            title="Bank Has Information Advantage",
            description="Asymmetric information - bank knows more than client",
            severity=severity,
            triggered=triggered,
            warning_signs=warning_signs,
            action_required="DEFER Day 1 P&L; Require client obtain independent valuation; Suitability review" if triggered else "No action",
        )

    def _check_earnings_manipulation(
        self,
        position_id: str,
        transaction_price: float,
        fair_value: float,
        fair_value_level: str,
        trade_date: Optional[date] = None,
        remark_count: int = 0,
    ) -> RedFlag:
        """Red Flag 4: Earnings manipulation risk."""
        warning_signs = []

        # Large Day 1 gain
        day1_gain = transaction_price - fair_value if fair_value > 0 else 0
        day1_pct = (day1_gain / fair_value * 100) if fair_value > 0 else 0

        ws_large_gain = WarningSign(
            description="Large Day 1 gain recognized immediately",
            severity=RedFlagSeverity.SEVERE,
            triggered=day1_pct > 20 and fair_value_level not in ["L3", "Level 3"],
            evidence=f"Day 1 P&L: ${day1_gain:,.0f} ({day1_pct:.1f}%)",
        )
        warning_signs.append(ws_large_gain)

        # Quarter-end timing
        near_quarter_end = False
        if trade_date:
            month = trade_date.month
            quarter_end_months = [3, 6, 9, 12]
            for qe_month in quarter_end_months:
                if month == qe_month and trade_date.day >= 25:
                    near_quarter_end = True
                elif month == qe_month + 1 and trade_date.day <= 5:
                    near_quarter_end = True

        ws_quarter_end = WarningSign(
            description="Trade executed near quarter/year end",
            severity=RedFlagSeverity.HIGH,
            triggered=near_quarter_end and day1_pct > 10,
            evidence=f"Trade date: {trade_date}, Day 1 P&L: {day1_pct:.1f}%",
        )
        warning_signs.append(ws_quarter_end)

        # Frequent remarks suggest gaming
        ws_remarks = WarningSign(
            description="Position repeatedly re-marked (gaming suspicion)",
            severity=RedFlagSeverity.MEDIUM,
            triggered=remark_count >= self.REMARK_THRESHOLD,
            evidence=f"Re-mark count: {remark_count}",
        )
        warning_signs.append(ws_remarks)

        triggered = any(ws.triggered for ws in warning_signs)
        max_sev = max(
            (ws.severity for ws in warning_signs if ws.triggered),
            default=RedFlagSeverity.LOW,
            key=lambda s: [RedFlagSeverity.SEVERE, RedFlagSeverity.HIGH, RedFlagSeverity.MEDIUM, RedFlagSeverity.LOW].index(s),
        )

        return RedFlag(
            flag_number=4,
            category=RedFlagCategory.EARNINGS_MANIPULATION,
            title="Earnings Manipulation Risk",
            description="Desk gaming Day 1 P&L to inflate current period earnings",
            severity=max_sev if triggered else RedFlagSeverity.LOW,
            triggered=triggered,
            warning_signs=warning_signs,
            action_required="DEFER Day 1 P&L; Escalate to Internal Audit; Pattern analysis" if triggered else "No action",
        )

    def _check_volume_spike(
        self,
        position_id: str,
        trade_date: Optional[date] = None,
        period_end_trade_count: int = 0,
    ) -> RedFlag:
        """Red Flag 5: Volume spike at period end."""
        warning_signs = []

        near_period_end = False
        if trade_date:
            # Last 5 days of month
            next_month = trade_date.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            days_to_end = (last_day - trade_date).days
            near_period_end = days_to_end <= self.PERIOD_END_WINDOW_DAYS

        ws_clustering = WarningSign(
            description="Concentration of Day 1 trades near period end",
            severity=RedFlagSeverity.HIGH,
            triggered=near_period_end and period_end_trade_count > 5,
            evidence=f"Period-end trades: {period_end_trade_count}, Days to month-end: {(last_day - trade_date).days if trade_date else 'N/A'}",
        )
        warning_signs.append(ws_clustering)

        ws_spike = WarningSign(
            description="Unusual volume increase vs prior periods",
            severity=RedFlagSeverity.MEDIUM,
            triggered=period_end_trade_count > 10,
            evidence=f"Period-end trade count: {period_end_trade_count}",
        )
        warning_signs.append(ws_spike)

        triggered = any(ws.triggered for ws in warning_signs)

        return RedFlag(
            flag_number=5,
            category=RedFlagCategory.VOLUME_SPIKE,
            title="Volume Spike at Period End",
            description="Clustering of Day 1 P&L trades near reporting dates",
            severity=RedFlagSeverity.HIGH if triggered else RedFlagSeverity.LOW,
            triggered=triggered,
            warning_signs=warning_signs,
            action_required="Pattern analysis; Compare to prior periods; Escalate if recurring" if triggered else "No action",
        )

    def _check_frequent_remarks(
        self,
        position_id: str,
        remark_count: int = 0,
    ) -> RedFlag:
        """Red Flag 6: Frequent re-marks."""
        warning_signs = []

        ws_remarks = WarningSign(
            description=f"Position re-marked {remark_count} times",
            severity=RedFlagSeverity.MEDIUM if remark_count >= 3 else RedFlagSeverity.LOW,
            triggered=remark_count >= self.REMARK_THRESHOLD,
            evidence=f"Re-mark count: {remark_count}, Threshold: {self.REMARK_THRESHOLD}",
        )
        warning_signs.append(ws_remarks)

        ws_pattern = WarningSign(
            description="Re-marks consistently favor desk position",
            severity=RedFlagSeverity.HIGH,
            triggered=remark_count >= 5,
            evidence=f"Excessive re-marks: {remark_count}",
        )
        warning_signs.append(ws_pattern)

        triggered = remark_count >= self.REMARK_THRESHOLD

        return RedFlag(
            flag_number=6,
            category=RedFlagCategory.FREQUENT_REMARKS,
            title="Frequent Re-marks",
            description="Positions repeatedly revalued, potentially to manage P&L",
            severity=RedFlagSeverity.HIGH if remark_count >= 5 else (
                RedFlagSeverity.MEDIUM if triggered else RedFlagSeverity.LOW
            ),
            triggered=triggered,
            warning_signs=warning_signs,
            action_required="Investigate re-mark pattern; Compare desk vs VC trajectory" if triggered else "No action",
        )

    def assess_barrier_option_example(self) -> RedFlagReport:
        """Run red flag assessment for the barrier option from the Excel model.

        This is the EUR/USD Double-No-Touch barrier option:
        - Transaction Price: $425,000
        - Fair Value: $306,000 (72% survival)
        - Day 1 P&L: +$119,000 (38.9% overpayment)
        - Level 3 (unobservable)
        - 3 dealer quotes (JPM, GS, Citi)

        Returns:
            RedFlagReport with assessment.
        """
        return self.assess_position(
            position_id="FX-OPT-001",
            transaction_price=425_000,
            fair_value=306_000,
            fair_value_level="L3",
            product_type="Barrier",
            num_dealer_quotes=3,
            has_bloomberg_pricing=True,
            desk_has_proprietary_data=True,
            client_type="corporate",
            trade_date=date(2025, 1, 5),
            remark_count=0,
            period_end_trade_count=0,
            model_comparison_values=[306_000, 318_000, 295_000, 306_213],
        )

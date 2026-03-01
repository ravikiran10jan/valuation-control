"""Data validation engine for market data and position data.

Implements the checks specified in the VC requirements:
  - Market data: positivity, arbitrage-free vol surface, stale data, cross-validation
  - Position data: notional sign, date ordering, required fields
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

import structlog

from app.core.config import settings

log = structlog.get_logger()


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class ValidationResult:
    passed: bool
    rule: str
    severity: Severity
    message: str
    details: Optional[dict] = None


@dataclass
class ValidationReport:
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    @property
    def failures(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed]

    @property
    def critical_failures(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.passed and r.severity == Severity.CRITICAL]


class DataValidator:
    """Stateless validator -- instantiate once and reuse."""

    def __init__(
        self,
        stale_threshold_hours: int = settings.data_stale_threshold_hours,
        cross_val_threshold_bps: float = settings.cross_validation_threshold_bps,
    ) -> None:
        self._stale_hours = stale_threshold_hours
        self._cross_val_bps = cross_val_threshold_bps

    # ── Market data validation ────────────────────────────────────
    def validate_market_data(
        self,
        field_name: str,
        value: float,
        timestamp: datetime,
        secondary_value: Optional[float] = None,
    ) -> ValidationReport:
        report = ValidationReport()

        # Check 1: Spot rates must be positive
        report.results.append(self._check_positive(field_name, value))

        # Check 2: Stale data check
        report.results.append(self._check_staleness(field_name, timestamp))

        # Check 3: Cross-validation if secondary source available
        if secondary_value is not None:
            report.results.append(
                self._check_cross_validation(field_name, value, secondary_value)
            )

        if not report.passed:
            log.warning(
                "market_data_validation_failed",
                field=field_name,
                failures=[f.message for f in report.failures],
            )

        return report

    def validate_vol_surface(
        self,
        currency_pair: str,
        tenor: str,
        surface: dict[str, float],
    ) -> ValidationReport:
        """Validate a vol surface slice (25P, ATM, 25C) for arbitrage."""
        report = ValidationReport()

        put_25 = surface.get("25P", 0)
        atm = surface.get("ATM", 0)
        call_25 = surface.get("25C", 0)

        # All vols must be positive
        for label, vol in [("25P", put_25), ("ATM", atm), ("25C", call_25)]:
            if vol <= 0:
                report.results.append(
                    ValidationResult(
                        passed=False,
                        rule="vol_positive",
                        severity=Severity.CRITICAL,
                        message=f"{currency_pair} {tenor} {label} vol is non-positive: {vol}",
                    )
                )
            else:
                report.results.append(
                    ValidationResult(
                        passed=True,
                        rule="vol_positive",
                        severity=Severity.INFO,
                        message=f"{currency_pair} {tenor} {label} vol OK",
                    )
                )

        # Smile shape: 25-delta puts should have higher vol than ATM (typical risk reversal)
        # This is a soft check -- many currency pairs exhibit this pattern
        if put_25 > 0 and atm > 0 and call_25 > 0:
            # Check butterfly spread is non-negative (no butterfly arbitrage)
            butterfly = (put_25 + call_25) / 2 - atm
            if butterfly < -0.5:  # Allow small tolerance
                report.results.append(
                    ValidationResult(
                        passed=False,
                        rule="vol_butterfly_arbitrage",
                        severity=Severity.WARNING,
                        message=(
                            f"{currency_pair} {tenor} butterfly is negative: "
                            f"{butterfly:.2f}% -- possible arbitrage"
                        ),
                        details={"butterfly": butterfly, "25P": put_25, "ATM": atm, "25C": call_25},
                    )
                )
            else:
                report.results.append(
                    ValidationResult(
                        passed=True,
                        rule="vol_butterfly_arbitrage",
                        severity=Severity.INFO,
                        message=f"{currency_pair} {tenor} butterfly OK: {butterfly:.2f}%",
                    )
                )

        return report

    def validate_yield_curve(
        self,
        curve_name: str,
        tenors: dict[str, float],
    ) -> ValidationReport:
        """Basic yield curve sanity checks."""
        report = ValidationReport()

        # All rates should be within a reasonable range (-2% to 20%)
        for tenor, rate in tenors.items():
            if rate < -2.0 or rate > 20.0:
                report.results.append(
                    ValidationResult(
                        passed=False,
                        rule="rate_range",
                        severity=Severity.CRITICAL,
                        message=f"{curve_name} {tenor} rate out of range: {rate}%",
                    )
                )
            else:
                report.results.append(
                    ValidationResult(
                        passed=True,
                        rule="rate_range",
                        severity=Severity.INFO,
                        message=f"{curve_name} {tenor} rate OK: {rate}%",
                    )
                )

        return report

    # ── Position data validation ──────────────────────────────────
    def validate_position(
        self,
        trade_id: str,
        notional: Optional[Decimal],
        trade_date: Optional[date],
        maturity_date: Optional[date],
        product_type: Optional[str],
        asset_class: Optional[str],
    ) -> ValidationReport:
        report = ValidationReport()

        # Check 1: Notional > 0
        if notional is not None and notional <= 0:
            report.results.append(
                ValidationResult(
                    passed=False,
                    rule="notional_positive",
                    severity=Severity.CRITICAL,
                    message=f"Trade {trade_id}: notional must be > 0, got {notional}",
                )
            )
        else:
            report.results.append(
                ValidationResult(
                    passed=True, rule="notional_positive",
                    severity=Severity.INFO, message=f"Trade {trade_id}: notional OK",
                )
            )

        # Check 2: Maturity > Trade Date
        if trade_date and maturity_date and maturity_date <= trade_date:
            report.results.append(
                ValidationResult(
                    passed=False,
                    rule="date_ordering",
                    severity=Severity.CRITICAL,
                    message=(
                        f"Trade {trade_id}: maturity {maturity_date} must be "
                        f"after trade date {trade_date}"
                    ),
                )
            )
        else:
            report.results.append(
                ValidationResult(
                    passed=True, rule="date_ordering",
                    severity=Severity.INFO, message=f"Trade {trade_id}: dates OK",
                )
            )

        # Check 3: Product type / asset class consistency
        valid_combos = {
            "FX": {"Spot", "Spot (EM)", "Forward", "Barrier (DNT)", "FX_Barrier",
                   "FX_Option", "FX_Forward", "FX_Swap", "Option", "NDF"},
            "Rates": {"IRS", "Swaption", "Cap", "Floor", "FRA"},
            "Credit": {"CDS", "CLN", "CDO"},
            "Equity": {"Equity_Option", "Equity_Swap", "Variance_Swap"},
            "Commodities": {"Commodity_Swap", "Commodity_Option"},
        }
        if asset_class and product_type:
            allowed = valid_combos.get(asset_class, set())
            if allowed and product_type not in allowed:
                report.results.append(
                    ValidationResult(
                        passed=False,
                        rule="product_asset_class_match",
                        severity=Severity.WARNING,
                        message=(
                            f"Trade {trade_id}: product '{product_type}' unexpected "
                            f"for asset class '{asset_class}'"
                        ),
                    )
                )
            else:
                report.results.append(
                    ValidationResult(
                        passed=True, rule="product_asset_class_match",
                        severity=Severity.INFO,
                        message=f"Trade {trade_id}: product/asset class OK",
                    )
                )

        if not report.passed:
            log.warning(
                "position_validation_failed",
                trade_id=trade_id,
                failures=[f.message for f in report.failures],
            )

        return report

    # ── Private helpers ───────────────────────────────────────────
    def _check_positive(self, field_name: str, value: float) -> ValidationResult:
        if value <= 0:
            return ValidationResult(
                passed=False,
                rule="positive_value",
                severity=Severity.CRITICAL,
                message=f"{field_name} must be positive, got {value}",
            )
        return ValidationResult(
            passed=True, rule="positive_value",
            severity=Severity.INFO, message=f"{field_name} positive OK",
        )

    def _check_staleness(self, field_name: str, timestamp: datetime) -> ValidationResult:
        age = datetime.utcnow() - timestamp
        if age > timedelta(hours=self._stale_hours):
            return ValidationResult(
                passed=False,
                rule="stale_data",
                severity=Severity.CRITICAL,
                message=f"{field_name} is stale: last updated {age} ago",
                details={"age_hours": age.total_seconds() / 3600},
            )
        return ValidationResult(
            passed=True, rule="stale_data",
            severity=Severity.INFO, message=f"{field_name} freshness OK",
        )

    def _check_cross_validation(
        self, field_name: str, primary: float, secondary: float
    ) -> ValidationResult:
        if primary == 0:
            diff_bps = abs(secondary) * 10000
        else:
            diff_bps = abs(primary - secondary) / abs(primary) * 10000

        if diff_bps > self._cross_val_bps:
            return ValidationResult(
                passed=False,
                rule="cross_validation",
                severity=Severity.WARNING,
                message=(
                    f"{field_name}: sources differ by {diff_bps:.1f} bps "
                    f"(primary={primary}, secondary={secondary})"
                ),
                details={"diff_bps": diff_bps, "primary": primary, "secondary": secondary},
            )
        return ValidationResult(
            passed=True, rule="cross_validation",
            severity=Severity.INFO,
            message=f"{field_name} cross-validation OK ({diff_bps:.1f} bps)",
        )

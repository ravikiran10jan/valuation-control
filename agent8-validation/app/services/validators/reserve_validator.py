"""Reserve Validator -- validates FVA, AVA, Model Reserve, and Day 1 PnL calculations.

Cross-checks reserve calculations from agent 5 against the Excel model's
expected values for every reserve component.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.core.config import settings
from app.models.schemas import (
    CategorySummary,
    CheckStatus,
    ValidationCategory,
    ValidationCheck,
    ValidationGap,
)
from app.services.expected_values import (
    EXPECTED_AVA_BARRIER,
    EXPECTED_DAY1_PNL,
    EXPECTED_FVA_BARRIER,
    EXPECTED_MODEL_RESERVES,
    EXPECTED_TOTAL_FVA,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class ReserveValidator:
    """Validates all reserve calculations (FVA, AVA, Model Reserve, Day 1 PnL)."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def validate(self) -> tuple[list[CategorySummary], list[ValidationGap]]:
        """Run all reserve validation checks.

        Returns summaries for FVA, AVA, MODEL_RESERVE, and DAY1_PNL categories,
        plus a combined list of gaps.
        """
        all_gaps: list[ValidationGap] = []

        fva_summary, fva_gaps = await self._validate_fva()
        all_gaps.extend(fva_gaps)

        ava_summary, ava_gaps = await self._validate_ava()
        all_gaps.extend(ava_gaps)

        mr_summary, mr_gaps = await self._validate_model_reserves()
        all_gaps.extend(mr_gaps)

        d1_summary, d1_gaps = await self._validate_day1_pnl()
        all_gaps.extend(d1_gaps)

        return [fva_summary, ava_summary, mr_summary, d1_summary], all_gaps

    # ── FVA Validation ───────────────────────────────────────────

    async def _validate_fva(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Validate FVA calculations for the barrier option and total FVA."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []
        cat = ValidationCategory.FVA
        pid = EXPECTED_FVA_BARRIER["position_id"]

        # Fetch actual FVA from agent 5
        actual = await self._client.get_fva(pid)

        if actual is None:
            checks.append(self._error_check(f"FVA-{pid}-FETCH", cat, pid, "Fetch FVA from agent 5"))
            return self._build_summary(cat, checks), gaps

        # Validate individual FVA fields
        fva_fields = {
            "premium": ("premium_paid", "premium", "transaction_price"),
            "fair_value": ("fair_value_at_inception", "fair_value", "vc_fair_value"),
            "fva_amount": ("fva_amount", "total_fva"),
            "monthly_release": ("monthly_release",),
            "total_months": ("months_to_maturity", "total_months"),
        }

        for field, actual_keys in fva_fields.items():
            expected_val = EXPECTED_FVA_BARRIER[field]
            actual_val = self._extract_value(actual, actual_keys)
            tolerance = 100.0 if field in ("premium", "fair_value", "fva_amount") else 10.0

            check, gap = self._numeric_check(
                check_id=f"FVA-{pid}-{field.upper()}",
                cat=cat,
                description=f"FVA {field} for {pid}",
                expected=expected_val,
                actual=actual_val,
                tolerance=tolerance,
                position_id=pid,
                field_name=f"fva.{field}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        # Validate total FVA across all positions
        agg = await self._client.get_fva_aggregate()
        if agg is not None:
            total_fva_actual = agg.get("total_fva")
            check, gap = self._numeric_check(
                check_id="FVA-TOTAL",
                cat=cat,
                description="Total FVA across all positions",
                expected=EXPECTED_TOTAL_FVA,
                actual=total_fva_actual,
                tolerance=500.0,
                field_name="total_fva",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)
        else:
            checks.append(self._skip_check("FVA-TOTAL", cat, "Total FVA aggregate"))

        return self._build_summary(cat, checks), gaps

    # ── AVA Validation ───────────────────────────────────────────

    async def _validate_ava(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Validate AVA calculations for the barrier option."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []
        cat = ValidationCategory.AVA
        pid = EXPECTED_AVA_BARRIER["position_id"]

        actual = await self._client.get_ava_detailed(pid)
        if actual is None:
            actual = await self._client.get_ava(pid)

        if actual is None:
            checks.append(self._error_check(f"AVA-{pid}-FETCH", cat, pid, "Fetch AVA from agent 5"))
            return self._build_summary(cat, checks), gaps

        # Validate total AVA
        total_ava_actual = actual.get("total_ava")
        check, gap = self._numeric_check(
            check_id=f"AVA-{pid}-TOTAL",
            cat=cat,
            description=f"Total AVA for {pid}",
            expected=EXPECTED_AVA_BARRIER["total_ava"],
            actual=total_ava_actual,
            tolerance=500.0,
            position_id=pid,
            field_name="ava.total",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # Validate each AVA component
        expected_components = EXPECTED_AVA_BARRIER["components"]
        actual_components = actual.get("components", {})

        for comp_name, expected_val in expected_components.items():
            actual_val = actual_components.get(comp_name)
            tolerance = max(50.0, abs(expected_val) * 0.05) if expected_val != 0 else 10.0

            check, gap = self._numeric_check(
                check_id=f"AVA-{pid}-{comp_name.upper()}",
                cat=cat,
                description=f"AVA component '{comp_name}' for {pid}",
                expected=expected_val,
                actual=actual_val,
                tolerance=tolerance,
                position_id=pid,
                field_name=f"ava.components.{comp_name}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        # Validate dealer quotes if available in detailed response
        expected_quotes = EXPECTED_AVA_BARRIER.get("dealer_quotes", {})
        actual_mpu = actual.get("mpu_detail", {})
        actual_quotes_list = actual_mpu.get("dealer_quotes", [])
        actual_quotes_map: dict[str, float] = {}
        for q in actual_quotes_list:
            name = q.get("dealer_name", "")
            val = q.get("value")
            if name and val is not None:
                actual_quotes_map[name] = float(val)

        for dealer, expected_quote in expected_quotes.items():
            actual_quote = actual_quotes_map.get(dealer)
            check, gap = self._numeric_check(
                check_id=f"AVA-{pid}-QUOTE-{dealer.upper()}",
                cat=cat,
                description=f"Dealer quote from {dealer} for {pid}",
                expected=expected_quote,
                actual=actual_quote,
                tolerance=1000.0,
                position_id=pid,
                field_name=f"ava.dealer_quotes.{dealer}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        return self._build_summary(cat, checks), gaps

    # ── Model Reserve Validation ─────────────────────────────────

    async def _validate_model_reserves(
        self,
    ) -> tuple[CategorySummary, list[ValidationGap]]:
        """Validate model reserve for each position."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []
        cat = ValidationCategory.MODEL_RESERVE

        total_expected = EXPECTED_MODEL_RESERVES.get("total", 0)
        total_actual = 0.0
        any_fetched = False

        for pid, expected_data in EXPECTED_MODEL_RESERVES.items():
            if pid == "total":
                continue
            if not isinstance(expected_data, dict):
                continue

            expected_reserve = expected_data["reserve"]
            expected_materiality = expected_data["materiality"]

            actual = await self._client.get_model_reserve(pid)

            if actual is None:
                checks.append(
                    self._skip_check(
                        f"MR-{pid}-RESERVE", cat, f"Model reserve for {pid}"
                    )
                )
                continue

            any_fetched = True
            actual_reserve = actual.get("model_reserve", actual.get("reserve"))
            if actual_reserve is not None:
                total_actual += float(actual_reserve)

            tolerance = max(50.0, abs(expected_reserve) * 0.05) if expected_reserve != 0 else 5.0
            check, gap = self._numeric_check(
                check_id=f"MR-{pid}-RESERVE",
                cat=cat,
                description=f"Model reserve amount for {pid}",
                expected=expected_reserve,
                actual=actual_reserve,
                tolerance=tolerance,
                position_id=pid,
                field_name="model_reserve",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

            # Check materiality classification
            actual_materiality = actual.get("materiality")
            if actual_materiality is not None:
                if str(actual_materiality).upper() == expected_materiality.upper():
                    checks.append(
                        ValidationCheck(
                            check_id=f"MR-{pid}-MATERIALITY",
                            category=cat,
                            description=f"Model reserve materiality for {pid}",
                            status=CheckStatus.PASS,
                            expected_value=expected_materiality,
                            actual_value=actual_materiality,
                            message="Materiality matches",
                            position_id=pid,
                        )
                    )
                else:
                    checks.append(
                        ValidationCheck(
                            check_id=f"MR-{pid}-MATERIALITY",
                            category=cat,
                            description=f"Model reserve materiality for {pid}",
                            status=CheckStatus.FAIL,
                            expected_value=expected_materiality,
                            actual_value=actual_materiality,
                            message=(
                                f"Materiality mismatch: expected {expected_materiality}, "
                                f"got {actual_materiality}"
                            ),
                            position_id=pid,
                        )
                    )
                    gaps.append(
                        ValidationGap(
                            gap_id=f"GAP-MR-{pid}-MATERIALITY",
                            category=cat,
                            severity="MEDIUM",
                            position_id=pid,
                            field_name="materiality",
                            expected_value=expected_materiality,
                            actual_value=actual_materiality,
                            recommendation=(
                                f"Fix materiality for {pid}: "
                                f"expected {expected_materiality}, got {actual_materiality}"
                            ),
                        )
                    )

        # Total model reserve
        if any_fetched:
            check, gap = self._numeric_check(
                check_id="MR-TOTAL",
                cat=cat,
                description="Total model reserve across all positions",
                expected=total_expected,
                actual=total_actual,
                tolerance=500.0,
                field_name="model_reserve.total",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        return self._build_summary(cat, checks), gaps

    # ── Day 1 PnL Validation ────────────────────────────────────

    async def _validate_day1_pnl(
        self,
    ) -> tuple[CategorySummary, list[ValidationGap]]:
        """Validate Day 1 P&L calculation for the barrier option."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []
        cat = ValidationCategory.DAY1_PNL
        pid = EXPECTED_DAY1_PNL["position_id"]

        actual = await self._client.get_day1_pnl(pid)
        if actual is None:
            checks.append(self._error_check(f"D1-{pid}-FETCH", cat, pid, "Fetch Day 1 PnL from agent 5"))
            return self._build_summary(cat, checks), gaps

        # Transaction price
        check, gap = self._numeric_check(
            check_id=f"D1-{pid}-TXN-PRICE",
            cat=cat,
            description=f"Day 1 transaction price for {pid}",
            expected=EXPECTED_DAY1_PNL["transaction_price"],
            actual=actual.get("transaction_price"),
            tolerance=100.0,
            position_id=pid,
            field_name="day1_pnl.transaction_price",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # Fair value
        check, gap = self._numeric_check(
            check_id=f"D1-{pid}-FAIR-VALUE",
            cat=cat,
            description=f"Day 1 fair value for {pid}",
            expected=EXPECTED_DAY1_PNL["fair_value"],
            actual=actual.get("fair_value"),
            tolerance=500.0,
            position_id=pid,
            field_name="day1_pnl.fair_value",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # Day 1 PnL amount
        check, gap = self._numeric_check(
            check_id=f"D1-{pid}-PNL",
            cat=cat,
            description=f"Day 1 P&L amount for {pid}",
            expected=EXPECTED_DAY1_PNL["day1_pnl"],
            actual=actual.get("day1_pnl"),
            tolerance=500.0,
            position_id=pid,
            field_name="day1_pnl.day1_pnl",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # Recognition status
        actual_recognition = actual.get("recognition_status", actual.get("recognition"))
        expected_recognition = EXPECTED_DAY1_PNL["recognition"]
        if actual_recognition is not None:
            if str(actual_recognition).upper() == expected_recognition.upper():
                checks.append(
                    ValidationCheck(
                        check_id=f"D1-{pid}-RECOGNITION",
                        category=cat,
                        description=f"Day 1 P&L recognition status for {pid}",
                        status=CheckStatus.PASS,
                        expected_value=expected_recognition,
                        actual_value=actual_recognition,
                        message="Recognition status matches",
                        position_id=pid,
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id=f"D1-{pid}-RECOGNITION",
                        category=cat,
                        description=f"Day 1 P&L recognition status for {pid}",
                        status=CheckStatus.FAIL,
                        expected_value=expected_recognition,
                        actual_value=actual_recognition,
                        message=f"Recognition mismatch: expected {expected_recognition}, got {actual_recognition}",
                        position_id=pid,
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id=f"GAP-D1-{pid}-RECOGNITION",
                        category=cat,
                        severity="HIGH",
                        position_id=pid,
                        field_name="recognition",
                        expected_value=expected_recognition,
                        actual_value=actual_recognition,
                        recommendation="Day 1 PnL for L3 barrier should be DEFERRED",
                    )
                )
        else:
            checks.append(
                self._skip_check(f"D1-{pid}-RECOGNITION", cat, "Recognition status")
            )

        # Monthly amortization
        check, gap = self._numeric_check(
            check_id=f"D1-{pid}-AMORT-MONTHLY",
            cat=cat,
            description=f"Day 1 monthly amortization for {pid}",
            expected=EXPECTED_DAY1_PNL["amortization_monthly"],
            actual=self._extract_value(
                actual,
                ("amortization_monthly", "monthly_amortization", "amortization_amount"),
            ),
            tolerance=100.0,
            position_id=pid,
            field_name="day1_pnl.amortization_monthly",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # Amortization months
        check, gap = self._numeric_check(
            check_id=f"D1-{pid}-AMORT-MONTHS",
            cat=cat,
            description=f"Day 1 amortization period (months) for {pid}",
            expected=EXPECTED_DAY1_PNL["amortization_months"],
            actual=self._extract_value(
                actual,
                ("amortization_months", "months_to_maturity", "total_periods"),
            ),
            tolerance=1.0,
            position_id=pid,
            field_name="day1_pnl.amortization_months",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # Daily amortization
        check, gap = self._numeric_check(
            check_id=f"D1-{pid}-AMORT-DAILY",
            cat=cat,
            description=f"Day 1 daily amortization for {pid}",
            expected=EXPECTED_DAY1_PNL["amortization_daily"],
            actual=self._extract_value(
                actual,
                ("amortization_daily", "daily_amortization"),
            ),
            tolerance=5.0,
            position_id=pid,
            field_name="day1_pnl.amortization_daily",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        return self._build_summary(cat, checks), gaps

    # ── Shared helpers ───────────────────────────────────────────

    @staticmethod
    def _extract_value(data: dict[str, Any], keys: tuple[str, ...]) -> Any:
        """Try multiple key names and return the first non-None value."""
        if data is None:
            return None
        for key in keys:
            val = data.get(key)
            if val is not None:
                return val
        return None

    @staticmethod
    def _numeric_check(
        check_id: str,
        cat: ValidationCategory,
        description: str,
        expected: Any,
        actual: Any,
        tolerance: float,
        position_id: str | None = None,
        field_name: str = "",
    ) -> tuple[ValidationCheck, ValidationGap | None]:
        """Compare two numeric values and return check + optional gap."""
        if expected is None and actual is None:
            return (
                ValidationCheck(
                    check_id=check_id,
                    category=cat,
                    description=description,
                    status=CheckStatus.SKIP,
                    message="Both expected and actual are None",
                    position_id=position_id,
                ),
                None,
            )

        if actual is None:
            return (
                ValidationCheck(
                    check_id=check_id,
                    category=cat,
                    description=description,
                    status=CheckStatus.SKIP,
                    expected_value=expected,
                    actual_value=None,
                    message="Actual value not available from agent",
                    position_id=position_id,
                ),
                None,
            )

        try:
            exp_f = float(expected)
            act_f = float(actual)
        except (TypeError, ValueError):
            return (
                ValidationCheck(
                    check_id=check_id,
                    category=cat,
                    description=description,
                    status=CheckStatus.ERROR,
                    expected_value=expected,
                    actual_value=actual,
                    message="Cannot convert to numeric for comparison",
                    position_id=position_id,
                ),
                None,
            )

        diff = act_f - exp_f
        abs_diff = abs(diff)

        if abs_diff <= tolerance:
            return (
                ValidationCheck(
                    check_id=check_id,
                    category=cat,
                    description=description,
                    status=CheckStatus.PASS,
                    expected_value=expected,
                    actual_value=actual,
                    difference=round(diff, 4),
                    tolerance=tolerance,
                    message=f"Within tolerance (diff={diff:.4f})",
                    position_id=position_id,
                ),
                None,
            )

        if abs_diff <= tolerance * 2:
            return (
                ValidationCheck(
                    check_id=check_id,
                    category=cat,
                    description=description,
                    status=CheckStatus.WARN,
                    expected_value=expected,
                    actual_value=actual,
                    difference=round(diff, 4),
                    tolerance=tolerance,
                    message=f"Near tolerance boundary (diff={diff:.4f})",
                    position_id=position_id,
                ),
                None,
            )

        gap = ValidationGap(
            gap_id=f"GAP-{check_id}",
            category=cat,
            severity="HIGH" if abs_diff > tolerance * 5 else "MEDIUM",
            position_id=position_id,
            field_name=field_name,
            expected_value=expected,
            actual_value=actual,
            difference=round(diff, 4),
            recommendation=(
                f"Fix {field_name}: expected {expected}, got {actual} (diff={diff:.4f})"
            ),
        )
        return (
            ValidationCheck(
                check_id=check_id,
                category=cat,
                description=description,
                status=CheckStatus.FAIL,
                expected_value=expected,
                actual_value=actual,
                difference=round(diff, 4),
                tolerance=tolerance,
                message=f"Outside tolerance (diff={diff:.4f})",
                position_id=position_id,
            ),
            gap,
        )

    @staticmethod
    def _error_check(
        check_id: str,
        cat: ValidationCategory,
        pid: str,
        description: str,
    ) -> ValidationCheck:
        return ValidationCheck(
            check_id=check_id,
            category=cat,
            description=description,
            status=CheckStatus.ERROR,
            message=f"Could not retrieve data for {pid} from upstream agent",
            position_id=pid,
        )

    @staticmethod
    def _skip_check(
        check_id: str, cat: ValidationCategory, description: str
    ) -> ValidationCheck:
        return ValidationCheck(
            check_id=check_id,
            category=cat,
            description=description,
            status=CheckStatus.SKIP,
            message="Data not available from upstream agent",
        )

    @staticmethod
    def _build_summary(
        cat: ValidationCategory, checks: list[ValidationCheck]
    ) -> CategorySummary:
        summary = CategorySummary(
            category=cat,
            total_checks=len(checks),
            passed=sum(1 for c in checks if c.status == CheckStatus.PASS),
            failed=sum(1 for c in checks if c.status == CheckStatus.FAIL),
            warned=sum(1 for c in checks if c.status == CheckStatus.WARN),
            skipped=sum(1 for c in checks if c.status == CheckStatus.SKIP),
            errors=sum(1 for c in checks if c.status == CheckStatus.ERROR),
            checks=checks,
        )
        summary.compute_accuracy()
        return summary

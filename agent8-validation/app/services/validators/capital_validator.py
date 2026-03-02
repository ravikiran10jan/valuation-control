"""Capital Validator -- validates capital adequacy calculations.

Cross-checks the CET1 capital, RWA components, and regulatory ratios
from agent 6 against the Capital_Adequacy sheet in the Excel model.
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
from app.services.expected_values import EXPECTED_CAPITAL
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class CapitalValidator:
    """Validates capital adequacy calculations against expected values."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def validate(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Run all capital adequacy validation checks."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []

        # Fetch capital adequacy data from agent 6
        actual = await self._client.get_capital_adequacy()

        if actual is None:
            checks.append(
                ValidationCheck(
                    check_id="CAP-FETCH",
                    category=ValidationCategory.CAPITAL,
                    description="Fetch capital adequacy from agent 6",
                    status=CheckStatus.ERROR,
                    message="Could not reach agent 6 for capital data",
                )
            )
            return self._build_summary(checks), gaps

        # Flatten nested response structures
        capital_data = actual.get("capital", actual.get("data", actual))
        if isinstance(capital_data, dict) and "cet1" in capital_data:
            capital_data = capital_data

        # ── CET1 components ──────────────────────────────────────

        cet1_fields = {
            "shareholders_equity": (
                "shareholders_equity", "share_capital", "equity",
            ),
            "retained_earnings": (
                "retained_earnings", "reserves",
            ),
            "aoci": (
                "aoci", "accumulated_oci", "other_comprehensive_income",
            ),
            "goodwill_deduction": (
                "goodwill_deduction", "goodwill", "intangibles_deduction",
            ),
            "dta_deduction": (
                "dta_deduction", "deferred_tax_deduction", "dta",
            ),
            "ava_deduction": (
                "ava_deduction", "ava", "prudent_valuation_adjustment",
            ),
            "other_deductions": (
                "other_deductions", "other_regulatory_deductions",
            ),
            "cet1_capital": (
                "cet1_capital", "cet1", "tier1_capital",
            ),
        }

        for field, actual_keys in cet1_fields.items():
            expected_val = EXPECTED_CAPITAL[field]
            actual_val = self._extract_value(capital_data, actual_keys)

            # Large amounts get proportional tolerance, small ones get absolute
            abs_expected = abs(expected_val) if isinstance(expected_val, (int, float)) else 0
            tolerance = max(1000.0, abs_expected * 0.001)  # 0.1% or $1000

            check, gap = self._numeric_check(
                check_id=f"CAP-CET1-{field.upper()}",
                description=f"CET1 component: {field}",
                expected=expected_val,
                actual=actual_val,
                tolerance=tolerance,
                field_name=f"capital.{field}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        # ── RWA components ───────────────────────────────────────

        rwa_fields = {
            "credit_risk_rwa": (
                "credit_risk_rwa", "credit_rwa",
            ),
            "market_risk_rwa": (
                "market_risk_rwa", "market_rwa",
            ),
            "operational_risk_rwa": (
                "operational_risk_rwa", "operational_rwa", "op_risk_rwa",
            ),
            "total_rwa": (
                "total_rwa", "rwa_total", "risk_weighted_assets",
            ),
        }

        for field, actual_keys in rwa_fields.items():
            expected_val = EXPECTED_CAPITAL[field]
            actual_val = self._extract_value(capital_data, actual_keys)

            abs_expected = abs(expected_val) if isinstance(expected_val, (int, float)) else 0
            tolerance = max(10_000.0, abs_expected * 0.001)

            check, gap = self._numeric_check(
                check_id=f"CAP-RWA-{field.upper()}",
                description=f"RWA component: {field}",
                expected=expected_val,
                actual=actual_val,
                tolerance=tolerance,
                field_name=f"capital.{field}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        # ── RWA additivity check ─────────────────────────────────
        # total_rwa should equal sum of components
        expected_total_rwa = EXPECTED_CAPITAL["total_rwa"]
        expected_sum = (
            EXPECTED_CAPITAL["credit_risk_rwa"]
            + EXPECTED_CAPITAL["market_risk_rwa"]
            + EXPECTED_CAPITAL["operational_risk_rwa"]
        )
        if expected_total_rwa == expected_sum:
            checks.append(
                ValidationCheck(
                    check_id="CAP-RWA-ADDITIVITY",
                    category=ValidationCategory.CAPITAL,
                    description="RWA total equals sum of components",
                    status=CheckStatus.PASS,
                    expected_value=expected_total_rwa,
                    actual_value=expected_sum,
                    message="RWA components sum correctly",
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    check_id="CAP-RWA-ADDITIVITY",
                    category=ValidationCategory.CAPITAL,
                    description="RWA total equals sum of components",
                    status=CheckStatus.FAIL,
                    expected_value=expected_total_rwa,
                    actual_value=expected_sum,
                    difference=expected_sum - expected_total_rwa,
                    message="RWA components do not sum to total",
                )
            )

        # ── CET1 capital derivation check ────────────────────────
        expected_cet1 = EXPECTED_CAPITAL["cet1_capital"]
        derived_cet1 = (
            EXPECTED_CAPITAL["shareholders_equity"]
            + EXPECTED_CAPITAL["retained_earnings"]
            + EXPECTED_CAPITAL["aoci"]
            + EXPECTED_CAPITAL["goodwill_deduction"]
            + EXPECTED_CAPITAL["dta_deduction"]
            + EXPECTED_CAPITAL["ava_deduction"]
            + EXPECTED_CAPITAL["other_deductions"]
        )

        if abs(expected_cet1 - derived_cet1) <= 1.0:
            checks.append(
                ValidationCheck(
                    check_id="CAP-CET1-DERIVATION",
                    category=ValidationCategory.CAPITAL,
                    description="CET1 capital equals sum of components",
                    status=CheckStatus.PASS,
                    expected_value=expected_cet1,
                    actual_value=derived_cet1,
                    message="CET1 components sum correctly",
                )
            )
        else:
            diff = derived_cet1 - expected_cet1
            checks.append(
                ValidationCheck(
                    check_id="CAP-CET1-DERIVATION",
                    category=ValidationCategory.CAPITAL,
                    description="CET1 capital equals sum of components",
                    status=CheckStatus.FAIL,
                    expected_value=expected_cet1,
                    actual_value=derived_cet1,
                    difference=diff,
                    message=f"CET1 derivation gap: {diff}",
                )
            )
            gaps.append(
                ValidationGap(
                    gap_id="GAP-CAP-CET1-DERIVATION",
                    category=ValidationCategory.CAPITAL,
                    severity="HIGH",
                    field_name="cet1_capital",
                    expected_value=expected_cet1,
                    actual_value=derived_cet1,
                    difference=diff,
                    recommendation="Review CET1 capital computation; component sum does not match total",
                )
            )

        # ── Regulatory ratio checks ──────────────────────────────

        # CET1 ratio: cet1_capital / total_rwa
        if expected_total_rwa > 0:
            computed_ratio = expected_cet1 / expected_total_rwa
            cet1_min = EXPECTED_CAPITAL["cet1_ratio_min"]
            ccb_min = EXPECTED_CAPITAL["ccb_min"]

            # Check CET1 ratio meets minimum
            if computed_ratio >= cet1_min:
                checks.append(
                    ValidationCheck(
                        check_id="CAP-CET1-RATIO-MIN",
                        category=ValidationCategory.CAPITAL,
                        description=(
                            f"CET1 ratio ({computed_ratio:.4f}) meets "
                            f"minimum requirement ({cet1_min})"
                        ),
                        status=CheckStatus.PASS,
                        expected_value=f">= {cet1_min}",
                        actual_value=round(computed_ratio, 6),
                        message="CET1 ratio above minimum",
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id="CAP-CET1-RATIO-MIN",
                        category=ValidationCategory.CAPITAL,
                        description=(
                            f"CET1 ratio ({computed_ratio:.4f}) meets "
                            f"minimum requirement ({cet1_min})"
                        ),
                        status=CheckStatus.FAIL,
                        expected_value=f">= {cet1_min}",
                        actual_value=round(computed_ratio, 6),
                        message="CET1 ratio below minimum",
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id="GAP-CAP-CET1-RATIO-MIN",
                        category=ValidationCategory.CAPITAL,
                        severity="HIGH",
                        field_name="cet1_ratio",
                        expected_value=f">= {cet1_min}",
                        actual_value=computed_ratio,
                        recommendation="CET1 ratio below regulatory minimum",
                    )
                )

            # Check CET1 ratio meets CCB
            if computed_ratio >= ccb_min:
                checks.append(
                    ValidationCheck(
                        check_id="CAP-CET1-CCB",
                        category=ValidationCategory.CAPITAL,
                        description=(
                            f"CET1 ratio ({computed_ratio:.4f}) meets "
                            f"capital conservation buffer ({ccb_min})"
                        ),
                        status=CheckStatus.PASS,
                        expected_value=f">= {ccb_min}",
                        actual_value=round(computed_ratio, 6),
                        message="CET1 ratio above CCB requirement",
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id="CAP-CET1-CCB",
                        category=ValidationCategory.CAPITAL,
                        description=(
                            f"CET1 ratio ({computed_ratio:.4f}) meets "
                            f"capital conservation buffer ({ccb_min})"
                        ),
                        status=CheckStatus.FAIL,
                        expected_value=f">= {ccb_min}",
                        actual_value=round(computed_ratio, 6),
                        message="CET1 ratio below CCB requirement",
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id="GAP-CAP-CET1-CCB",
                        category=ValidationCategory.CAPITAL,
                        severity="HIGH",
                        field_name="cet1_ratio_ccb",
                        expected_value=f">= {ccb_min}",
                        actual_value=computed_ratio,
                        recommendation="CET1 ratio below capital conservation buffer",
                    )
                )

        # ── AVA impact on CET1 ───────────────────────────────────
        ava_deduction = EXPECTED_CAPITAL["ava_deduction"]
        checks.append(
            ValidationCheck(
                check_id="CAP-AVA-IMPACT",
                category=ValidationCategory.CAPITAL,
                description="AVA deduction correctly applied to CET1",
                status=CheckStatus.PASS,
                expected_value=ava_deduction,
                actual_value=ava_deduction,
                message=(
                    f"AVA deduction of {ava_deduction:,.0f} applied "
                    f"({abs(ava_deduction) / expected_cet1 * 100:.4f}% of CET1)"
                ),
            )
        )

        return self._build_summary(checks), gaps

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _extract_value(data: dict[str, Any] | None, keys: tuple[str, ...]) -> Any:
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
        description: str,
        expected: Any,
        actual: Any,
        tolerance: float,
        field_name: str = "",
    ) -> tuple[ValidationCheck, ValidationGap | None]:
        cat = ValidationCategory.CAPITAL

        if actual is None:
            return (
                ValidationCheck(
                    check_id=check_id,
                    category=cat,
                    description=description,
                    status=CheckStatus.SKIP,
                    expected_value=expected,
                    message="Actual value not available from agent",
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
                    message="Cannot convert to numeric",
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
                    difference=round(diff, 2),
                    tolerance=tolerance,
                    message=f"Within tolerance (diff={diff:,.2f})",
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
                    difference=round(diff, 2),
                    tolerance=tolerance,
                    message=f"Near tolerance boundary (diff={diff:,.2f})",
                ),
                None,
            )

        return (
            ValidationCheck(
                check_id=check_id,
                category=cat,
                description=description,
                status=CheckStatus.FAIL,
                expected_value=expected,
                actual_value=actual,
                difference=round(diff, 2),
                tolerance=tolerance,
                message=f"Outside tolerance (diff={diff:,.2f})",
            ),
            ValidationGap(
                gap_id=f"GAP-{check_id}",
                category=cat,
                severity="HIGH" if abs_diff > tolerance * 5 else "MEDIUM",
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                difference=round(diff, 2),
                recommendation=f"Fix {field_name}: expected {expected:,}, got {actual}",
            ),
        )

    @staticmethod
    def _build_summary(checks: list[ValidationCheck]) -> CategorySummary:
        summary = CategorySummary(
            category=ValidationCategory.CAPITAL,
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

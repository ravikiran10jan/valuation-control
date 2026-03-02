"""Hierarchy Validator -- validates FV hierarchy classification and totals.

Cross-checks the fair value hierarchy (Level 1 / 2 / 3) position counts
and book values from agent 6 (IFRS 13 report) against the FV_Hierarchy
sheet in the Excel model.
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
    EXPECTED_FV_HIERARCHY,
    EXPECTED_POSITIONS,
    EXPECTED_SUMMARY,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class HierarchyValidator:
    """Validates FV hierarchy classification and book value totals."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def validate(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Run all FV hierarchy validation checks."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []

        # ── Internal consistency of expected values ──────────────
        self._validate_internal_consistency(checks, gaps)

        # ── Fetch from agent 6 ───────────────────────────────────
        actual = await self._client.get_ifrs13_report()

        if actual is None:
            checks.append(
                ValidationCheck(
                    check_id="FVH-FETCH",
                    category=ValidationCategory.FV_HIERARCHY,
                    description="Fetch IFRS 13 report from agent 6",
                    status=CheckStatus.ERROR,
                    message="Could not reach agent 6 for IFRS 13 hierarchy data",
                )
            )
            return self._build_summary(checks), gaps

        # Extract hierarchy data from the response
        hierarchy_data = self._extract_hierarchy(actual)

        # ── Validate each level ──────────────────────────────────
        for level, expected in EXPECTED_FV_HIERARCHY.items():
            expected_count = expected["count"]
            expected_bv = expected["book_value"]

            actual_level = hierarchy_data.get(level, {})
            actual_count = actual_level.get("count")
            actual_bv = actual_level.get("book_value", actual_level.get("total_value"))

            # Count check
            check_id_count = f"FVH-{level}-COUNT"
            if actual_count is not None:
                if int(actual_count) == expected_count:
                    checks.append(
                        ValidationCheck(
                            check_id=check_id_count,
                            category=ValidationCategory.FV_HIERARCHY,
                            description=f"FV hierarchy {level} position count",
                            status=CheckStatus.PASS,
                            expected_value=expected_count,
                            actual_value=actual_count,
                            message=f"Count matches: {expected_count}",
                        )
                    )
                else:
                    checks.append(
                        ValidationCheck(
                            check_id=check_id_count,
                            category=ValidationCategory.FV_HIERARCHY,
                            description=f"FV hierarchy {level} position count",
                            status=CheckStatus.FAIL,
                            expected_value=expected_count,
                            actual_value=actual_count,
                            difference=int(actual_count) - expected_count,
                            message=f"Count mismatch: expected {expected_count}, got {actual_count}",
                        )
                    )
                    gaps.append(
                        ValidationGap(
                            gap_id=f"GAP-FVH-{level}-COUNT",
                            category=ValidationCategory.FV_HIERARCHY,
                            severity="HIGH",
                            field_name=f"fv_hierarchy.{level}.count",
                            expected_value=expected_count,
                            actual_value=actual_count,
                            recommendation=(
                                f"Review FV classification: {level} should have "
                                f"{expected_count} positions, found {actual_count}"
                            ),
                        )
                    )
            else:
                checks.append(
                    ValidationCheck(
                        check_id=check_id_count,
                        category=ValidationCategory.FV_HIERARCHY,
                        description=f"FV hierarchy {level} position count",
                        status=CheckStatus.SKIP,
                        expected_value=expected_count,
                        message="Count not available from agent response",
                    )
                )

            # Book value check
            check_id_bv = f"FVH-{level}-BOOK-VALUE"
            if actual_bv is not None:
                try:
                    act_bv_f = float(actual_bv)
                    exp_bv_f = float(expected_bv)
                    diff = act_bv_f - exp_bv_f
                    tolerance = max(1000.0, abs(exp_bv_f) * 0.001)

                    if abs(diff) <= tolerance:
                        checks.append(
                            ValidationCheck(
                                check_id=check_id_bv,
                                category=ValidationCategory.FV_HIERARCHY,
                                description=f"FV hierarchy {level} book value",
                                status=CheckStatus.PASS,
                                expected_value=expected_bv,
                                actual_value=actual_bv,
                                difference=round(diff, 2),
                                tolerance=tolerance,
                                message=f"Book value within tolerance (diff={diff:,.2f})",
                            )
                        )
                    elif abs(diff) <= tolerance * 2:
                        checks.append(
                            ValidationCheck(
                                check_id=check_id_bv,
                                category=ValidationCategory.FV_HIERARCHY,
                                description=f"FV hierarchy {level} book value",
                                status=CheckStatus.WARN,
                                expected_value=expected_bv,
                                actual_value=actual_bv,
                                difference=round(diff, 2),
                                tolerance=tolerance,
                                message=f"Book value near tolerance (diff={diff:,.2f})",
                            )
                        )
                    else:
                        checks.append(
                            ValidationCheck(
                                check_id=check_id_bv,
                                category=ValidationCategory.FV_HIERARCHY,
                                description=f"FV hierarchy {level} book value",
                                status=CheckStatus.FAIL,
                                expected_value=expected_bv,
                                actual_value=actual_bv,
                                difference=round(diff, 2),
                                tolerance=tolerance,
                                message=f"Book value outside tolerance (diff={diff:,.2f})",
                            )
                        )
                        gaps.append(
                            ValidationGap(
                                gap_id=f"GAP-FVH-{level}-BOOK-VALUE",
                                category=ValidationCategory.FV_HIERARCHY,
                                severity="HIGH" if abs(diff) > tolerance * 5 else "MEDIUM",
                                field_name=f"fv_hierarchy.{level}.book_value",
                                expected_value=expected_bv,
                                actual_value=actual_bv,
                                difference=round(diff, 2),
                                recommendation=(
                                    f"Fix {level} book value: expected {expected_bv:,}, "
                                    f"got {act_bv_f:,.0f}"
                                ),
                            )
                        )
                except (TypeError, ValueError):
                    checks.append(
                        ValidationCheck(
                            check_id=check_id_bv,
                            category=ValidationCategory.FV_HIERARCHY,
                            description=f"FV hierarchy {level} book value",
                            status=CheckStatus.ERROR,
                            expected_value=expected_bv,
                            actual_value=actual_bv,
                            message="Cannot convert to numeric",
                        )
                    )
            else:
                checks.append(
                    ValidationCheck(
                        check_id=check_id_bv,
                        category=ValidationCategory.FV_HIERARCHY,
                        description=f"FV hierarchy {level} book value",
                        status=CheckStatus.SKIP,
                        expected_value=expected_bv,
                        message="Book value not available from agent response",
                    )
                )

        # ── Total book value across levels ───────────────────────
        total_bv_expected = sum(v["book_value"] for v in EXPECTED_FV_HIERARCHY.values())
        total_count_expected = sum(v["count"] for v in EXPECTED_FV_HIERARCHY.values())

        checks.append(
            ValidationCheck(
                check_id="FVH-TOTAL-COUNT",
                category=ValidationCategory.FV_HIERARCHY,
                description="Total positions across all FV levels",
                status=CheckStatus.PASS if total_count_expected == len(EXPECTED_POSITIONS) else CheckStatus.FAIL,
                expected_value=len(EXPECTED_POSITIONS),
                actual_value=total_count_expected,
                message=f"Total count: {total_count_expected}",
            )
        )

        # ── Level 3 exposure ─────────────────────────────────────
        expected_l3_exposure = EXPECTED_SUMMARY.get("level_3_exposure", 0)
        expected_l3_bv = EXPECTED_FV_HIERARCHY.get("L3", {}).get("book_value", 0)

        if expected_l3_exposure == expected_l3_bv:
            checks.append(
                ValidationCheck(
                    check_id="FVH-L3-EXPOSURE-CONSISTENCY",
                    category=ValidationCategory.FV_HIERARCHY,
                    description="L3 exposure matches between Summary and FV Hierarchy",
                    status=CheckStatus.PASS,
                    expected_value=expected_l3_exposure,
                    actual_value=expected_l3_bv,
                    message="L3 exposure consistent across sheets",
                )
            )
        else:
            checks.append(
                ValidationCheck(
                    check_id="FVH-L3-EXPOSURE-CONSISTENCY",
                    category=ValidationCategory.FV_HIERARCHY,
                    description="L3 exposure matches between Summary and FV Hierarchy",
                    status=CheckStatus.FAIL,
                    expected_value=expected_l3_exposure,
                    actual_value=expected_l3_bv,
                    difference=expected_l3_bv - expected_l3_exposure,
                    message="L3 exposure inconsistent between sheets",
                )
            )
            gaps.append(
                ValidationGap(
                    gap_id="GAP-FVH-L3-EXPOSURE",
                    category=ValidationCategory.FV_HIERARCHY,
                    severity="HIGH",
                    field_name="level_3_exposure",
                    expected_value=expected_l3_exposure,
                    actual_value=expected_l3_bv,
                    recommendation="Reconcile L3 exposure between Summary and FV Hierarchy",
                )
            )

        return self._build_summary(checks), gaps

    def _validate_internal_consistency(
        self,
        checks: list[ValidationCheck],
        gaps: list[ValidationGap],
    ) -> None:
        """Check that expected hierarchy values are internally consistent with positions."""
        # Count positions by FV level from the positions data
        level_counts: dict[str, int] = {}
        level_book_values: dict[str, float] = {}

        for pos in EXPECTED_POSITIONS:
            level = pos["fv_level"]
            level_counts[level] = level_counts.get(level, 0) + 1
            level_book_values[level] = level_book_values.get(level, 0) + pos["book_value_usd"]

        for level, expected in EXPECTED_FV_HIERARCHY.items():
            derived_count = level_counts.get(level, 0)
            expected_count = expected["count"]

            if derived_count == expected_count:
                checks.append(
                    ValidationCheck(
                        check_id=f"FVH-INTERNAL-{level}-COUNT",
                        category=ValidationCategory.FV_HIERARCHY,
                        description=(
                            f"Internal: {level} count from positions matches "
                            f"FV_Hierarchy ({expected_count})"
                        ),
                        status=CheckStatus.PASS,
                        expected_value=expected_count,
                        actual_value=derived_count,
                        message="Consistent",
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id=f"FVH-INTERNAL-{level}-COUNT",
                        category=ValidationCategory.FV_HIERARCHY,
                        description=(
                            f"Internal: {level} count from positions matches "
                            f"FV_Hierarchy ({expected_count})"
                        ),
                        status=CheckStatus.FAIL,
                        expected_value=expected_count,
                        actual_value=derived_count,
                        message=f"Positions sheet has {derived_count}, FV_Hierarchy has {expected_count}",
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id=f"GAP-FVH-INTERNAL-{level}-COUNT",
                        category=ValidationCategory.FV_HIERARCHY,
                        severity="HIGH",
                        field_name=f"fv_hierarchy.{level}.count",
                        expected_value=expected_count,
                        actual_value=derived_count,
                        recommendation=(
                            f"Reconcile {level} count between Positions and FV_Hierarchy sheets"
                        ),
                    )
                )

            derived_bv = level_book_values.get(level, 0)
            expected_bv = expected["book_value"]
            diff = abs(derived_bv - expected_bv)

            if diff <= 1.0:
                checks.append(
                    ValidationCheck(
                        check_id=f"FVH-INTERNAL-{level}-BV",
                        category=ValidationCategory.FV_HIERARCHY,
                        description=(
                            f"Internal: {level} book value from positions matches "
                            f"FV_Hierarchy ({expected_bv:,})"
                        ),
                        status=CheckStatus.PASS,
                        expected_value=expected_bv,
                        actual_value=derived_bv,
                        message="Consistent",
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id=f"FVH-INTERNAL-{level}-BV",
                        category=ValidationCategory.FV_HIERARCHY,
                        description=(
                            f"Internal: {level} book value from positions matches "
                            f"FV_Hierarchy ({expected_bv:,})"
                        ),
                        status=CheckStatus.WARN,
                        expected_value=expected_bv,
                        actual_value=derived_bv,
                        difference=round(derived_bv - expected_bv, 2),
                        message=(
                            f"Positions sum to {derived_bv:,.0f}, "
                            f"FV_Hierarchy says {expected_bv:,}"
                        ),
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id=f"GAP-FVH-INTERNAL-{level}-BV",
                        category=ValidationCategory.FV_HIERARCHY,
                        severity="MEDIUM",
                        field_name=f"fv_hierarchy.{level}.book_value",
                        expected_value=expected_bv,
                        actual_value=derived_bv,
                        difference=round(derived_bv - expected_bv, 2),
                        recommendation=(
                            f"Reconcile {level} book value between Positions "
                            f"and FV_Hierarchy"
                        ),
                    )
                )

    @staticmethod
    def _extract_hierarchy(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Extract a level -> {count, book_value} mapping from agent 6 response."""
        result: dict[str, dict[str, Any]] = {}

        # Try common response structures
        hierarchy = data.get("hierarchy", data.get("fair_value_hierarchy", data))

        if isinstance(hierarchy, dict):
            for level_key in ("L1", "L2", "L3", "Level1", "Level2", "Level3",
                              "level_1", "level_2", "level_3"):
                val = hierarchy.get(level_key)
                if isinstance(val, dict):
                    # Normalize key to L1/L2/L3
                    norm_key = level_key.replace("Level", "L").replace("level_", "L")
                    result[norm_key] = val

        if isinstance(hierarchy, list):
            for entry in hierarchy:
                level = entry.get("level", entry.get("classification", ""))
                norm = str(level).replace("Level", "L").replace("level_", "L")
                if norm in ("L1", "L2", "L3"):
                    result[norm] = entry

        return result

    @staticmethod
    def _build_summary(checks: list[ValidationCheck]) -> CategorySummary:
        summary = CategorySummary(
            category=ValidationCategory.FV_HIERARCHY,
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

"""Position Validator -- validates all 7 positions match expected data.

Compares each position field (notional, desk mark, IPV price, pct diff,
RAG status, FV level, FVA, book value) against the Excel model values.
"""

from __future__ import annotations

import structlog

from app.core.config import settings
from app.models.schemas import (
    CategorySummary,
    CheckStatus,
    ValidationCategory,
    ValidationCheck,
    ValidationGap,
)
from app.services.expected_values import EXPECTED_POSITIONS
from app.services.upstream import UpstreamClient

log = structlog.get_logger()

# Fields to compare and their tolerance strategies
_NUMERIC_FIELDS = {
    "notional_usd": ("amount", 1000.0),
    "desk_mark": ("price", None),
    "ipv_price": ("price", None),
    "pct_diff": ("pct", None),
    "fva_usd": ("amount", 5.0),
    "book_value_usd": ("amount", 1000.0),
}

_EXACT_FIELDS = ["currency_pair", "product_type", "rag_status", "fv_level"]


class PositionValidator:
    """Validates all position data against expected Excel model values."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def validate(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Run all position validation checks.

        Returns a CategorySummary and a list of identified gaps.
        """
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []

        # Attempt to fetch actual positions from agent 1
        actual_positions = await self._client.get_positions()

        if actual_positions is None:
            checks.append(
                ValidationCheck(
                    check_id="POS-FETCH",
                    category=ValidationCategory.POSITIONS,
                    description="Fetch positions from agent 1",
                    status=CheckStatus.ERROR,
                    message="Could not reach agent 1 to retrieve positions",
                )
            )
            return self._build_summary(checks), gaps

        # Build a lookup of actual positions by position_id (try common key names)
        actual_lookup: dict[str, dict] = {}
        if isinstance(actual_positions, list):
            for pos in actual_positions:
                pid = (
                    pos.get("position_id")
                    or pos.get("trade_id")
                    or pos.get("id")
                    or ""
                )
                if pid:
                    actual_lookup[str(pid)] = pos

        # --- Check: correct number of positions ---
        checks.append(
            self._compare_exact(
                check_id="POS-COUNT",
                description="Total number of positions",
                expected=len(EXPECTED_POSITIONS),
                actual=len(actual_positions) if isinstance(actual_positions, list) else 0,
            )
        )

        # --- Check each expected position ---
        for idx, expected in enumerate(EXPECTED_POSITIONS):
            pid = expected["position_id"]
            actual = actual_lookup.get(pid)

            if actual is None:
                check = ValidationCheck(
                    check_id=f"POS-{pid}-EXISTS",
                    category=ValidationCategory.POSITIONS,
                    description=f"Position {pid} exists in agent output",
                    status=CheckStatus.FAIL,
                    expected_value=pid,
                    actual_value=None,
                    message=f"Position {pid} not found in agent 1 response",
                    position_id=pid,
                )
                checks.append(check)
                gaps.append(
                    ValidationGap(
                        gap_id=f"GAP-POS-{pid}-MISSING",
                        category=ValidationCategory.POSITIONS,
                        severity="HIGH",
                        position_id=pid,
                        field_name="position_id",
                        expected_value=pid,
                        actual_value=None,
                        recommendation=f"Ensure agent 1 returns position {pid}",
                    )
                )
                continue

            # Exact-match fields
            for field in _EXACT_FIELDS:
                exp_val = expected.get(field)
                act_val = actual.get(field)
                check = self._compare_exact(
                    check_id=f"POS-{pid}-{field.upper()}",
                    description=f"{pid}: {field} matches expected",
                    expected=exp_val,
                    actual=act_val,
                    position_id=pid,
                )
                checks.append(check)
                if check.status == CheckStatus.FAIL:
                    gaps.append(
                        ValidationGap(
                            gap_id=f"GAP-POS-{pid}-{field.upper()}",
                            category=ValidationCategory.POSITIONS,
                            severity="MEDIUM",
                            position_id=pid,
                            field_name=field,
                            expected_value=exp_val,
                            actual_value=act_val,
                            recommendation=(
                                f"Fix {field} for {pid}: "
                                f"expected {exp_val}, got {act_val}"
                            ),
                        )
                    )

            # Numeric fields
            for field, (tol_type, custom_tol) in _NUMERIC_FIELDS.items():
                exp_val = expected.get(field)
                act_val = actual.get(field)
                tolerance = self._resolve_tolerance(tol_type, custom_tol)

                check = self._compare_numeric(
                    check_id=f"POS-{pid}-{field.upper()}",
                    description=f"{pid}: {field} within tolerance",
                    expected=exp_val,
                    actual=act_val,
                    tolerance=tolerance,
                    position_id=pid,
                )
                checks.append(check)
                if check.status == CheckStatus.FAIL:
                    gaps.append(
                        ValidationGap(
                            gap_id=f"GAP-POS-{pid}-{field.upper()}",
                            category=ValidationCategory.POSITIONS,
                            severity="HIGH" if abs(check.difference or 0) > tolerance * 5 else "MEDIUM",
                            position_id=pid,
                            field_name=field,
                            expected_value=exp_val,
                            actual_value=act_val,
                            difference=check.difference,
                            recommendation=(
                                f"Adjust {field} for {pid}: "
                                f"expected {exp_val}, got {act_val} "
                                f"(diff={check.difference})"
                            ),
                        )
                    )

        return self._build_summary(checks), gaps

    # ── Comparison helpers ───────────────────────────────────────

    @staticmethod
    def _compare_exact(
        check_id: str,
        description: str,
        expected: object,
        actual: object,
        position_id: str | None = None,
    ) -> ValidationCheck:
        """Compare two values for exact equality."""
        # Normalize strings for comparison
        exp_str = str(expected).strip().upper() if expected is not None else None
        act_str = str(actual).strip().upper() if actual is not None else None

        if exp_str == act_str:
            return ValidationCheck(
                check_id=check_id,
                category=ValidationCategory.POSITIONS,
                description=description,
                status=CheckStatus.PASS,
                expected_value=expected,
                actual_value=actual,
                message="Match",
                position_id=position_id,
            )
        return ValidationCheck(
            check_id=check_id,
            category=ValidationCategory.POSITIONS,
            description=description,
            status=CheckStatus.FAIL,
            expected_value=expected,
            actual_value=actual,
            message=f"Mismatch: expected={expected}, actual={actual}",
            position_id=position_id,
        )

    @staticmethod
    def _compare_numeric(
        check_id: str,
        description: str,
        expected: object,
        actual: object,
        tolerance: float,
        position_id: str | None = None,
    ) -> ValidationCheck:
        """Compare two numeric values within a tolerance."""
        if expected is None or actual is None:
            status = CheckStatus.SKIP if expected is None else CheckStatus.FAIL
            return ValidationCheck(
                check_id=check_id,
                category=ValidationCategory.POSITIONS,
                description=description,
                status=status,
                expected_value=expected,
                actual_value=actual,
                message="One or both values are None",
                position_id=position_id,
            )

        try:
            exp_f = float(expected)
            act_f = float(actual)
        except (TypeError, ValueError):
            return ValidationCheck(
                check_id=check_id,
                category=ValidationCategory.POSITIONS,
                description=description,
                status=CheckStatus.ERROR,
                expected_value=expected,
                actual_value=actual,
                message="Cannot convert to numeric for comparison",
                position_id=position_id,
            )

        diff = act_f - exp_f
        abs_diff = abs(diff)

        if abs_diff <= tolerance:
            return ValidationCheck(
                check_id=check_id,
                category=ValidationCategory.POSITIONS,
                description=description,
                status=CheckStatus.PASS,
                expected_value=expected,
                actual_value=actual,
                difference=round(diff, 6),
                tolerance=tolerance,
                message=f"Within tolerance (diff={diff:.6f}, tol={tolerance})",
                position_id=position_id,
            )

        # Check for WARN (within 2x tolerance)
        if abs_diff <= tolerance * 2:
            return ValidationCheck(
                check_id=check_id,
                category=ValidationCategory.POSITIONS,
                description=description,
                status=CheckStatus.WARN,
                expected_value=expected,
                actual_value=actual,
                difference=round(diff, 6),
                tolerance=tolerance,
                message=(
                    f"Near tolerance boundary (diff={diff:.6f}, tol={tolerance})"
                ),
                position_id=position_id,
            )

        return ValidationCheck(
            check_id=check_id,
            category=ValidationCategory.POSITIONS,
            description=description,
            status=CheckStatus.FAIL,
            expected_value=expected,
            actual_value=actual,
            difference=round(diff, 6),
            tolerance=tolerance,
            message=f"Outside tolerance (diff={diff:.6f}, tol={tolerance})",
            position_id=position_id,
        )

    @staticmethod
    def _resolve_tolerance(tol_type: str, custom: float | None) -> float:
        """Determine the numeric tolerance to apply."""
        if custom is not None:
            return custom
        if tol_type == "price":
            return settings.price_tolerance_pct
        if tol_type == "amount":
            return settings.amount_tolerance_usd
        if tol_type == "pct":
            return settings.ratio_tolerance_pct
        return settings.amount_tolerance_usd

    @staticmethod
    def _build_summary(checks: list[ValidationCheck]) -> CategorySummary:
        """Build a CategorySummary from a list of checks."""
        summary = CategorySummary(
            category=ValidationCategory.POSITIONS,
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

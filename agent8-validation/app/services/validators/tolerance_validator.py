"""Tolerance Validator -- validates RAG status assignments match expected thresholds.

Ensures that the tolerance thresholds configured in the system (G10 Spot,
EM Spot, FX Forwards, FX Options) match the Excel model's Assumptions
sheet, and that RAG status assignments for each position are correct.
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
from app.services.expected_values import (
    EXPECTED_POSITIONS,
    EXPECTED_THRESHOLDS,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()

# Mapping from position attributes to threshold category
_G10_CURRENCIES = {"EUR", "USD", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "NOK", "SEK"}
_EM_CURRENCIES = {"TRY", "BRL", "ZAR", "MXN", "INR", "IDR", "PHP", "THB"}


def _classify_threshold_category(position: dict) -> str:
    """Determine which threshold category a position falls into."""
    product_type = position.get("product_type", "").lower()
    pair = position.get("currency_pair", "")

    if product_type in ("barrier", "option", "vanilla_option"):
        return "FX_OPTIONS"
    if product_type == "forward":
        return "FX_FORWARDS"

    # Spot -- determine G10 vs EM from currency pair
    currencies = set()
    if "/" in pair:
        base, quote = pair.split("/")
        currencies = {base.upper(), quote.upper()}
    else:
        currencies = {pair.upper()}

    if currencies - _G10_CURRENCIES:
        return "EM_SPOT"
    return "G10_SPOT"


def _expected_rag(pct_diff: float, category: str) -> str:
    """Compute expected RAG status from percentage difference and threshold category."""
    thresholds = EXPECTED_THRESHOLDS.get(category, {})
    abs_diff = abs(pct_diff)

    if category in ("G10_SPOT", "FX_FORWARDS"):
        # These use BPS thresholds but pct_diff is already in percent-like units
        # For G10_SPOT: green_max_bps=5 means 5 basis points = 0.05%
        green_max = thresholds.get("green_max_bps", 5) / 100.0  # convert bps to pct
        amber_max = thresholds.get("amber_max_bps", 10) / 100.0
    else:
        green_max = thresholds.get("green_max_pct", 2.0)
        amber_max = thresholds.get("amber_max_pct", 5.0)

    if abs_diff <= green_max:
        return "GREEN"
    if abs_diff <= amber_max:
        return "AMBER"
    return "RED"


class ToleranceValidator:
    """Validates tolerance thresholds and RAG status assignments."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def validate(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Run all tolerance validation checks."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []

        # --- Validate threshold configuration ---
        await self._validate_threshold_config(checks, gaps)

        # --- Validate RAG assignment for each position ---
        self._validate_rag_assignments(checks, gaps)

        return self._build_summary(checks), gaps

    async def _validate_threshold_config(
        self,
        checks: list[ValidationCheck],
        gaps: list[ValidationGap],
    ) -> None:
        """Validate that agent-configured thresholds match expected values."""
        for category, expected in EXPECTED_THRESHOLDS.items():
            for threshold_key, expected_val in expected.items():
                check_id = f"TOL-CFG-{category}-{threshold_key.upper()}"

                # Try to fetch actual thresholds from agent 2 or agent 3
                actual_val = await self._fetch_threshold(category, threshold_key)

                if actual_val is None:
                    checks.append(
                        ValidationCheck(
                            check_id=check_id,
                            category=ValidationCategory.TOLERANCES,
                            description=(
                                f"Threshold {category}.{threshold_key} "
                                f"matches expected ({expected_val})"
                            ),
                            status=CheckStatus.SKIP,
                            expected_value=expected_val,
                            actual_value=None,
                            message="Could not retrieve threshold from upstream agent",
                        )
                    )
                    continue

                tol = settings.bps_tolerance if "bps" in threshold_key else settings.pct_threshold_tolerance
                diff = abs(float(actual_val) - float(expected_val))

                if diff <= tol:
                    checks.append(
                        ValidationCheck(
                            check_id=check_id,
                            category=ValidationCategory.TOLERANCES,
                            description=(
                                f"Threshold {category}.{threshold_key} "
                                f"matches expected ({expected_val})"
                            ),
                            status=CheckStatus.PASS,
                            expected_value=expected_val,
                            actual_value=actual_val,
                            difference=round(diff, 4),
                            tolerance=tol,
                            message="Threshold matches",
                        )
                    )
                else:
                    checks.append(
                        ValidationCheck(
                            check_id=check_id,
                            category=ValidationCategory.TOLERANCES,
                            description=(
                                f"Threshold {category}.{threshold_key} "
                                f"matches expected ({expected_val})"
                            ),
                            status=CheckStatus.FAIL,
                            expected_value=expected_val,
                            actual_value=actual_val,
                            difference=round(diff, 4),
                            tolerance=tol,
                            message=f"Threshold mismatch: expected {expected_val}, got {actual_val}",
                        )
                    )
                    gaps.append(
                        ValidationGap(
                            gap_id=f"GAP-TOL-{category}-{threshold_key.upper()}",
                            category=ValidationCategory.TOLERANCES,
                            severity="HIGH",
                            field_name=f"{category}.{threshold_key}",
                            expected_value=expected_val,
                            actual_value=actual_val,
                            difference=round(diff, 4),
                            recommendation=(
                                f"Update {category} {threshold_key} threshold from "
                                f"{actual_val} to {expected_val}"
                            ),
                        )
                    )

    def _validate_rag_assignments(
        self,
        checks: list[ValidationCheck],
        gaps: list[ValidationGap],
    ) -> None:
        """Validate that each position's RAG status is correctly assigned."""
        for position in EXPECTED_POSITIONS:
            pid = position["position_id"]
            expected_rag = position["rag_status"]
            pct_diff = position["pct_diff"]
            category = _classify_threshold_category(position)

            # Compute what the RAG should be based on thresholds
            computed_rag = _expected_rag(pct_diff, category)

            check_id = f"TOL-RAG-{pid}"

            # The Excel expected RAG should match our computed RAG
            # (validates internal consistency of the Excel model)
            if expected_rag == computed_rag:
                checks.append(
                    ValidationCheck(
                        check_id=check_id,
                        category=ValidationCategory.TOLERANCES,
                        description=(
                            f"{pid}: RAG status '{expected_rag}' consistent "
                            f"with pct_diff={pct_diff} under {category} thresholds"
                        ),
                        status=CheckStatus.PASS,
                        expected_value=expected_rag,
                        actual_value=computed_rag,
                        message=f"RAG correctly assigned for {category} (diff={pct_diff}%)",
                        position_id=pid,
                    )
                )
            else:
                # Check if the Excel overrides the RAG (e.g. FX-OPT-001 is RED
                # because it is L3, not because of pct_diff)
                is_l3_override = position.get("fv_level") == "L3"
                if is_l3_override and expected_rag == "RED":
                    checks.append(
                        ValidationCheck(
                            check_id=check_id,
                            category=ValidationCategory.TOLERANCES,
                            description=(
                                f"{pid}: RAG status 'RED' due to L3 classification override"
                            ),
                            status=CheckStatus.PASS,
                            expected_value=expected_rag,
                            actual_value="RED (L3 override)",
                            message=(
                                "L3 positions are automatically flagged RED "
                                "regardless of percentage difference"
                            ),
                            position_id=pid,
                        )
                    )
                else:
                    checks.append(
                        ValidationCheck(
                            check_id=check_id,
                            category=ValidationCategory.TOLERANCES,
                            description=(
                                f"{pid}: RAG status '{expected_rag}' consistent "
                                f"with pct_diff={pct_diff} under {category} thresholds"
                            ),
                            status=CheckStatus.WARN,
                            expected_value=expected_rag,
                            actual_value=computed_rag,
                            message=(
                                f"Computed RAG ({computed_rag}) differs from expected "
                                f"({expected_rag}) -- may indicate threshold edge case"
                            ),
                            position_id=pid,
                        )
                    )
                    gaps.append(
                        ValidationGap(
                            gap_id=f"GAP-TOL-RAG-{pid}",
                            category=ValidationCategory.TOLERANCES,
                            severity="MEDIUM",
                            position_id=pid,
                            field_name="rag_status",
                            expected_value=expected_rag,
                            actual_value=computed_rag,
                            recommendation=(
                                f"Review RAG assignment for {pid}: "
                                f"pct_diff={pct_diff}, category={category}, "
                                f"expected={expected_rag}, computed={computed_rag}"
                            ),
                        )
                    )

    async def _fetch_threshold(
        self, category: str, threshold_key: str
    ) -> float | None:
        """Attempt to fetch a threshold value from agent 2 or agent 3."""
        # Map our category names to agent API parameters
        asset_product_map = {
            "G10_SPOT": ("FX", "spot"),
            "EM_SPOT": ("FX", "em_spot"),
            "FX_FORWARDS": ("FX", "forward"),
            "FX_OPTIONS": ("FX", "option"),
        }
        mapping = asset_product_map.get(category)
        if mapping is None:
            return None

        result = await self._client.get_tolerances(mapping[0], mapping[1])
        if result is None:
            return None

        # Try to extract the relevant threshold from the response
        # The response structure varies -- try common field names
        if "bps" in threshold_key:
            if "green" in threshold_key:
                return result.get("green_threshold") or result.get("green_threshold_bps")
            return result.get("amber_threshold") or result.get("amber_threshold_bps")
        else:
            if "green" in threshold_key:
                return result.get("green_threshold") or result.get("tolerance_pct")
            return result.get("amber_threshold")

    @staticmethod
    def _build_summary(checks: list[ValidationCheck]) -> CategorySummary:
        """Build a CategorySummary from a list of checks."""
        summary = CategorySummary(
            category=ValidationCategory.TOLERANCES,
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

"""Pricing Validator -- validates barrier pricing methods match expected survival probabilities.

Cross-checks the pricing engine's (agent 2) outputs for the barrier
option against the Barrier_Pricing_Methods sheet in the Excel model,
including survival probabilities from analytical, Monte Carlo, PDE, and
Bloomberg OVML methods.
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
    EXPECTED_BARRIER_PRICING,
    EXPECTED_GREEKS_BARRIER,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class PricingValidator:
    """Validates barrier option pricing against expected values."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def validate(self) -> tuple[CategorySummary, list[ValidationGap]]:
        """Run all pricing validation checks."""
        checks: list[ValidationCheck] = []
        gaps: list[ValidationGap] = []

        # Attempt to fetch barrier pricing from agent 2
        actual = await self._client.price_fx_barrier(self._barrier_request_payload())

        if actual is None:
            checks.append(
                ValidationCheck(
                    check_id="PRC-BARRIER-FETCH",
                    category=ValidationCategory.PRICING,
                    description="Fetch barrier pricing from agent 2",
                    status=CheckStatus.ERROR,
                    message="Could not reach agent 2 pricing engine",
                )
            )
            # Still validate Greeks if possible
            await self._validate_greeks(checks, gaps)
            return self._build_summary(checks), gaps

        # --- Validate survival probabilities ---
        survival_fields = {
            "analytical_survival": ("analytical_survival", "survival_analytical"),
            "monte_carlo_survival": ("monte_carlo_survival", "mc_survival", "survival_mc"),
            "pde_survival": ("pde_survival", "survival_pde"),
            "bloomberg_ovml": ("bloomberg_ovml", "bloomberg_survival", "ovml_survival"),
            "consensus_survival": ("consensus_survival", "survival_consensus"),
        }

        tol = settings.survival_prob_tolerance
        method_results = actual.get("method_results", actual.get("methods", {}))

        for field, actual_keys in survival_fields.items():
            expected_val = EXPECTED_BARRIER_PRICING[field]
            actual_val = self._extract_value(
                method_results if isinstance(method_results, dict) else actual,
                actual_keys,
            )

            check, gap = self._numeric_check(
                check_id=f"PRC-BARRIER-{field.upper()}",
                description=f"Barrier survival probability ({field})",
                expected=expected_val,
                actual=actual_val,
                tolerance=tol,
                field_name=f"barrier_pricing.{field}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        # --- Validate fair value ---
        expected_fv = EXPECTED_BARRIER_PRICING["fair_value"]
        actual_fv = actual.get("fair_value")
        check, gap = self._numeric_check(
            check_id="PRC-BARRIER-FAIR-VALUE",
            description="Barrier option fair value",
            expected=expected_fv,
            actual=actual_fv,
            tolerance=500.0,
            field_name="barrier_pricing.fair_value",
        )
        checks.append(check)
        if gap:
            gaps.append(gap)

        # --- Validate method convergence ---
        # All methods should be within tolerance_pct of each other
        expected_tol_pct = EXPECTED_BARRIER_PRICING["tolerance_pct"]
        method_values = []
        for field in ("analytical_survival", "monte_carlo_survival", "pde_survival", "bloomberg_ovml"):
            val = self._extract_value(
                method_results if isinstance(method_results, dict) else actual,
                survival_fields[field],
            )
            if val is not None:
                try:
                    method_values.append(float(val))
                except (TypeError, ValueError):
                    pass

        if len(method_values) >= 2:
            max_val = max(method_values)
            min_val = min(method_values)
            spread_pct = ((max_val - min_val) / min_val * 100) if min_val != 0 else 0

            if spread_pct <= expected_tol_pct:
                checks.append(
                    ValidationCheck(
                        check_id="PRC-BARRIER-CONVERGENCE",
                        category=ValidationCategory.PRICING,
                        description=(
                            f"Pricing methods converge within {expected_tol_pct}% of each other"
                        ),
                        status=CheckStatus.PASS,
                        expected_value=f"<= {expected_tol_pct}%",
                        actual_value=f"{spread_pct:.4f}%",
                        message=f"Method spread {spread_pct:.4f}% is within tolerance",
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id="PRC-BARRIER-CONVERGENCE",
                        category=ValidationCategory.PRICING,
                        description=(
                            f"Pricing methods converge within {expected_tol_pct}% of each other"
                        ),
                        status=CheckStatus.FAIL,
                        expected_value=f"<= {expected_tol_pct}%",
                        actual_value=f"{spread_pct:.4f}%",
                        message=f"Method spread {spread_pct:.4f}% exceeds tolerance",
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id="GAP-PRC-BARRIER-CONVERGENCE",
                        category=ValidationCategory.PRICING,
                        severity="HIGH",
                        field_name="barrier_pricing.convergence",
                        expected_value=f"<= {expected_tol_pct}%",
                        actual_value=f"{spread_pct:.4f}%",
                        recommendation="Review barrier pricing methods for convergence issues",
                    )
                )
        else:
            checks.append(
                ValidationCheck(
                    check_id="PRC-BARRIER-CONVERGENCE",
                    category=ValidationCategory.PRICING,
                    description="Pricing methods convergence check",
                    status=CheckStatus.SKIP,
                    message="Insufficient method results for convergence check",
                )
            )

        # --- Validate Greeks ---
        await self._validate_greeks(checks, gaps)

        return self._build_summary(checks), gaps

    async def _validate_greeks(
        self,
        checks: list[ValidationCheck],
        gaps: list[ValidationGap],
    ) -> None:
        """Validate Greek sensitivities for the barrier option."""
        greek_fields = {
            "delta_per_pip": ("delta_per_pip", "delta"),
            "vega_per_1pct": ("vega_per_1pct", "vega"),
            "theta_daily": ("theta_daily", "theta"),
        }

        # Try to get Greeks from the pricing response or a separate endpoint
        actual_greeks = await self._client.price_fx_barrier(self._barrier_request_payload())
        greeks_data: dict[str, Any] = {}
        if actual_greeks is not None:
            greeks_data = actual_greeks.get("greeks", actual_greeks)

        for field, actual_keys in greek_fields.items():
            expected_val = EXPECTED_GREEKS_BARRIER[field]
            actual_val = self._extract_value(greeks_data, actual_keys)

            # Greeks have wider tolerances
            tolerance = abs(expected_val) * 0.10 if isinstance(expected_val, (int, float)) and expected_val != 0 else 100.0

            check, gap = self._numeric_check(
                check_id=f"PRC-GREEK-{field.upper()}",
                description=f"Barrier Greek: {field}",
                expected=expected_val,
                actual=actual_val,
                tolerance=tolerance,
                field_name=f"greeks.{field}",
            )
            checks.append(check)
            if gap:
                gaps.append(gap)

        # Gamma near barrier (qualitative check)
        expected_gamma = EXPECTED_GREEKS_BARRIER["gamma_near_barrier"]
        actual_gamma = greeks_data.get("gamma_near_barrier", greeks_data.get("gamma_flag"))
        if actual_gamma is not None:
            if str(actual_gamma).upper() == str(expected_gamma).upper():
                checks.append(
                    ValidationCheck(
                        check_id="PRC-GREEK-GAMMA-BARRIER",
                        category=ValidationCategory.PRICING,
                        description="Barrier gamma near barrier flag",
                        status=CheckStatus.PASS,
                        expected_value=expected_gamma,
                        actual_value=actual_gamma,
                        message="Gamma near barrier flag matches",
                    )
                )
            else:
                checks.append(
                    ValidationCheck(
                        check_id="PRC-GREEK-GAMMA-BARRIER",
                        category=ValidationCategory.PRICING,
                        description="Barrier gamma near barrier flag",
                        status=CheckStatus.FAIL,
                        expected_value=expected_gamma,
                        actual_value=actual_gamma,
                        message=f"Expected {expected_gamma}, got {actual_gamma}",
                    )
                )
                gaps.append(
                    ValidationGap(
                        gap_id="GAP-PRC-GREEK-GAMMA-BARRIER",
                        category=ValidationCategory.PRICING,
                        severity="MEDIUM",
                        field_name="greeks.gamma_near_barrier",
                        expected_value=expected_gamma,
                        actual_value=actual_gamma,
                        recommendation="Review gamma near barrier classification",
                    )
                )
        else:
            checks.append(
                ValidationCheck(
                    check_id="PRC-GREEK-GAMMA-BARRIER",
                    category=ValidationCategory.PRICING,
                    description="Barrier gamma near barrier flag",
                    status=CheckStatus.SKIP,
                    expected_value=expected_gamma,
                    message="Gamma near barrier flag not available from agent",
                )
            )

    @staticmethod
    def _barrier_request_payload() -> dict[str, Any]:
        """Build a representative barrier pricing request payload."""
        return {
            "spot": 1.0825,
            "lower_barrier": 1.05,
            "upper_barrier": 1.15,
            "maturity": 0.917,  # ~11 months
            "notional": 50_000_000,
            "vol": 0.085,
            "r_dom": 0.045,
            "r_for": 0.035,
            "barrier_type": "double_knock_out",
            "currency": "USD",
            "mc_paths": 100_000,
        }

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
        """Compare two numeric values and return check + optional gap."""
        cat = ValidationCategory.PRICING

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
                    difference=round(diff, 6),
                    tolerance=tolerance,
                    message=f"Within tolerance (diff={diff:.6f})",
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
                    difference=round(diff, 6),
                    tolerance=tolerance,
                    message=f"Near tolerance boundary (diff={diff:.6f})",
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
                difference=round(diff, 6),
                tolerance=tolerance,
                message=f"Outside tolerance (diff={diff:.6f})",
            ),
            ValidationGap(
                gap_id=f"GAP-{check_id}",
                category=cat,
                severity="HIGH" if abs_diff > tolerance * 5 else "MEDIUM",
                field_name=field_name,
                expected_value=expected,
                actual_value=actual,
                difference=round(diff, 6),
                recommendation=f"Fix {field_name}: expected {expected}, got {actual}",
            ),
        )

    @staticmethod
    def _build_summary(checks: list[ValidationCheck]) -> CategorySummary:
        summary = CategorySummary(
            category=ValidationCategory.PRICING,
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

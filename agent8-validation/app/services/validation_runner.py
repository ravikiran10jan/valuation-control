"""Validation Runner -- executes ALL validators and produces a comprehensive report.

Orchestrates the position, tolerance, reserve, pricing, capital, and
hierarchy validators, aggregates their results into a single report,
and computes an overall accuracy score.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import structlog

from app.models.schemas import (
    CategorySummary,
    CheckStatus,
    ValidationCategory,
    ValidationCheck,
    ValidationGap,
    ValidationReport,
)
from app.services.upstream import UpstreamClient
from app.services.validators.capital_validator import CapitalValidator
from app.services.validators.hierarchy_validator import HierarchyValidator
from app.services.validators.position_validator import PositionValidator
from app.services.validators.pricing_validator import PricingValidator
from app.services.validators.reserve_validator import ReserveValidator
from app.services.validators.tolerance_validator import ToleranceValidator

log = structlog.get_logger()

# Module-level cache for the latest report
_latest_report: ValidationReport | None = None


def get_latest_report() -> ValidationReport | None:
    """Return the most recent validation report, or None."""
    return _latest_report


class ValidationRunner:
    """Orchestrates all validators and produces a comprehensive report."""

    def __init__(self) -> None:
        self._client = UpstreamClient()

    async def run_all(
        self,
        categories: list[ValidationCategory] | None = None,
    ) -> ValidationReport:
        """Execute the full (or filtered) validation suite.

        Args:
            categories: If provided, only run validators for these categories.
                        None means run everything.

        Returns:
            A ValidationReport with all results.
        """
        global _latest_report

        report_id = f"VAL-{uuid.uuid4().hex[:12].upper()}"
        start = time.monotonic()
        log.info("validation_run_start", report_id=report_id, categories=categories)

        # Health checks
        agents_reachable = await self._client.check_all_health()
        log.info("agent_health_check", reachable=agents_reachable)

        all_summaries: list[CategorySummary] = []
        all_gaps: list[ValidationGap] = []

        run_all = categories is None

        # ── Positions ────────────────────────────────────────────
        if run_all or ValidationCategory.POSITIONS in categories:
            try:
                summary, gaps = await PositionValidator(self._client).validate()
                all_summaries.append(summary)
                all_gaps.extend(gaps)
                log.info(
                    "validator_complete",
                    category="POSITIONS",
                    passed=summary.passed,
                    failed=summary.failed,
                )
            except Exception as exc:
                log.error("validator_error", category="POSITIONS", error=str(exc))
                all_summaries.append(self._error_summary(ValidationCategory.POSITIONS, exc))

        # ── Tolerances ───────────────────────────────────────────
        if run_all or ValidationCategory.TOLERANCES in categories:
            try:
                summary, gaps = await ToleranceValidator(self._client).validate()
                all_summaries.append(summary)
                all_gaps.extend(gaps)
                log.info(
                    "validator_complete",
                    category="TOLERANCES",
                    passed=summary.passed,
                    failed=summary.failed,
                )
            except Exception as exc:
                log.error("validator_error", category="TOLERANCES", error=str(exc))
                all_summaries.append(self._error_summary(ValidationCategory.TOLERANCES, exc))

        # ── Reserves (FVA, AVA, Model Reserve, Day1 PnL) ────────
        reserve_cats = {
            ValidationCategory.FVA,
            ValidationCategory.AVA,
            ValidationCategory.MODEL_RESERVE,
            ValidationCategory.DAY1_PNL,
        }
        if run_all or reserve_cats & set(categories or []):
            try:
                summaries, gaps = await ReserveValidator(self._client).validate()
                for s in summaries:
                    if run_all or s.category in (categories or []):
                        all_summaries.append(s)
                all_gaps.extend(gaps)
                for s in summaries:
                    log.info(
                        "validator_complete",
                        category=s.category.value,
                        passed=s.passed,
                        failed=s.failed,
                    )
            except Exception as exc:
                log.error("validator_error", category="RESERVES", error=str(exc))
                for cat in reserve_cats:
                    if run_all or cat in (categories or []):
                        all_summaries.append(self._error_summary(cat, exc))

        # ── Pricing ──────────────────────────────────────────────
        if run_all or ValidationCategory.PRICING in categories:
            try:
                summary, gaps = await PricingValidator(self._client).validate()
                all_summaries.append(summary)
                all_gaps.extend(gaps)
                log.info(
                    "validator_complete",
                    category="PRICING",
                    passed=summary.passed,
                    failed=summary.failed,
                )
            except Exception as exc:
                log.error("validator_error", category="PRICING", error=str(exc))
                all_summaries.append(self._error_summary(ValidationCategory.PRICING, exc))

        # ── Capital ──────────────────────────────────────────────
        if run_all or ValidationCategory.CAPITAL in categories:
            try:
                summary, gaps = await CapitalValidator(self._client).validate()
                all_summaries.append(summary)
                all_gaps.extend(gaps)
                log.info(
                    "validator_complete",
                    category="CAPITAL",
                    passed=summary.passed,
                    failed=summary.failed,
                )
            except Exception as exc:
                log.error("validator_error", category="CAPITAL", error=str(exc))
                all_summaries.append(self._error_summary(ValidationCategory.CAPITAL, exc))

        # ── FV Hierarchy ─────────────────────────────────────────
        if run_all or ValidationCategory.FV_HIERARCHY in categories:
            try:
                summary, gaps = await HierarchyValidator(self._client).validate()
                all_summaries.append(summary)
                all_gaps.extend(gaps)
                log.info(
                    "validator_complete",
                    category="FV_HIERARCHY",
                    passed=summary.passed,
                    failed=summary.failed,
                )
            except Exception as exc:
                log.error("validator_error", category="FV_HIERARCHY", error=str(exc))
                all_summaries.append(
                    self._error_summary(ValidationCategory.FV_HIERARCHY, exc)
                )

        # ── Aggregate ────────────────────────────────────────────
        total_checks = sum(s.total_checks for s in all_summaries)
        total_passed = sum(s.passed for s in all_summaries)
        total_failed = sum(s.failed for s in all_summaries)
        total_warned = sum(s.warned for s in all_summaries)
        total_skipped = sum(s.skipped for s in all_summaries)
        total_errors = sum(s.errors for s in all_summaries)

        evaluable = total_checks - total_skipped
        overall_score = round((total_passed / evaluable) * 100, 2) if evaluable > 0 else 0.0

        # Generate recommendations from gaps
        recommendations = self._generate_recommendations(all_gaps)

        elapsed = time.monotonic() - start

        report = ValidationReport(
            report_id=report_id,
            timestamp=datetime.now(timezone.utc),
            overall_score_pct=overall_score,
            total_checks=total_checks,
            total_passed=total_passed,
            total_failed=total_failed,
            total_warned=total_warned,
            total_skipped=total_skipped,
            total_errors=total_errors,
            categories=all_summaries,
            gaps=all_gaps,
            recommendations=recommendations,
            agents_reachable=agents_reachable,
        )

        _latest_report = report

        log.info(
            "validation_run_complete",
            report_id=report_id,
            overall_score=overall_score,
            total_checks=total_checks,
            passed=total_passed,
            failed=total_failed,
            warned=total_warned,
            skipped=total_skipped,
            errors=total_errors,
            gaps=len(all_gaps),
            elapsed_seconds=round(elapsed, 3),
        )

        return report

    # ── Category-specific runners ────────────────────────────────

    async def run_positions(self) -> ValidationReport:
        """Run only position validation."""
        return await self.run_all(categories=[ValidationCategory.POSITIONS])

    async def run_tolerances(self) -> ValidationReport:
        """Run only tolerance validation."""
        return await self.run_all(categories=[ValidationCategory.TOLERANCES])

    async def run_reserves(self) -> ValidationReport:
        """Run only reserve validations (FVA, AVA, Model Reserve, Day1 PnL)."""
        return await self.run_all(
            categories=[
                ValidationCategory.FVA,
                ValidationCategory.AVA,
                ValidationCategory.MODEL_RESERVE,
                ValidationCategory.DAY1_PNL,
            ]
        )

    async def run_pricing(self) -> ValidationReport:
        """Run only pricing validation."""
        return await self.run_all(categories=[ValidationCategory.PRICING])

    async def run_capital(self) -> ValidationReport:
        """Run only capital adequacy validation."""
        return await self.run_all(categories=[ValidationCategory.CAPITAL])

    async def run_hierarchy(self) -> ValidationReport:
        """Run only FV hierarchy validation."""
        return await self.run_all(categories=[ValidationCategory.FV_HIERARCHY])

    # ── Helpers ──────────────────────────────────────────────────

    @staticmethod
    def _error_summary(
        cat: ValidationCategory, exc: Exception
    ) -> CategorySummary:
        """Create a single-check error summary when a validator crashes."""
        return CategorySummary(
            category=cat,
            total_checks=1,
            errors=1,
            checks=[
                ValidationCheck(
                    check_id=f"{cat.value}-CRASH",
                    category=cat,
                    description=f"Execute {cat.value} validator",
                    status=CheckStatus.ERROR,
                    message=f"Validator raised exception: {exc}",
                )
            ],
        )

    @staticmethod
    def _generate_recommendations(gaps: list[ValidationGap]) -> list[str]:
        """Derive prioritised recommendations from the gap list."""
        recommendations: list[str] = []

        high_gaps = [g for g in gaps if g.severity == "HIGH"]
        medium_gaps = [g for g in gaps if g.severity == "MEDIUM"]
        low_gaps = [g for g in gaps if g.severity == "LOW"]

        if high_gaps:
            recommendations.append(
                f"CRITICAL: {len(high_gaps)} high-severity gap(s) found. "
                f"Address these first to bring the system into alignment "
                f"with the Excel model."
            )

        # Group by category
        categories_with_failures: set[str] = set()
        for g in gaps:
            categories_with_failures.add(g.category.value)

        if "POSITIONS" in categories_with_failures:
            recommendations.append(
                "Review agent 1 position data ingestion. One or more "
                "position fields do not match the Excel model."
            )

        if "TOLERANCES" in categories_with_failures:
            recommendations.append(
                "Verify tolerance threshold configuration in agent 3 "
                "(IPV Orchestrator). RAG status assignments may be incorrect."
            )

        if "FVA" in categories_with_failures or "AVA" in categories_with_failures:
            recommendations.append(
                "Review reserve calculations in agent 5. FVA or AVA "
                "amounts deviate from the Excel model."
            )

        if "MODEL_RESERVE" in categories_with_failures:
            recommendations.append(
                "Check model reserve computation in agent 5. Reserve "
                "amounts or materiality classifications may be off."
            )

        if "DAY1_PNL" in categories_with_failures:
            recommendations.append(
                "Validate Day 1 P&L recognition logic in agent 5. "
                "Deferred amounts or amortization schedules may differ."
            )

        if "PRICING" in categories_with_failures:
            recommendations.append(
                "Review pricing engine (agent 2) barrier option methods. "
                "Survival probabilities or fair values may need recalibration."
            )

        if "CAPITAL" in categories_with_failures:
            recommendations.append(
                "Verify capital adequacy inputs in agent 6. CET1 "
                "components or RWA calculations may not match the Excel model."
            )

        if "FV_HIERARCHY" in categories_with_failures:
            recommendations.append(
                "Reconcile FV hierarchy classifications in agent 6. "
                "Level counts or book values may be inconsistent."
            )

        if medium_gaps:
            recommendations.append(
                f"{len(medium_gaps)} medium-severity gap(s) should be "
                f"reviewed during the next validation cycle."
            )

        if low_gaps:
            recommendations.append(
                f"{len(low_gaps)} low-severity gap(s) noted for information."
            )

        if not gaps:
            recommendations.append(
                "All checks passed. The multi-agent system is fully "
                "aligned with the Excel model."
            )

        return recommendations

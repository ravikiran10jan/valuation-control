"""Step 4: Flag Exceptions.

Generates RED/AMBER/GREEN status using specific thresholds and creates
exception records for positions that breach tolerances.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import structlog

from app.core.config import settings
from app.models.schemas import (
    ComparisonResult,
    ExceptionRecord,
    FairValueLevel,
    PositionInput,
    RAGStatus,
)
from app.services.tolerance_engine import calculate_breach_amount_usd

log = structlog.get_logger()


class ExceptionGenerator:
    """Generates exception records for positions breaching IPV tolerances."""

    def flag_exception(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
    ) -> Optional[ExceptionRecord]:
        """Flag an exception for a position if it breaches tolerance.

        Only AMBER and RED positions generate exceptions.
        GREEN positions return None.

        Auto-action logic:
          - AMBER: create exception for investigation
          - RED L1/L2: create exception + trigger dispute
          - RED L3: create exception + trigger dispute + escalate to committee
        """
        if comparison.rag_status == RAGStatus.GREEN:
            return None

        breach_usd = calculate_breach_amount_usd(
            comparison.difference_pct,
            position.notional,
            comparison.product_category,
        )

        # Determine auto-action based on severity and fair value level
        auto_action = self._determine_auto_action(
            comparison.rag_status,
            position.fair_value_level,
            breach_usd,
        )

        exception = ExceptionRecord(
            position_id=position.position_id,
            severity=comparison.rag_status,
            difference=comparison.difference,
            difference_pct=comparison.difference_pct,
            breach_amount_usd=breach_usd,
            product_category=comparison.product_category,
            fair_value_level=position.fair_value_level,
            auto_action=auto_action,
        )

        log.info(
            "exception_flagged",
            position_id=position.position_id,
            severity=comparison.rag_status.value,
            diff_pct=f"{comparison.difference_pct:.4f}%",
            breach_usd=str(breach_usd) if breach_usd else "N/A",
            auto_action=auto_action,
        )

        return exception

    def _determine_auto_action(
        self,
        severity: RAGStatus,
        level: FairValueLevel,
        breach_usd: Optional[Decimal],
    ) -> str:
        """Determine the automatic action to take for a breach.

        Rules:
          - AMBER: Log for investigation only, no immediate dispute
          - RED: Always trigger dispute
          - RED + L3: Escalate to VC committee
          - RED + material (>500K USD): Escalate to VC committee
        """
        if severity == RAGStatus.AMBER:
            return "NONE"

        # RED severity
        if level == FairValueLevel.L3:
            return "ESCALATE"

        if breach_usd and breach_usd > Decimal(str(settings.materiality_threshold_usd)):
            return "ESCALATE"

        return "DISPUTE"

    def flag_all(
        self,
        positions: list[PositionInput],
        comparisons: dict[str, ComparisonResult],
    ) -> dict[str, Optional[ExceptionRecord]]:
        """Flag exceptions for all positions.

        Returns a dict mapping position_id -> ExceptionRecord (or None for GREEN).
        """
        exceptions: dict[str, Optional[ExceptionRecord]] = {}
        for pos in positions:
            comp = comparisons.get(pos.position_id)
            if comp is None:
                exceptions[pos.position_id] = None
                continue
            exceptions[pos.position_id] = self.flag_exception(pos, comp)

        # Log summary
        raised = [e for e in exceptions.values() if e is not None]
        amber_count = sum(1 for e in raised if e.severity == RAGStatus.AMBER)
        red_count = sum(1 for e in raised if e.severity == RAGStatus.RED)
        dispute_count = sum(1 for e in raised if e.auto_action == "DISPUTE")
        escalate_count = sum(1 for e in raised if e.auto_action == "ESCALATE")

        log.info(
            "exceptions_summary",
            total=len(raised),
            amber=amber_count,
            red=red_count,
            disputes=dispute_count,
            escalations=escalate_count,
        )

        return exceptions

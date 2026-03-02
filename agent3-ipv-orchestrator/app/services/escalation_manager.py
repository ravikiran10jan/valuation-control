"""Steps 5-6: Investigate & Dispute + Escalate to VC Committee.

Step 5: Triggers Agent 4 (Dispute Workflow) for breached positions.
Step 6: Auto-escalates material variances to the VC Committee.
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import structlog

from app.core.config import settings
from app.models.schemas import (
    ComparisonResult,
    EscalationRecord,
    ExceptionRecord,
    FairValueLevel,
    PositionInput,
    RAGStatus,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class EscalationManager:
    """Manages dispute creation and escalation to VC committee."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def process_exception(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        exception: ExceptionRecord,
        valuation_date: date,
    ) -> EscalationRecord:
        """Process a single exception: create dispute and/or escalate.

        Step 5 logic (Investigate & Dispute):
          - RED positions: create a dispute in Agent 4
          - AMBER positions: logged for monitoring, no immediate dispute

        Step 6 logic (Escalate to Committee):
          - RED + L3: auto-escalate to VC committee
          - RED + material breach (>500K USD): auto-escalate
          - All other RED: create dispute for desk investigation
        """
        if exception.auto_action == "NONE":
            # AMBER: monitor only, no active dispute
            log.info(
                "escalation_monitor_only",
                position_id=position.position_id,
                severity=exception.severity.value,
            )
            return EscalationRecord(
                position_id=position.position_id,
                action="NO_ACTION",
                reason=f"AMBER exception logged for monitoring (diff: {exception.difference_pct:.4f}%)",
            )

        dispute_id: Optional[int] = None
        committee_agenda_id: Optional[int] = None

        # Step 5: Create dispute for RED positions
        if exception.auto_action in ("DISPUTE", "ESCALATE"):
            dispute_id = await self._create_dispute(position, comparison, exception)

        # Step 6: Escalate to committee for material breaches
        if exception.auto_action == "ESCALATE":
            committee_agenda_id = await self._escalate_to_committee(
                position, comparison, exception, dispute_id, valuation_date,
            )

        if exception.auto_action == "ESCALATE":
            action = "ESCALATED_TO_COMMITTEE"
            target = "COMMITTEE"
            reason = self._build_escalation_reason(position, exception)
        else:
            action = "DISPUTE_CREATED"
            target = "DESK"
            reason = (
                f"Dispute created: desk mark {comparison.desk_mark} vs "
                f"IPV {comparison.ipv_price} (diff: {comparison.difference_pct:.4f}%)"
            )

        log.info(
            "escalation_complete",
            position_id=position.position_id,
            action=action,
            dispute_id=dispute_id,
            committee_agenda_id=committee_agenda_id,
        )

        return EscalationRecord(
            position_id=position.position_id,
            action=action,
            dispute_id=dispute_id,
            committee_agenda_id=committee_agenda_id,
            reason=reason,
            target=target,
        )

    async def _create_dispute(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        exception: ExceptionRecord,
    ) -> Optional[int]:
        """Create a dispute in Agent 4."""
        try:
            result = await self._client.create_dispute(
                position_id=int(position.position_id.split("-")[-1])
                if "-" in position.position_id
                else 0,
                exception_id=0,  # Will be populated by Agent 4
                vc_fair_value=comparison.ipv_price,
                desk_mark=comparison.desk_mark,
                difference=comparison.difference,
                difference_pct=comparison.difference_pct,
                vc_analyst="ipv_orchestrator",
            )
            dispute_id = result.get("dispute_id")
            log.info(
                "dispute_created",
                position_id=position.position_id,
                dispute_id=dispute_id,
            )
            return dispute_id
        except Exception as exc:
            log.error(
                "dispute_creation_failed",
                position_id=position.position_id,
                error=str(exc),
            )
            return None

    async def _escalate_to_committee(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        exception: ExceptionRecord,
        dispute_id: Optional[int],
        valuation_date: date,
    ) -> Optional[int]:
        """Escalate an exception to the VC Committee agenda."""
        # Schedule committee meeting: next business day + escalation_committee_days
        meeting_date = valuation_date + timedelta(days=settings.escalation_committee_days)

        try:
            result = await self._client.add_to_committee_agenda(
                exception_id=dispute_id or 0,
                position_id=int(position.position_id.split("-")[-1])
                if "-" in position.position_id
                else 0,
                difference=comparison.difference,
                meeting_date=meeting_date,
            )
            agenda_id = result.get("agenda_id")
            log.info(
                "committee_escalation_created",
                position_id=position.position_id,
                agenda_id=agenda_id,
                meeting_date=meeting_date.isoformat(),
            )
            return agenda_id
        except Exception as exc:
            log.error(
                "committee_escalation_failed",
                position_id=position.position_id,
                error=str(exc),
            )
            return None

    def _build_escalation_reason(
        self,
        position: PositionInput,
        exception: ExceptionRecord,
    ) -> str:
        """Build a human-readable escalation reason."""
        reasons = []
        if exception.severity == RAGStatus.RED:
            reasons.append(f"RED severity ({exception.difference_pct:.4f}% variance)")
        if position.fair_value_level == FairValueLevel.L3:
            reasons.append("Level 3 fair value (model-dependent)")
        if (
            exception.breach_amount_usd
            and exception.breach_amount_usd > Decimal(str(settings.materiality_threshold_usd))
        ):
            reasons.append(
                f"Material breach: USD {exception.breach_amount_usd:,.0f} "
                f"exceeds threshold USD {settings.materiality_threshold_usd:,.0f}"
            )
        return "; ".join(reasons) if reasons else "Auto-escalated by IPV orchestrator"

    async def process_all(
        self,
        positions: list[PositionInput],
        comparisons: dict[str, ComparisonResult],
        exceptions: dict[str, Optional[ExceptionRecord]],
        valuation_date: date,
    ) -> dict[str, EscalationRecord]:
        """Process all exceptions: create disputes and escalations.

        Returns a dict mapping position_id -> EscalationRecord.
        Only processes positions that have non-None exceptions.
        """
        records: dict[str, EscalationRecord] = {}

        for pos in positions:
            exc = exceptions.get(pos.position_id)
            comp = comparisons.get(pos.position_id)
            if exc is None or comp is None:
                # GREEN position, no escalation needed
                records[pos.position_id] = EscalationRecord(
                    position_id=pos.position_id,
                    action="NO_ACTION",
                    reason="Within tolerance (GREEN)",
                )
                continue

            record = await self.process_exception(pos, comp, exc, valuation_date)
            records[pos.position_id] = record

        # Log summary
        disputes = sum(1 for r in records.values() if r.dispute_id is not None)
        escalations = sum(1 for r in records.values() if r.committee_agenda_id is not None)
        log.info(
            "escalation_summary",
            total_processed=len(records),
            disputes_created=disputes,
            committee_escalations=escalations,
        )

        return records

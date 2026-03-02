"""Step 7: Resolve & Adjust.

Posts adjustments and creates reserves via Agent 5 (Reserve Calculations)
for positions that breached tolerances.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Optional

import structlog

from app.models.schemas import (
    ComparisonResult,
    EscalationRecord,
    ExceptionRecord,
    PositionInput,
    RAGStatus,
    ResolutionRecord,
    ValuationResult,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class ResolutionEngine:
    """Handles post-IPV adjustments and reserve creation via Agent 5."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def resolve_position(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        valuation: ValuationResult,
        exception: Optional[ExceptionRecord],
        escalation: Optional[EscalationRecord],
    ) -> ResolutionRecord:
        """Resolve a single position: create reserves or post adjustments.

        Resolution logic:
          - GREEN: No action needed
          - AMBER: Create prudent valuation reserve (AVA-style)
          - RED with dispute: Reserve the difference pending resolution
          - RED escalated: Full reserve + model reserve for L3 positions
        """
        if exception is None:
            # GREEN position — no reserve needed
            return ResolutionRecord(
                position_id=position.position_id,
                action="NO_ACTION",
                notes="Position within tolerance (GREEN) — no reserve required",
            )

        reserve_amount: Optional[Decimal] = None
        reserve_type: Optional[str] = None
        adjustment_amount: Optional[Decimal] = None

        if exception.severity == RAGStatus.AMBER:
            # AMBER: create a prudent valuation adjustment (small reserve)
            reserve_amount, reserve_type = await self._create_amber_reserve(
                position, comparison, valuation,
            )
            action = "RESERVE_CREATED"
            notes = (
                f"Prudent valuation reserve of USD {reserve_amount:,.2f} "
                f"created for AMBER breach ({comparison.difference_pct:.4f}%)"
            )

        elif exception.severity == RAGStatus.RED:
            if escalation and escalation.action == "ESCALATED_TO_COMMITTEE":
                # RED + Escalated: full reserve + potential model reserve
                reserve_amount, reserve_type = await self._create_red_escalated_reserve(
                    position, comparison, valuation,
                )
                action = "RESERVE_CREATED"
                notes = (
                    f"Full IPV reserve of USD {reserve_amount:,.2f} created "
                    f"for RED breach escalated to committee ({comparison.difference_pct:.4f}%)"
                )
            else:
                # RED with dispute: reserve the breach amount
                reserve_amount, reserve_type = await self._create_red_dispute_reserve(
                    position, comparison, valuation,
                )
                action = "RESERVE_CREATED"
                notes = (
                    f"Dispute reserve of USD {reserve_amount:,.2f} created "
                    f"for RED breach under dispute ({comparison.difference_pct:.4f}%)"
                )
        else:
            action = "NO_ACTION"
            notes = "No resolution action required"

        log.info(
            "resolution_complete",
            position_id=position.position_id,
            action=action,
            reserve_type=reserve_type,
            reserve_amount=str(reserve_amount) if reserve_amount else "N/A",
        )

        return ResolutionRecord(
            position_id=position.position_id,
            action=action,
            reserve_type=reserve_type,
            reserve_amount=reserve_amount,
            adjustment_amount=adjustment_amount,
            notes=notes,
        )

    async def _create_amber_reserve(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        valuation: ValuationResult,
    ) -> tuple[Decimal, str]:
        """Create a prudent valuation reserve for an AMBER breach.

        Reserve = notional * (abs_diff_pct - green_threshold) / 100.
        """
        abs_diff = abs(comparison.difference_pct)
        excess_pct = abs_diff - comparison.threshold_green
        reserve = (position.notional * excess_pct) / Decimal("100")
        reserve = reserve.quantize(Decimal("0.01"))

        # Call Agent 5 to persist the reserve
        await self._call_agent5_reserves(position, valuation, reserve, "AVA")

        return reserve, "AVA"

    async def _create_red_dispute_reserve(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        valuation: ValuationResult,
    ) -> tuple[Decimal, str]:
        """Create a dispute reserve for a RED breach.

        Reserve = notional * abs(diff_pct) / 100 — full breach amount.
        """
        abs_diff = abs(comparison.difference_pct)
        reserve = (position.notional * abs_diff) / Decimal("100")
        reserve = reserve.quantize(Decimal("0.01"))

        await self._call_agent5_reserves(position, valuation, reserve, "FVA")

        return reserve, "FVA"

    async def _create_red_escalated_reserve(
        self,
        position: PositionInput,
        comparison: ComparisonResult,
        valuation: ValuationResult,
    ) -> tuple[Decimal, str]:
        """Create an escalated reserve for a RED breach escalated to committee.

        Reserve = notional * abs(diff_pct) / 100 + model reserve component.
        The model reserve adds an additional 10% buffer for L3 positions.
        """
        abs_diff = abs(comparison.difference_pct)
        base_reserve = (position.notional * abs_diff) / Decimal("100")

        # Add model reserve buffer for L3 positions
        if position.fair_value_level.value == "L3":
            model_buffer = base_reserve * Decimal("0.10")  # 10% additional buffer
        else:
            model_buffer = Decimal("0")

        total_reserve = (base_reserve + model_buffer).quantize(Decimal("0.01"))

        await self._call_agent5_reserves(position, valuation, total_reserve, "Model_Reserve")

        return total_reserve, "Model_Reserve"

    async def _call_agent5_reserves(
        self,
        position: PositionInput,
        valuation: ValuationResult,
        reserve_amount: Decimal,
        reserve_type: str,
    ) -> Optional[dict[str, Any]]:
        """Call Agent 5 to persist the reserve calculation."""
        position_payload = {
            "position_id": 0,  # Agent 5 expects an int
            "trade_id": position.position_id,
            "product_type": position.product_type,
            "asset_class": "FX",
            "currency_pair": position.currency_pair,
            "notional": str(position.notional),
            "desk_mark": str(position.desk_mark),
            "vc_fair_value": str(valuation.ipv_price),
            "fair_value_level": position.fair_value_level.value,
        }

        try:
            result = await self._client.calculate_reserves(
                position=position_payload,
                model_results=[
                    {
                        "model_name": valuation.model_name or "ipv_model",
                        "fair_value": str(valuation.ipv_price),
                        "method": valuation.pricing_method,
                    }
                ],
            )
            log.info(
                "agent5_reserve_calculated",
                position_id=position.position_id,
                reserve_type=reserve_type,
                amount=str(reserve_amount),
            )
            return result
        except Exception as exc:
            log.warning(
                "agent5_reserve_failed",
                position_id=position.position_id,
                error=str(exc),
            )
            return None

    async def resolve_all(
        self,
        positions: list[PositionInput],
        comparisons: dict[str, ComparisonResult],
        valuations: dict[str, ValuationResult],
        exceptions: dict[str, Optional[ExceptionRecord]],
        escalations: dict[str, EscalationRecord],
    ) -> dict[str, ResolutionRecord]:
        """Resolve all positions: create reserves and adjustments.

        Returns a dict mapping position_id -> ResolutionRecord.
        """
        records: dict[str, ResolutionRecord] = {}

        for pos in positions:
            comp = comparisons.get(pos.position_id)
            val = valuations.get(pos.position_id)
            exc = exceptions.get(pos.position_id)
            esc = escalations.get(pos.position_id)

            if comp is None or val is None:
                records[pos.position_id] = ResolutionRecord(
                    position_id=pos.position_id,
                    action="NO_ACTION",
                    notes="Missing comparison or valuation data",
                )
                continue

            record = await self.resolve_position(pos, comp, val, exc, esc)
            records[pos.position_id] = record

        # Log summary
        reserves_created = sum(
            1 for r in records.values() if r.action == "RESERVE_CREATED"
        )
        total_reserves = sum(
            r.reserve_amount for r in records.values()
            if r.reserve_amount is not None
        )
        log.info(
            "resolution_summary",
            total_positions=len(records),
            reserves_created=reserves_created,
            total_reserves_usd=str(total_reserves),
        )

        return records

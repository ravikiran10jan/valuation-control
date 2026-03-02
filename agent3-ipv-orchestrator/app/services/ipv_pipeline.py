"""The MAIN IPV Orchestrator: 8-step pipeline.

Orchestrates the full Independent Price Verification lifecycle:
  1. GATHER MARKET DATA — Call Agent 1 for spot rates, forward points, vol surfaces
  2. RUN VALUATION MODEL — Call Agent 2 pricing engine for each position
  3. COMPARE DESK vs VC — Calculate differences, apply tolerance thresholds
  4. FLAG EXCEPTIONS — Generate RED/AMBER/GREEN status using specific thresholds
  5. INVESTIGATE & DISPUTE — Trigger Agent 4 dispute workflow for breaches
  6. ESCALATE TO VC COMMITTEE — Auto-escalate material variances
  7. RESOLVE & ADJUST — Post adjustments, create reserves via Agent 5
  8. REPORT — Generate regulatory reports via Agent 6
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Coroutine, Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.postgres import IPVAuditEntry, IPVPositionResult, IPVRun, IPVStepResult
from app.models.schemas import (
    ComparisonResult,
    EscalationRecord,
    ExceptionRecord,
    IPVRunRequest,
    IPVRunStatus,
    IPVRunSummary,
    IPVStepName,
    MarketDataSnapshot,
    PositionInput,
    PositionResult,
    ProgressUpdate,
    RAGStatus,
    ReportTriggerResult,
    ResolutionRecord,
    StepResult,
    StepStatus,
    ValuationResult,
)
from app.services.comparison_engine import ComparisonEngine
from app.services.escalation_manager import EscalationManager
from app.services.exception_generator import ExceptionGenerator
from app.services.market_data_gatherer import MarketDataGatherer
from app.services.report_trigger import ReportTrigger
from app.services.resolution_engine import ResolutionEngine
from app.services.tolerance_engine import classify_product, get_thresholds
from app.services.upstream import UpstreamClient
from app.services.valuation_runner import ValuationRunner

log = structlog.get_logger()

# Step definitions in order
STEP_DEFINITIONS = [
    (1, IPVStepName.GATHER_MARKET_DATA),
    (2, IPVStepName.RUN_VALUATION_MODEL),
    (3, IPVStepName.COMPARE_DESK_VS_VC),
    (4, IPVStepName.FLAG_EXCEPTIONS),
    (5, IPVStepName.INVESTIGATE_DISPUTE),
    (6, IPVStepName.ESCALATE_TO_COMMITTEE),
    (7, IPVStepName.RESOLVE_AND_ADJUST),
    (8, IPVStepName.REPORT),
]


# Type for WebSocket progress callback
ProgressCallback = Callable[[ProgressUpdate], Coroutine[Any, Any, None]]


class IPVPipeline:
    """The main IPV orchestrator that runs the full 8-step lifecycle."""

    def __init__(
        self,
        db: Optional[AsyncSession] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        self._db = db
        self._progress_callback = progress_callback
        self._client = UpstreamClient()
        self._market_data_gatherer = MarketDataGatherer(self._client)
        self._valuation_runner = ValuationRunner(self._client)
        self._comparison_engine = ComparisonEngine()
        self._exception_generator = ExceptionGenerator()
        self._escalation_manager = EscalationManager(self._client)
        self._resolution_engine = ResolutionEngine(self._client)
        self._report_trigger = ReportTrigger(self._client)

        # Pipeline state
        self._run_id: str = ""
        self._market_data: dict[str, MarketDataSnapshot] = {}
        self._valuations: dict[str, ValuationResult] = {}
        self._comparisons: dict[str, ComparisonResult] = {}
        self._exceptions: dict[str, Optional[ExceptionRecord]] = {}
        self._escalations: dict[str, EscalationRecord] = {}
        self._resolutions: dict[str, ResolutionRecord] = {}
        self._reports: list[ReportTriggerResult] = []

    async def _notify(self, update: ProgressUpdate) -> None:
        """Send a progress update via the callback."""
        if self._progress_callback:
            try:
                await self._progress_callback(update)
            except Exception as exc:
                log.warning("progress_callback_error", error=str(exc))

    async def _audit(
        self,
        action: str,
        step_name: Optional[str] = None,
        position_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Write an audit entry to the database."""
        if self._db is None:
            return
        entry = IPVAuditEntry(
            run_id=self._run_id,
            action=action,
            step_name=step_name,
            position_id=position_id,
            details=details,
        )
        self._db.add(entry)

    async def run(
        self,
        request: IPVRunRequest,
        positions: list[PositionInput],
    ) -> IPVRunSummary:
        """Execute the full 8-step IPV pipeline.

        Args:
            request: The IPV run request with configuration.
            positions: List of positions to process.

        Returns:
            IPVRunSummary with complete results.
        """
        self._run_id = f"IPV-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        started_at = datetime.utcnow()

        log.info(
            "ipv_pipeline_start",
            run_id=self._run_id,
            positions=len(positions),
            valuation_date=request.valuation_date.isoformat(),
        )

        # Initialize run record in database
        if self._db:
            db_run = IPVRun(
                run_id=self._run_id,
                valuation_date=request.valuation_date,
                run_type=request.run_type,
                status="RUNNING",
                triggered_by=request.triggered_by,
                started_at=started_at,
                total_positions=len(positions),
                config_snapshot={
                    "fx_g10_spot_green_bps": settings.fx_g10_spot_threshold_green_bps,
                    "fx_g10_spot_amber_bps": settings.fx_g10_spot_threshold_amber_bps,
                    "fx_em_spot_green_pct": settings.fx_em_spot_threshold_green_pct,
                    "fx_em_spot_amber_pct": settings.fx_em_spot_threshold_amber_pct,
                    "fx_forward_green_bps": settings.fx_forward_threshold_green_bps,
                    "fx_forward_amber_bps": settings.fx_forward_threshold_amber_bps,
                    "fx_option_green_pct": settings.fx_option_threshold_green_pct,
                    "fx_option_amber_pct": settings.fx_option_threshold_amber_pct,
                },
            )
            self._db.add(db_run)

        await self._audit("PIPELINE_STARTED", details={"positions": len(positions)})

        # Initialize summary
        summary = IPVRunSummary(
            run_id=self._run_id,
            valuation_date=request.valuation_date,
            run_type=request.run_type,
            status=IPVRunStatus.RUNNING,
            triggered_by=request.triggered_by,
            started_at=started_at,
            total_positions=len(positions),
            steps_total=8,
        )

        skip_steps = set(request.skip_steps)
        step_results: list[StepResult] = []

        # Execute each step
        for step_num, step_name in STEP_DEFINITIONS:
            if step_name in skip_steps:
                step_result = StepResult(
                    step_number=step_num,
                    step_name=step_name,
                    status=StepStatus.SKIPPED,
                )
                step_results.append(step_result)
                continue

            step_result = await self._execute_step(
                step_num, step_name, request, positions,
            )
            step_results.append(step_result)
            summary.steps_completed = sum(
                1 for s in step_results if s.status == StepStatus.COMPLETED
            )
            summary.current_step = step_name

            # Persist step result
            if self._db:
                db_step = IPVStepResult(
                    run_id=self._run_id,
                    step_number=step_num,
                    step_name=step_name.value,
                    status=step_result.status.value,
                    started_at=step_result.started_at,
                    completed_at=step_result.completed_at,
                    duration_seconds=step_result.duration_seconds,
                    positions_processed=step_result.positions_processed,
                    errors={"errors": step_result.errors} if step_result.errors else None,
                    data=step_result.data,
                )
                self._db.add(db_step)

        # Build final position results
        position_results = self._build_position_results(positions)

        # Persist position results
        if self._db:
            for pr in position_results:
                db_pos = IPVPositionResult(
                    run_id=self._run_id,
                    position_id=pr.position_id,
                    currency_pair=pr.currency_pair,
                    product_type=pr.product_type,
                    product_category=pr.product_category.value,
                    notional=pr.notional,
                    desk_mark=pr.desk_mark,
                    ipv_price=pr.ipv_price,
                    difference=pr.difference,
                    difference_pct=pr.difference_pct,
                    rag_status=pr.rag_status.value,
                    fair_value_level=pr.fair_value_level.value,
                    threshold_green=pr.threshold_green,
                    threshold_amber=pr.threshold_amber,
                    breach_amount_usd=pr.breach_amount_usd,
                    exception_raised=pr.exception_raised,
                    dispute_id=pr.dispute_id,
                    escalated=pr.escalated,
                    reserve_amount=pr.reserve_amount,
                    notes=pr.notes,
                    market_data=(
                        {"spot_rate": str(self._market_data[pr.position_id].spot_rate)}
                        if pr.position_id in self._market_data
                        and self._market_data[pr.position_id].spot_rate
                        else None
                    ),
                    pricing_details=(
                        {"method": self._valuations[pr.position_id].pricing_method}
                        if pr.position_id in self._valuations
                        else None
                    ),
                )
                self._db.add(db_pos)

        # Finalize summary
        completed_at = datetime.utcnow()
        duration = (completed_at - started_at).total_seconds()
        has_failures = any(s.status == StepStatus.FAILED for s in step_results)

        summary.completed_at = completed_at
        summary.duration_seconds = duration
        summary.status = IPVRunStatus.PARTIAL if has_failures else IPVRunStatus.COMPLETED
        summary.steps = step_results
        summary.position_results = position_results
        summary.reports_generated = self._reports

        # Compute counts
        summary.green_count = sum(1 for p in position_results if p.rag_status == RAGStatus.GREEN)
        summary.amber_count = sum(1 for p in position_results if p.rag_status == RAGStatus.AMBER)
        summary.red_count = sum(1 for p in position_results if p.rag_status == RAGStatus.RED)
        summary.l1_count = sum(1 for p in position_results if p.fair_value_level.value == "L1")
        summary.l2_count = sum(1 for p in position_results if p.fair_value_level.value == "L2")
        summary.l3_count = sum(1 for p in position_results if p.fair_value_level.value == "L3")
        summary.exceptions_raised = sum(1 for p in position_results if p.exception_raised)
        summary.disputes_created = sum(1 for p in position_results if p.dispute_id is not None)
        summary.escalations_triggered = sum(1 for p in position_results if p.escalated)
        summary.total_breach_amount_usd = sum(
            p.breach_amount_usd for p in position_results if p.breach_amount_usd
        )
        summary.total_reserves_usd = sum(
            p.reserve_amount for p in position_results if p.reserve_amount
        )

        # Update database run record
        if self._db:
            db_run.status = summary.status.value
            db_run.completed_at = completed_at
            db_run.duration_seconds = duration
            db_run.green_count = summary.green_count
            db_run.amber_count = summary.amber_count
            db_run.red_count = summary.red_count
            db_run.l1_count = summary.l1_count
            db_run.l2_count = summary.l2_count
            db_run.l3_count = summary.l3_count
            db_run.exceptions_raised = summary.exceptions_raised
            db_run.disputes_created = summary.disputes_created
            db_run.escalations_triggered = summary.escalations_triggered
            db_run.total_breach_amount_usd = summary.total_breach_amount_usd
            db_run.total_reserves_usd = summary.total_reserves_usd
            await self._db.commit()

        await self._audit("PIPELINE_COMPLETED", details={
            "status": summary.status.value,
            "duration_seconds": duration,
            "green": summary.green_count,
            "amber": summary.amber_count,
            "red": summary.red_count,
        })

        # Final progress notification
        await self._notify(ProgressUpdate(
            run_id=self._run_id,
            event_type="RUN_COMPLETED",
            message=f"IPV run completed: {summary.green_count}G/{summary.amber_count}A/{summary.red_count}R",
            progress_pct=100.0,
            data={
                "status": summary.status.value,
                "green": summary.green_count,
                "amber": summary.amber_count,
                "red": summary.red_count,
            },
        ))

        log.info(
            "ipv_pipeline_complete",
            run_id=self._run_id,
            status=summary.status.value,
            duration_seconds=round(duration, 2),
            green=summary.green_count,
            amber=summary.amber_count,
            red=summary.red_count,
        )

        return summary

    async def _execute_step(
        self,
        step_num: int,
        step_name: IPVStepName,
        request: IPVRunRequest,
        positions: list[PositionInput],
    ) -> StepResult:
        """Execute a single pipeline step with error handling."""
        started_at = datetime.utcnow()
        progress_base = ((step_num - 1) / 8) * 100

        await self._notify(ProgressUpdate(
            run_id=self._run_id,
            event_type="STEP_STARTED",
            step_number=step_num,
            step_name=step_name,
            step_status=StepStatus.RUNNING,
            message=f"Step {step_num}/8: {step_name.value}",
            progress_pct=progress_base,
        ))

        await self._audit(
            "STEP_STARTED",
            step_name=step_name.value,
            details={"step_number": step_num},
        )

        try:
            data = await self._run_step_logic(step_num, step_name, request, positions)
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()

            result = StepResult(
                step_number=step_num,
                step_name=step_name,
                status=StepStatus.COMPLETED,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                positions_processed=len(positions),
                data=data,
            )

            await self._notify(ProgressUpdate(
                run_id=self._run_id,
                event_type="STEP_COMPLETED",
                step_number=step_num,
                step_name=step_name,
                step_status=StepStatus.COMPLETED,
                message=f"Step {step_num}/8 completed: {step_name.value} ({duration:.1f}s)",
                progress_pct=progress_base + (100 / 8),
            ))

            await self._audit(
                "STEP_COMPLETED",
                step_name=step_name.value,
                details={"duration_seconds": round(duration, 2)},
            )

            return result

        except Exception as exc:
            completed_at = datetime.utcnow()
            duration = (completed_at - started_at).total_seconds()
            error_msg = f"{type(exc).__name__}: {exc}"

            log.error(
                "ipv_step_failed",
                run_id=self._run_id,
                step=step_name.value,
                error=error_msg,
            )

            await self._notify(ProgressUpdate(
                run_id=self._run_id,
                event_type="STEP_FAILED",
                step_number=step_num,
                step_name=step_name,
                step_status=StepStatus.FAILED,
                message=f"Step {step_num}/8 FAILED: {step_name.value} — {error_msg}",
                progress_pct=progress_base,
            ))

            await self._audit(
                "STEP_FAILED",
                step_name=step_name.value,
                details={"error": error_msg},
            )

            return StepResult(
                step_number=step_num,
                step_name=step_name,
                status=StepStatus.FAILED,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                errors=[error_msg],
            )

    async def _run_step_logic(
        self,
        step_num: int,
        step_name: IPVStepName,
        request: IPVRunRequest,
        positions: list[PositionInput],
    ) -> Optional[dict[str, Any]]:
        """Dispatch to the actual step logic."""
        if step_name == IPVStepName.GATHER_MARKET_DATA:
            return await self._step1_gather_market_data(positions, request.valuation_date)
        elif step_name == IPVStepName.RUN_VALUATION_MODEL:
            return await self._step2_run_valuation(positions)
        elif step_name == IPVStepName.COMPARE_DESK_VS_VC:
            return await self._step3_compare(positions)
        elif step_name == IPVStepName.FLAG_EXCEPTIONS:
            return await self._step4_flag_exceptions(positions)
        elif step_name == IPVStepName.INVESTIGATE_DISPUTE:
            return await self._step5_investigate(positions, request.valuation_date)
        elif step_name == IPVStepName.ESCALATE_TO_COMMITTEE:
            return await self._step6_escalate(positions, request.valuation_date)
        elif step_name == IPVStepName.RESOLVE_AND_ADJUST:
            return await self._step7_resolve(positions)
        elif step_name == IPVStepName.REPORT:
            return await self._step8_report(request.valuation_date)
        return None

    async def _step1_gather_market_data(
        self,
        positions: list[PositionInput],
        valuation_date: date,
    ) -> dict[str, Any]:
        """Step 1: Gather market data from Agent 1."""
        self._market_data = await self._market_data_gatherer.gather_all(
            positions, valuation_date,
        )
        return {
            "positions_with_data": len(self._market_data),
            "avg_quality": round(
                sum(
                    (s.quality_score or 0) for s in self._market_data.values()
                ) / max(len(self._market_data), 1),
                2,
            ),
        }

    async def _step2_run_valuation(
        self,
        positions: list[PositionInput],
    ) -> dict[str, Any]:
        """Step 2: Run pricing models via Agent 2."""
        self._valuations = await self._valuation_runner.price_all(
            positions, self._market_data,
        )

        # Notify per-position progress
        for pos_id, val in self._valuations.items():
            await self._notify(ProgressUpdate(
                run_id=self._run_id,
                event_type="POSITION_PROCESSED",
                step_number=2,
                step_name=IPVStepName.RUN_VALUATION_MODEL,
                position_id=pos_id,
                message=f"Priced {pos_id}: {val.ipv_price} ({val.pricing_method})",
                progress_pct=12.5 + (12.5 * list(self._valuations.keys()).index(pos_id) / max(len(self._valuations), 1)),
            ))

        return {
            "positions_priced": len(self._valuations),
            "agent2_priced": sum(1 for v in self._valuations.values() if v.pricing_source == "agent2"),
            "fallback_priced": sum(1 for v in self._valuations.values() if "fallback" in v.pricing_source),
        }

    async def _step3_compare(
        self,
        positions: list[PositionInput],
    ) -> dict[str, Any]:
        """Step 3: Compare desk marks vs VC independent prices."""
        self._comparisons = self._comparison_engine.compare_all(
            positions, self._valuations,
        )
        green = sum(1 for c in self._comparisons.values() if c.rag_status == RAGStatus.GREEN)
        amber = sum(1 for c in self._comparisons.values() if c.rag_status == RAGStatus.AMBER)
        red = sum(1 for c in self._comparisons.values() if c.rag_status == RAGStatus.RED)
        return {"green": green, "amber": amber, "red": red}

    async def _step4_flag_exceptions(
        self,
        positions: list[PositionInput],
    ) -> dict[str, Any]:
        """Step 4: Flag exceptions for tolerance breaches."""
        self._exceptions = self._exception_generator.flag_all(
            positions, self._comparisons,
        )
        raised = [e for e in self._exceptions.values() if e is not None]
        disputes = sum(1 for e in raised if e.auto_action == "DISPUTE")
        escalations = sum(1 for e in raised if e.auto_action == "ESCALATE")
        return {
            "exceptions_raised": len(raised),
            "auto_disputes": disputes,
            "auto_escalations": escalations,
        }

    async def _step5_investigate(
        self,
        positions: list[PositionInput],
        valuation_date: date,
    ) -> dict[str, Any]:
        """Step 5: Create disputes for RED positions via Agent 4."""
        # Only process exceptions that need disputes
        dispute_positions = [
            pos for pos in positions
            if (
                self._exceptions.get(pos.position_id) is not None
                and self._exceptions[pos.position_id].auto_action in ("DISPUTE", "ESCALATE")
            )
        ]

        disputes_created = 0
        for pos in dispute_positions:
            exc = self._exceptions[pos.position_id]
            comp = self._comparisons[pos.position_id]
            record = await self._escalation_manager.process_exception(
                pos, comp, exc, valuation_date,
            )
            self._escalations[pos.position_id] = record
            if record.dispute_id is not None:
                disputes_created += 1

        # Fill in no-action for positions without exceptions
        for pos in positions:
            if pos.position_id not in self._escalations:
                self._escalations[pos.position_id] = EscalationRecord(
                    position_id=pos.position_id,
                    action="NO_ACTION",
                    reason="Within tolerance or AMBER (monitoring only)",
                )

        return {"disputes_created": disputes_created}

    async def _step6_escalate(
        self,
        positions: list[PositionInput],
        valuation_date: date,
    ) -> dict[str, Any]:
        """Step 6: Escalate material variances to VC Committee."""
        escalated = sum(
            1 for r in self._escalations.values()
            if r.action == "ESCALATED_TO_COMMITTEE"
        )
        return {"committee_escalations": escalated}

    async def _step7_resolve(
        self,
        positions: list[PositionInput],
    ) -> dict[str, Any]:
        """Step 7: Create reserves and adjustments via Agent 5."""
        self._resolutions = await self._resolution_engine.resolve_all(
            positions,
            self._comparisons,
            self._valuations,
            self._exceptions,
            self._escalations,
        )
        reserves_created = sum(
            1 for r in self._resolutions.values() if r.action == "RESERVE_CREATED"
        )
        total_reserves = sum(
            r.reserve_amount for r in self._resolutions.values()
            if r.reserve_amount is not None
        )
        return {
            "reserves_created": reserves_created,
            "total_reserves_usd": str(total_reserves),
        }

    async def _step8_report(
        self,
        valuation_date: date,
    ) -> dict[str, Any]:
        """Step 8: Generate regulatory reports via Agent 6."""
        self._reports = await self._report_trigger.trigger_all_reports(valuation_date)
        generated = sum(1 for r in self._reports if r.status == "GENERATED")
        failed = sum(1 for r in self._reports if r.status == "FAILED")
        return {
            "reports_generated": generated,
            "reports_failed": failed,
            "report_types": [r.report_type for r in self._reports if r.status == "GENERATED"],
        }

    def _build_position_results(
        self,
        positions: list[PositionInput],
    ) -> list[PositionResult]:
        """Build final per-position results from all pipeline data."""
        results: list[PositionResult] = []
        for pos in positions:
            val = self._valuations.get(pos.position_id)
            comp = self._comparisons.get(pos.position_id)
            exc = self._exceptions.get(pos.position_id)
            esc = self._escalations.get(pos.position_id)
            res = self._resolutions.get(pos.position_id)

            if val is None or comp is None:
                # Position couldn't be processed
                category = classify_product(pos.product_type, pos.currency_pair)
                green_threshold, amber_threshold = get_thresholds(category)
                results.append(PositionResult(
                    position_id=pos.position_id,
                    currency_pair=pos.currency_pair,
                    product_type=pos.product_type,
                    notional=pos.notional,
                    desk_mark=pos.desk_mark,
                    ipv_price=pos.desk_mark,
                    difference=Decimal("0"),
                    difference_pct=Decimal("0"),
                    rag_status=RAGStatus.GREEN,
                    fair_value_level=pos.fair_value_level,
                    product_category=category,
                    threshold_green=green_threshold,
                    threshold_amber=amber_threshold,
                    notes="Processing incomplete — missing valuation or comparison",
                ))
                continue

            results.append(PositionResult(
                position_id=pos.position_id,
                currency_pair=pos.currency_pair,
                product_type=pos.product_type,
                notional=pos.notional,
                desk_mark=pos.desk_mark,
                ipv_price=val.ipv_price,
                difference=comp.difference,
                difference_pct=comp.difference_pct,
                rag_status=comp.rag_status,
                fair_value_level=pos.fair_value_level,
                product_category=comp.product_category,
                threshold_green=comp.threshold_green,
                threshold_amber=comp.threshold_amber,
                breach_amount_usd=exc.breach_amount_usd if exc else None,
                exception_raised=exc is not None,
                dispute_id=esc.dispute_id if esc else None,
                escalated=(esc.action == "ESCALATED_TO_COMMITTEE") if esc else False,
                reserve_amount=res.reserve_amount if res else None,
                notes=res.notes if res else None,
            ))

        return results

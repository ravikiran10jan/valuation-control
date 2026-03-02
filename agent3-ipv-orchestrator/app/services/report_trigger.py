"""Step 8: Report.

Triggers regulatory report generation via Agent 6 (Regulatory Reporting).
Generates Pillar 3, IFRS 13, PRA110, and FR Y-14Q reports.
"""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

import structlog

from app.models.schemas import ReportTriggerResult
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class ReportTrigger:
    """Triggers regulatory report generation via Agent 6."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def trigger_pillar3(self, reporting_date: date) -> ReportTriggerResult:
        """Generate Pillar 3 regulatory report."""
        try:
            result = await self._client.generate_pillar3_report(reporting_date)
            report_id = result.get("report_id")
            log.info("report_pillar3_generated", report_id=report_id)
            return ReportTriggerResult(
                report_type="PILLAR3",
                report_id=report_id,
                status="GENERATED",
                details=result,
            )
        except Exception as exc:
            log.error("report_pillar3_failed", error=str(exc))
            return ReportTriggerResult(
                report_type="PILLAR3",
                status="FAILED",
                details={"error": str(exc)},
            )

    async def trigger_ifrs13(self, reporting_date: date) -> ReportTriggerResult:
        """Generate IFRS 13 fair value hierarchy report."""
        try:
            result = await self._client.generate_ifrs13_report(reporting_date)
            report_id = result.get("report_id")
            log.info("report_ifrs13_generated", report_id=report_id)
            return ReportTriggerResult(
                report_type="IFRS13",
                report_id=report_id,
                status="GENERATED",
                details=result,
            )
        except Exception as exc:
            log.error("report_ifrs13_failed", error=str(exc))
            return ReportTriggerResult(
                report_type="IFRS13",
                status="FAILED",
                details={"error": str(exc)},
            )

    async def trigger_pra110(self, reporting_date: date) -> ReportTriggerResult:
        """Generate PRA110 UK regulatory return."""
        try:
            result = await self._client.generate_pra110_report(reporting_date)
            report_id = result.get("report_id")
            log.info("report_pra110_generated", report_id=report_id)
            return ReportTriggerResult(
                report_type="PRA110",
                report_id=report_id,
                status="GENERATED",
                details=result,
            )
        except Exception as exc:
            log.error("report_pra110_failed", error=str(exc))
            return ReportTriggerResult(
                report_type="PRA110",
                status="FAILED",
                details={"error": str(exc)},
            )

    async def trigger_fry14q(self, reporting_date: date) -> ReportTriggerResult:
        """Generate FR Y-14Q Federal Reserve quarterly return."""
        try:
            result = await self._client.generate_fry14q_report(reporting_date)
            report_id = result.get("report_id")
            log.info("report_fry14q_generated", report_id=report_id)
            return ReportTriggerResult(
                report_type="FRY14Q",
                report_id=report_id,
                status="GENERATED",
                details=result,
            )
        except Exception as exc:
            log.error("report_fry14q_failed", error=str(exc))
            return ReportTriggerResult(
                report_type="FRY14Q",
                status="FAILED",
                details={"error": str(exc)},
            )

    async def trigger_all_reports(
        self,
        reporting_date: date,
    ) -> list[ReportTriggerResult]:
        """Trigger generation of all regulatory reports concurrently.

        Generates:
          1. Pillar 3 (Basel III)
          2. IFRS 13 (Fair Value Hierarchy)
          3. PRA110 (UK Regulatory)
          4. FR Y-14Q (US Federal Reserve)
        """
        log.info("report_trigger_all_start", reporting_date=reporting_date.isoformat())

        results = await asyncio.gather(
            self.trigger_pillar3(reporting_date),
            self.trigger_ifrs13(reporting_date),
            self.trigger_pra110(reporting_date),
            self.trigger_fry14q(reporting_date),
            return_exceptions=True,
        )

        report_results: list[ReportTriggerResult] = []
        report_types = ["PILLAR3", "IFRS13", "PRA110", "FRY14Q"]

        for rtype, result in zip(report_types, results):
            if isinstance(result, Exception):
                log.error("report_trigger_exception", report_type=rtype, error=str(result))
                report_results.append(
                    ReportTriggerResult(
                        report_type=rtype,
                        status="FAILED",
                        details={"error": str(result)},
                    )
                )
            else:
                report_results.append(result)

        generated = sum(1 for r in report_results if r.status == "GENERATED")
        failed = sum(1 for r in report_results if r.status == "FAILED")
        log.info(
            "report_trigger_all_complete",
            generated=generated,
            failed=failed,
        )

        return report_results

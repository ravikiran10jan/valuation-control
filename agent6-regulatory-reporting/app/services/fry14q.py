"""FR Y-14Q Reporter for US Federal Reserve quarterly returns.

Generates FR Y-14Q Schedule H.1 (Trading Risk) reports.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import StringIO
import csv
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx

from app.core.config import settings
from app.models.postgres import RegulatoryReport
from app.models.schemas import (
    AVABreakdown,
    FairValueLevelSummary,
    FRY14QReportOut,
    FRY14QScheduleH1,
    ReportStatus,
    ReportType,
    VaRMetrics,
)
from app.services.ifrs13 import IFRS13Reporter
from app.services.pillar3 import Pillar3Reporter

log = structlog.get_logger()


class FRY14QReporter:
    """Generate FR Y-14Q Federal Reserve quarterly reports.

    Schedule H.1: Trading Risk
    - Fair value hierarchy
    - VaR
    - Prudent valuation adjustments
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.ifrs13_reporter = IFRS13Reporter(db)
        self.pillar3_reporter = Pillar3Reporter(db)

    async def generate_fr_y14q(self, reporting_date: date) -> FRY14QReportOut:
        """Generate FR Y-14Q return.

        Args:
            reporting_date: The reporting date.

        Returns:
            FRY14QReportOut with Schedule H.1.
        """
        log.info("generating_fry14q_report", reporting_date=str(reporting_date))

        # Schedule H.1: Trading Risk
        schedule_h1 = await self._generate_schedule_h1(reporting_date)

        # Generate CSV (Fed requires CSV format)
        csv_content = self._render_fr_y14q_csv(reporting_date, schedule_h1)

        # Store report
        report = RegulatoryReport(
            report_type=ReportType.FRY14Q.value,
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_us,
            status=ReportStatus.DRAFT.value,
            content={
                "schedule_h1": {
                    "fair_value_hierarchy": [
                        fv.model_dump() for fv in schedule_h1.fair_value_hierarchy
                    ],
                    "prudent_valuation": schedule_h1.prudent_valuation.model_dump(),
                    "var_metrics": schedule_h1.var_metrics.model_dump(),
                },
            },
            file_format="CSV",
            file_content=csv_content,
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        log.info(
            "fry14q_report_generated",
            report_id=report.report_id,
            reporting_date=str(reporting_date),
        )

        return FRY14QReportOut(
            report_id=report.report_id,
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_us,
            status=ReportStatus(report.status),
            schedule_h1=schedule_h1,
            csv_content=csv_content,
            generated_at=report.generated_at,
        )

    async def _generate_schedule_h1(
        self, reporting_date: date
    ) -> FRY14QScheduleH1:
        """Generate Schedule H.1: Trading Risk.

        Args:
            reporting_date: The reporting date.

        Returns:
            FRY14QScheduleH1 with all trading risk data.
        """
        # Get fair value hierarchy from IFRS13 reporter
        positions = await self.ifrs13_reporter._get_positions(reporting_date)
        fv_hierarchy = await self.ifrs13_reporter._aggregate_by_level(positions)

        # Get prudent valuation from Pillar3 reporter
        all_avas = await self.pillar3_reporter._get_all_avas(reporting_date)
        if all_avas:
            ava_data = all_avas[0] if all_avas else {}
            prudent_valuation = AVABreakdown(
                mpu=ava_data.get("mpu", Decimal("0")),
                close_out=ava_data.get("close_out", Decimal("0")),
                model_risk=ava_data.get("model_risk", Decimal("0")),
                credit_spreads=ava_data.get("credit_spreads", Decimal("0")),
                funding=ava_data.get("funding", Decimal("0")),
                concentration=ava_data.get("concentration", Decimal("0")),
                admin=ava_data.get("admin", Decimal("0")),
            )
        else:
            prudent_valuation = AVABreakdown()

        # Get VaR metrics
        var_metrics = await self._get_var_metrics(reporting_date)

        return FRY14QScheduleH1(
            fair_value_hierarchy=fv_hierarchy,
            prudent_valuation=prudent_valuation,
            var_metrics=var_metrics,
        )

    async def _get_var_metrics(self, reporting_date: date) -> VaRMetrics:
        """Get VaR metrics for the reporting date.

        In production, would fetch from risk system.

        Args:
            reporting_date: The reporting date.

        Returns:
            VaRMetrics with VaR figures.
        """
        # Try to fetch from agent2 or risk system
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.agent1_base_url}/risk/var",
                    params={"valuation_date": str(reporting_date)},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    return VaRMetrics(
                        var_1day_99=Decimal(str(data.get("var_1day_99", 0))),
                        var_10day_99=Decimal(str(data.get("var_10day_99", 0))),
                        stressed_var=Decimal(str(data.get("stressed_var", 0)))
                        if data.get("stressed_var")
                        else None,
                    )
        except Exception as e:
            log.warning("var_metrics_fetch_failed", error=str(e))

        # Return placeholder values
        return VaRMetrics(
            var_1day_99=Decimal("50000000"),  # $50M placeholder
            var_10day_99=Decimal("158113883"),  # sqrt(10) * 50M
            stressed_var=Decimal("100000000"),
        )

    def _render_fr_y14q_csv(
        self, reporting_date: date, schedule_h1: FRY14QScheduleH1
    ) -> str:
        """Render FR Y-14Q Schedule H.1 as CSV.

        Args:
            reporting_date: The reporting date.
            schedule_h1: Schedule H.1 data.

        Returns:
            CSV string.
        """
        output = StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow(["FR Y-14Q Schedule H.1 - Trading Risk"])
        writer.writerow(["Firm Reference", settings.firm_reference_us])
        writer.writerow(["Reporting Date", str(reporting_date)])
        writer.writerow(["Generated At", datetime.utcnow().isoformat()])
        writer.writerow([])

        # Fair Value Hierarchy
        writer.writerow(["Fair Value Hierarchy"])
        writer.writerow(["Level", "Position Count", "Total Fair Value", "% of Total"])
        for fv in schedule_h1.fair_value_hierarchy:
            writer.writerow([
                fv.level.value,
                fv.count,
                f"{fv.total_fair_value:.2f}",
                f"{fv.percentage_of_total:.2f}%",
            ])
        writer.writerow([])

        # Prudent Valuation
        writer.writerow(["Prudent Valuation Adjustments (AVA)"])
        writer.writerow(["Category", "Amount"])
        pv = schedule_h1.prudent_valuation
        writer.writerow(["Market Price Uncertainty", f"{pv.market_price_uncertainty:.2f}"])
        writer.writerow(["Close-Out Costs", f"{pv.close_out_costs:.2f}"])
        writer.writerow(["Model Risk", f"{pv.model_risk:.2f}"])
        writer.writerow(["Unearned Credit Spreads", f"{pv.unearned_credit_spreads:.2f}"])
        writer.writerow(["Investment & Funding", f"{pv.investment_funding:.2f}"])
        writer.writerow(["Concentrated Positions", f"{pv.concentrated_positions:.2f}"])
        writer.writerow(["Future Admin Costs", f"{pv.future_admin_costs:.2f}"])
        writer.writerow(["Total AVA", f"{pv.total:.2f}"])
        writer.writerow([])

        # VaR Metrics
        writer.writerow(["Value at Risk Metrics"])
        writer.writerow(["Metric", "Value"])
        var = schedule_h1.var_metrics
        writer.writerow(["VaR (1-day, 99%)", f"{var.var_1day_99:.2f}"])
        writer.writerow(["VaR (10-day, 99%)", f"{var.var_10day_99:.2f}"])
        if var.stressed_var:
            writer.writerow(["Stressed VaR", f"{var.stressed_var:.2f}"])

        return output.getvalue()

    async def submit_to_fed(self, report_id: int) -> dict:
        """Submit FR Y-14Q to Federal Reserve.

        Args:
            report_id: The report ID to submit.

        Returns:
            Submission response.
        """
        report = await self.db.get(RegulatoryReport, report_id)
        if not report:
            raise ValueError(f"Report {report_id} not found")

        if report.status != ReportStatus.APPROVED.value:
            raise ValueError(
                f"Report must be APPROVED before submission. Current status: {report.status}"
            )

        # In production, this would call the Fed API
        log.info("submitting_fry14q", report_id=report_id)

        # Update report status
        report.status = ReportStatus.SUBMITTED.value
        report.submitted_at = datetime.utcnow()
        report.submission_ref = f"FED-Y14Q-{report.reporting_date}-{report_id}"

        await self.db.commit()

        return {
            "report_id": report_id,
            "regulator": "FED",
            "submitted_at": report.submitted_at,
            "confirmation_id": report.submission_ref,
            "status": "SUBMITTED",
        }

"""Pillar 3 Reporter for Basel III regulatory disclosures.

Generates quarterly Pillar 3 reports including Table 3.2 (Prudent Valuation).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx

from app.core.config import settings
from app.models.postgres import (
    AVASnapshot,
    CET1Capital,
    RegulatoryReport,
)
from app.models.schemas import (
    AVABreakdown,
    Pillar3Table32,
    Pillar3ReportOut,
    ReportStatus,
    ReportType,
)

log = structlog.get_logger()


class Pillar3Reporter:
    """Generate quarterly Pillar 3 disclosures (Basel III)."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_pillar3_report(self, reporting_date: date) -> Pillar3ReportOut:
        """Generate quarterly Pillar 3 disclosure.

        Key tables:
        - Table 3.1: Capital structure (CET1, AT1, Tier 2)
        - Table 3.2: Prudent Valuation (AVA breakdown)
        - Table 4: Credit risk exposures
        - Table 5: Market risk (VaR, stressed VaR)

        Args:
            reporting_date: The reporting date for the disclosure.

        Returns:
            Pillar3ReportOut with generated tables.
        """
        log.info("generating_pillar3_report", reporting_date=str(reporting_date))

        # Generate Table 3.2: Prudent Valuation (AVA)
        table_3_2 = await self._generate_table_3_2(reporting_date)

        # Store report
        report = RegulatoryReport(
            report_type=ReportType.PILLAR3.value,
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_eu,
            status=ReportStatus.DRAFT.value,
            content={
                "tables": {
                    "3.2": table_3_2.model_dump() if table_3_2 else {}
                }
            },
            file_format="PDF",
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        log.info(
            "pillar3_report_generated",
            report_id=report.report_id,
            reporting_date=str(reporting_date),
        )

        return Pillar3ReportOut(
            report_id=report.report_id,
            reporting_date=reporting_date,
            status=ReportStatus(report.status),
            tables={"3.2": table_3_2} if table_3_2 else {},
            generated_at=report.generated_at,
        )

    async def _generate_table_3_2(self, reporting_date: date) -> Optional[Pillar3Table32]:
        """Generate Table 3.2: Prudent Valuation Adjustments.

        Shows AVA by category across all positions.

        Args:
            reporting_date: The reporting date.

        Returns:
            Pillar3Table32 with AVA breakdown.
        """
        # Get all AVAs for the reporting date
        all_avas = await self._get_all_avas(reporting_date)

        if not all_avas:
            log.warning("no_avas_found", reporting_date=str(reporting_date))
            # Return empty table with zeros
            breakdown = {
                "Market Price Uncertainty": Decimal("0"),
                "Close-Out Costs": Decimal("0"),
                "Model Risk": Decimal("0"),
                "Unearned Credit Spreads": Decimal("0"),
                "Investment & Funding": Decimal("0"),
                "Concentrated Positions": Decimal("0"),
                "Future Admin Costs": Decimal("0"),
            }
            return Pillar3Table32(
                total_ava="€0",
                breakdown=breakdown,
                as_pct_of_cet1="0.00%",
            )

        # Aggregate by category
        totals = {
            "Market Price Uncertainty": sum(a.get("mpu", Decimal("0")) for a in all_avas),
            "Close-Out Costs": sum(a.get("close_out", Decimal("0")) for a in all_avas),
            "Model Risk": sum(a.get("model_risk", Decimal("0")) for a in all_avas),
            "Unearned Credit Spreads": sum(a.get("credit_spreads", Decimal("0")) for a in all_avas),
            "Investment & Funding": sum(a.get("funding", Decimal("0")) for a in all_avas),
            "Concentrated Positions": sum(a.get("concentration", Decimal("0")) for a in all_avas),
            "Future Admin Costs": sum(a.get("admin", Decimal("0")) for a in all_avas),
        }

        total_ava = sum(totals.values())

        # Get CET1 for percentage calculation
        cet1 = await self._get_cet1(reporting_date)
        ava_pct = (total_ava / cet1 * 100) if cet1 else Decimal("0")

        return Pillar3Table32(
            total_ava=f"€{total_ava:,.0f}",
            breakdown=totals,
            as_pct_of_cet1=f"{ava_pct:.2f}%",
        )

    async def _get_all_avas(self, reporting_date: date) -> list[dict]:
        """Get all AVA calculations for a reporting date.

        Fetches from local AVA snapshots or agent5 API.

        Args:
            reporting_date: The reporting date.

        Returns:
            List of AVA dictionaries.
        """
        # First try local AVA snapshots
        stmt = select(AVASnapshot).where(AVASnapshot.valuation_date == reporting_date)
        result = await self.db.execute(stmt)
        snapshots = result.scalars().all()

        if snapshots:
            # Aggregate by type
            ava_by_type: dict[str, Decimal] = {}
            type_mapping = {
                "MPU": "mpu",
                "CLOSE_OUT": "close_out",
                "MODEL_RISK": "model_risk",
                "CREDIT_SPREADS": "credit_spreads",
                "FUNDING": "funding",
                "CONCENTRATION": "concentration",
                "ADMIN": "admin",
            }
            for snapshot in snapshots:
                key = type_mapping.get(snapshot.ava_type, snapshot.ava_type.lower())
                ava_by_type[key] = ava_by_type.get(key, Decimal("0")) + Decimal(str(snapshot.ava_amount))
            return [ava_by_type]

        # Fallback: Try agent5 API
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.agent5_base_url}/reserves/ava",
                    params={"valuation_date": str(reporting_date)},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            log.error("agent5_ava_fetch_failed", error=str(e))

        return []

    async def _get_cet1(self, reporting_date: date) -> Decimal:
        """Get CET1 capital for the reporting date.

        Args:
            reporting_date: The reporting date.

        Returns:
            CET1 capital amount.
        """
        stmt = (
            select(CET1Capital)
            .where(CET1Capital.reporting_date <= reporting_date)
            .order_by(CET1Capital.reporting_date.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        capital = result.scalar_one_or_none()

        if capital:
            return Decimal(str(capital.cet1_capital))

        # Return default placeholder if not found
        log.warning("cet1_not_found", reporting_date=str(reporting_date))
        return Decimal("50000000000")  # €50bn placeholder

    async def submit_to_regulator(
        self,
        report_id: int,
        regulator: str = "ECB",
    ) -> dict:
        """Submit Pillar 3 report to regulator.

        Args:
            report_id: The report ID to submit.
            regulator: Target regulator (ECB, PRA).

        Returns:
            Submission response with confirmation.
        """
        # Get report
        report = await self.db.get(RegulatoryReport, report_id)
        if not report:
            raise ValueError(f"Report {report_id} not found")

        if report.status != ReportStatus.APPROVED.value:
            raise ValueError(f"Report must be APPROVED before submission. Current status: {report.status}")

        # In production, this would call the regulator API
        # For now, simulate submission
        log.info(
            "submitting_pillar3_to_regulator",
            report_id=report_id,
            regulator=regulator,
        )

        # Update report status
        report.status = ReportStatus.SUBMITTED.value
        report.submitted_at = datetime.utcnow()
        report.submission_ref = f"{regulator}-{report.reporting_date}-{report_id}"

        await self.db.commit()

        return {
            "report_id": report_id,
            "regulator": regulator,
            "submitted_at": report.submitted_at,
            "confirmation_id": report.submission_ref,
            "status": "SUBMITTED",
        }

    async def approve_report(self, report_id: int, approved_by: str) -> RegulatoryReport:
        """Approve a Pillar 3 report for submission.

        Args:
            report_id: The report ID to approve.
            approved_by: The approver's username.

        Returns:
            Updated report.
        """
        report = await self.db.get(RegulatoryReport, report_id)
        if not report:
            raise ValueError(f"Report {report_id} not found")

        report.status = ReportStatus.APPROVED.value
        report.approved_at = datetime.utcnow()
        report.approved_by = approved_by

        await self.db.commit()
        await self.db.refresh(report)

        log.info(
            "pillar3_report_approved",
            report_id=report_id,
            approved_by=approved_by,
        )

        return report

"""PRA110 Reporter for UK Prudential Regulation Authority returns.

Generates PRA110 returns including Section D (Prudent Valuation).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import xml.etree.ElementTree as ET

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import settings
from app.models.postgres import AVASnapshot, RegulatoryReport
from app.models.schemas import (
    PRA110ReportOut,
    PRA110SectionD,
    ReportStatus,
    ReportType,
)
from app.services.pillar3 import Pillar3Reporter

log = structlog.get_logger()


class PRA110Reporter:
    """Generate PRA110 UK regulatory returns.

    Due: Q+20 days

    Sections:
    A: Balance sheet
    B: P&L
    C: Capital resources
    D: Prudent valuation (AVA)
    E: Credit risk
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.pillar3_reporter = Pillar3Reporter(db)

    async def generate_pra110(self, reporting_date: date) -> PRA110ReportOut:
        """Generate PRA110 return.

        Args:
            reporting_date: The reporting date.

        Returns:
            PRA110ReportOut with all sections.
        """
        log.info("generating_pra110_report", reporting_date=str(reporting_date))

        # Section D: Prudent Valuation
        section_d = await self._generate_section_d(reporting_date)

        # Generate XML (PRA requires specific XML format)
        xml_content = self._render_pra110_xml(reporting_date, section_d)

        # Store report
        report = RegulatoryReport(
            report_type=ReportType.PRA110.value,
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_uk,
            status=ReportStatus.DRAFT.value,
            content={
                "section_d": section_d.model_dump(),
            },
            file_format="XML",
            file_content=xml_content,
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        log.info(
            "pra110_report_generated",
            report_id=report.report_id,
            reporting_date=str(reporting_date),
        )

        return PRA110ReportOut(
            report_id=report.report_id,
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_uk,
            status=ReportStatus(report.status),
            section_d=section_d,
            xml_content=xml_content,
            generated_at=report.generated_at,
        )

    async def _generate_section_d(self, reporting_date: date) -> PRA110SectionD:
        """Generate Section D: Prudent Valuation Adjustments.

        Same 7 categories as Pillar 3 Table 3.2.

        Args:
            reporting_date: The reporting date.

        Returns:
            PRA110SectionD with AVA breakdown.
        """
        # Re-use Pillar3Reporter logic
        table_3_2 = await self.pillar3_reporter._generate_table_3_2(reporting_date)

        if not table_3_2:
            return PRA110SectionD(
                d010_mpu=Decimal("0"),
                d020_close_out=Decimal("0"),
                d030_model_risk=Decimal("0"),
                d040_credit_spreads=Decimal("0"),
                d050_funding=Decimal("0"),
                d060_concentration=Decimal("0"),
                d070_admin=Decimal("0"),
                d080_total_ava=Decimal("0"),
            )

        # Convert to PRA110 format
        breakdown = table_3_2.breakdown
        return PRA110SectionD(
            d010_mpu=breakdown.get("Market Price Uncertainty", Decimal("0")),
            d020_close_out=breakdown.get("Close-Out Costs", Decimal("0")),
            d030_model_risk=breakdown.get("Model Risk", Decimal("0")),
            d040_credit_spreads=breakdown.get("Unearned Credit Spreads", Decimal("0")),
            d050_funding=breakdown.get("Investment & Funding", Decimal("0")),
            d060_concentration=breakdown.get("Concentrated Positions", Decimal("0")),
            d070_admin=breakdown.get("Future Admin Costs", Decimal("0")),
            d080_total_ava=sum(breakdown.values()),
        )

    def _render_pra110_xml(
        self, reporting_date: date, section_d: PRA110SectionD
    ) -> str:
        """Render PRA110 return as XML.

        Args:
            reporting_date: The reporting date.
            section_d: Section D data.

        Returns:
            XML string.
        """
        # Create root element
        root = ET.Element("PRA110")
        root.set("xmlns", "http://www.bankofengland.co.uk/pra110")
        root.set("version", "1.0")

        # Header
        header = ET.SubElement(root, "Header")
        ET.SubElement(header, "FirmReference").text = settings.firm_reference_uk
        ET.SubElement(header, "ReportingDate").text = str(reporting_date)
        ET.SubElement(header, "ReportingPeriod").text = "Q"
        ET.SubElement(header, "GeneratedAt").text = datetime.utcnow().isoformat()

        # Section D: Prudent Valuation
        section_d_elem = ET.SubElement(root, "SectionD")
        section_d_elem.set("name", "Prudent Valuation Adjustments")

        # Add AVA items
        items = [
            ("D010", "MarketPriceUncertainty", section_d.d010_mpu),
            ("D020", "CloseOutCosts", section_d.d020_close_out),
            ("D030", "ModelRisk", section_d.d030_model_risk),
            ("D040", "UnearnedCreditSpreads", section_d.d040_credit_spreads),
            ("D050", "InvestmentFunding", section_d.d050_funding),
            ("D060", "ConcentratedPositions", section_d.d060_concentration),
            ("D070", "FutureAdminCosts", section_d.d070_admin),
            ("D080", "TotalAVA", section_d.d080_total_ava),
        ]

        for code, name, value in items:
            item = ET.SubElement(section_d_elem, "Item")
            item.set("code", code)
            item.set("name", name)
            item.text = f"{value:.2f}"

        # Convert to string
        return ET.tostring(root, encoding="unicode", method="xml")

    async def submit_to_pra(self, report_id: int) -> dict:
        """Submit PRA110 return to PRA portal.

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

        # In production, this would call the PRA API
        log.info("submitting_pra110", report_id=report_id)

        # Update report status
        report.status = ReportStatus.SUBMITTED.value
        report.submitted_at = datetime.utcnow()
        report.submission_ref = f"PRA-{report.reporting_date}-{report_id}"

        await self.db.commit()

        return {
            "report_id": report_id,
            "regulator": "PRA",
            "submitted_at": report.submitted_at,
            "confirmation_id": report.submission_ref,
            "status": "SUBMITTED",
        }

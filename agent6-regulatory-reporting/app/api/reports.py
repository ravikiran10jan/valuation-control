"""API endpoints for regulatory reporting."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    AuditEventOut,
    AuditEventType,
    AuditReportOut,
    AuditTrailQuery,
    CapitalAdequacyRequest,
    CapitalAdequacyResult,
    FRY14QReportOut,
    IFRS13ReportOut,
    Pillar3ReportOut,
    PRA110ReportOut,
    ReportGenerationStatus,
    ReportSubmissionRequest,
    ReportSubmissionResponse,
    ReportType,
)
from app.services.audit_trail import AuditTrail, log_event
from app.services.capital_adequacy import CapitalAdequacyService
from app.services.fry14q import FRY14QReporter
from app.services.ifrs13 import IFRS13Reporter
from app.services.pillar3 import Pillar3Reporter
from app.services.pra110 import PRA110Reporter
from app.services.pva_level3 import PVALevel3Reporter

router = APIRouter(prefix="/reports", tags=["regulatory-reports"])
audit_router = APIRouter(prefix="/audit", tags=["audit-trail"])


# ── Pillar 3 Endpoints ────────────────────────────────────────────
@router.post("/pillar3", response_model=Pillar3ReportOut)
async def generate_pillar3(
    reporting_date: date,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Pillar3ReportOut:
    """Generate Pillar 3 regulatory report.

    Generates quarterly Basel III Pillar 3 disclosure including
    Table 3.2 (Prudent Valuation Adjustments).
    """
    reporter = Pillar3Reporter(db)
    report = await reporter.generate_pillar3_report(reporting_date)

    # Log audit event
    await log_event(
        db,
        AuditEventType.REPORT_GENERATED,
        user=request.headers.get("X-User-ID", "system"),
        details={
            "report_type": "PILLAR3",
            "report_id": report.report_id,
            "reporting_date": str(reporting_date),
        },
        ip_address=request.client.host if request.client else None,
    )

    return report


@router.post("/pillar3/{report_id}/approve")
async def approve_pillar3(
    report_id: int,
    approved_by: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approve a Pillar 3 report for submission."""
    reporter = Pillar3Reporter(db)
    try:
        report = await reporter.approve_report(report_id, approved_by)

        # Log audit event
        await log_event(
            db,
            AuditEventType.REPORT_GENERATED,
            user=approved_by,
            details={
                "action": "APPROVE",
                "report_type": "PILLAR3",
                "report_id": report_id,
            },
            ip_address=request.client.host if request.client else None,
        )

        return {"status": "APPROVED", "report_id": report_id, "approved_by": approved_by}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/pillar3/{report_id}/submit", response_model=ReportSubmissionResponse)
async def submit_pillar3(
    report_id: int,
    regulator: str = "ECB",
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> ReportSubmissionResponse:
    """Submit Pillar 3 report to regulator."""
    reporter = Pillar3Reporter(db)
    try:
        result = await reporter.submit_to_regulator(report_id, regulator)

        # Log audit event
        if request:
            await log_event(
                db,
                AuditEventType.REPORT_SUBMITTED,
                user=request.headers.get("X-User-ID", "system"),
                details={
                    "report_type": "PILLAR3",
                    "report_id": report_id,
                    "regulator": regulator,
                    "confirmation_id": result.get("confirmation_id"),
                },
                ip_address=request.client.host if request.client else None,
            )

        return ReportSubmissionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── IFRS 13 Endpoints ─────────────────────────────────────────────
@router.post("/ifrs13", response_model=IFRS13ReportOut)
async def generate_ifrs13(
    reporting_date: date,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> IFRS13ReportOut:
    """Generate IFRS 13 fair value hierarchy report.

    Includes fair value levels, Level 3 reconciliation,
    and valuation techniques disclosure.
    """
    reporter = IFRS13Reporter(db)
    report = await reporter.generate_fair_value_hierarchy(reporting_date)

    # Log audit event
    await log_event(
        db,
        AuditEventType.REPORT_GENERATED,
        user=request.headers.get("X-User-ID", "system"),
        details={
            "report_type": "IFRS13",
            "report_id": report.report_id,
            "reporting_date": str(reporting_date),
        },
        ip_address=request.client.host if request.client else None,
    )

    return report


# ── PRA110 Endpoints ──────────────────────────────────────────────
@router.post("/pra110", response_model=PRA110ReportOut)
async def generate_pra110(
    reporting_date: date,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PRA110ReportOut:
    """Generate PRA110 UK regulatory return.

    Generates Section D (Prudent Valuation) with XML output.
    """
    reporter = PRA110Reporter(db)
    report = await reporter.generate_pra110(reporting_date)

    # Log audit event
    await log_event(
        db,
        AuditEventType.REPORT_GENERATED,
        user=request.headers.get("X-User-ID", "system"),
        details={
            "report_type": "PRA110",
            "report_id": report.report_id,
            "reporting_date": str(reporting_date),
        },
        ip_address=request.client.host if request.client else None,
    )

    return report


@router.post("/pra110/{report_id}/submit", response_model=ReportSubmissionResponse)
async def submit_pra110(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReportSubmissionResponse:
    """Submit PRA110 return to PRA."""
    reporter = PRA110Reporter(db)
    try:
        result = await reporter.submit_to_pra(report_id)

        # Log audit event
        await log_event(
            db,
            AuditEventType.REPORT_SUBMITTED,
            user=request.headers.get("X-User-ID", "system"),
            details={
                "report_type": "PRA110",
                "report_id": report_id,
                "regulator": "PRA",
                "confirmation_id": result.get("confirmation_id"),
            },
            ip_address=request.client.host if request.client else None,
        )

        return ReportSubmissionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pra110/{report_id}/xml")
async def get_pra110_xml(
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download PRA110 report as XML file."""
    from app.models.postgres import RegulatoryReport

    report = await db.get(RegulatoryReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    if report.report_type != ReportType.PRA110.value:
        raise HTTPException(status_code=400, detail="Report is not a PRA110 return")

    return Response(
        content=report.file_content or "",
        media_type="application/xml",
        headers={
            "Content-Disposition": f"attachment; filename=PRA110_{report.reporting_date}.xml"
        },
    )


# ── FR Y-14Q Endpoints ────────────────────────────────────────────
# ── PVA Level 3 Summary Endpoints ─────────────────────────────
@router.post("/pva-level3")
async def generate_pva_level3(
    reporting_date: date,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate PVA Level 3 Summary report.

    Generates quarterly Pillar 3 disclosure for Level 3 positions,
    as required by CRR Article 105 / EBA Guidelines.

    Includes:
    - Table 1: Level 3 Fair Value Positions by Product Type
    - Table 2: AVA Components for Level 3 Positions
    - Table 3: Level 3 AVA Quarterly Reconciliation
    """
    reporter = PVALevel3Reporter(db)
    report = await reporter.generate_pva_level3_report(reporting_date)

    # Log audit event
    await log_event(
        db,
        AuditEventType.REPORT_GENERATED,
        user=request.headers.get("X-User-ID", "system"),
        details={
            "report_type": "PVA_LEVEL3",
            "report_id": report.get("report_id"),
            "reporting_date": str(reporting_date),
        },
        ip_address=request.client.host if request.client else None,
    )

    return report


# ── FR Y-14Q Endpoints ────────────────────────────────────────
@router.post("/fry14q", response_model=FRY14QReportOut)
async def generate_fry14q(
    reporting_date: date,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> FRY14QReportOut:
    """Generate FR Y-14Q Federal Reserve quarterly return.

    Generates Schedule H.1 (Trading Risk) with CSV output.
    """
    reporter = FRY14QReporter(db)
    report = await reporter.generate_fr_y14q(reporting_date)

    # Log audit event
    await log_event(
        db,
        AuditEventType.REPORT_GENERATED,
        user=request.headers.get("X-User-ID", "system"),
        details={
            "report_type": "FRY14Q",
            "report_id": report.report_id,
            "reporting_date": str(reporting_date),
        },
        ip_address=request.client.host if request.client else None,
    )

    return report


@router.post("/fry14q/{report_id}/submit", response_model=ReportSubmissionResponse)
async def submit_fry14q(
    report_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ReportSubmissionResponse:
    """Submit FR Y-14Q to Federal Reserve."""
    reporter = FRY14QReporter(db)
    try:
        result = await reporter.submit_to_fed(report_id)

        # Log audit event
        await log_event(
            db,
            AuditEventType.REPORT_SUBMITTED,
            user=request.headers.get("X-User-ID", "system"),
            details={
                "report_type": "FRY14Q",
                "report_id": report_id,
                "regulator": "FED",
                "confirmation_id": result.get("confirmation_id"),
            },
            ip_address=request.client.host if request.client else None,
        )

        return ReportSubmissionResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/fry14q/{report_id}/csv")
async def get_fry14q_csv(
    report_id: int,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download FR Y-14Q report as CSV file."""
    from app.models.postgres import RegulatoryReport

    report = await db.get(RegulatoryReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    if report.report_type != ReportType.FRY14Q.value:
        raise HTTPException(status_code=400, detail="Report is not an FR Y-14Q return")

    return Response(
        content=report.file_content or "",
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=FRY14Q_{report.reporting_date}.csv"
        },
    )


# ── Capital Adequacy Endpoints ───────────────────────────────────
@router.post("/capital-adequacy", response_model=CapitalAdequacyResult)
async def generate_capital_adequacy(
    req: CapitalAdequacyRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CapitalAdequacyResult:
    """Generate capital adequacy report matching Excel Capital_Adequacy sheet.

    Calculates:
      - CET1 Capital from equity components and deductions (including AVA)
      - RWA across credit risk, market risk, and operational risk
      - Capital ratios (CET1, leverage) vs regulatory minimums
      - Pass/fail assessment against Basel III requirements

    Excel example with defaults:
      CET1 = $70,465,575
      Total RWA = $297,860,000
      CET1 Ratio = 23.7%
      Min required: 4.5% -> PASS
    """
    service = CapitalAdequacyService(db)
    result = await service.calculate_capital_adequacy(req)

    # Log audit event
    await log_event(
        db,
        AuditEventType.CAPITAL_ADEQUACY_CALCULATED,
        user=request.headers.get("X-User-ID", "system"),
        details={
            "report_type": "CAPITAL_ADEQUACY",
            "report_id": result.report_id,
            "reporting_date": str(req.reporting_date),
            "total_cet1": float(result.total_cet1),
            "total_rwa": float(result.total_rwa),
            "cet1_ratio_pct": float(result.cet1_ratio_pct),
            "passes_minimum": result.capital_ratios.passes_minimum,
            "passes_with_buffers": result.capital_ratios.passes_with_ccyb,
        },
        ip_address=request.client.host if request.client else None,
    )

    await db.commit()
    return result


@router.get("/capital-adequacy/latest", response_model=CapitalAdequacyResult)
async def get_latest_capital_adequacy(
    reporting_date: Optional[date] = None,
    db: AsyncSession = Depends(get_db),
) -> CapitalAdequacyResult:
    """Get the latest capital adequacy report.

    If reporting_date is provided, returns the report for that specific date.
    Otherwise returns the most recent report available.
    """
    service = CapitalAdequacyService(db)
    result = await service.get_latest_report(reporting_date)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No capital adequacy report found"
                + (f" for {reporting_date}" if reporting_date else "")
                + ". Generate one first using POST /reports/capital-adequacy."
            ),
        )

    return result


# ── Audit Trail Endpoints ─────────────────────────────────────────
@audit_router.get("/trail", response_model=list[AuditEventOut])
async def get_audit_trail(
    start_date: date,
    end_date: date,
    event_type: Optional[AuditEventType] = None,
    user: Optional[str] = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> list[AuditEventOut]:
    """Query audit trail with filters.

    Returns audit events matching the specified criteria.
    """
    audit_trail = AuditTrail(db)
    query = AuditTrailQuery(
        start_date=start_date,
        end_date=end_date,
        event_type=event_type,
        user=user,
        limit=limit,
        offset=offset,
    )
    return await audit_trail.query_audit_events(query)


@audit_router.get("/trail/{event_id}", response_model=AuditEventOut)
async def get_audit_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
) -> AuditEventOut:
    """Get a single audit event by ID."""
    audit_trail = AuditTrail(db)
    event = await audit_trail.get_audit_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"Audit event {event_id} not found")
    return event


@audit_router.get("/report", response_model=AuditReportOut)
async def get_audit_report(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
) -> AuditReportOut:
    """Generate audit report for a period.

    Returns summary and detailed events for external auditors.
    """
    audit_trail = AuditTrail(db)
    return await audit_trail.generate_audit_report(start_date, end_date)


@audit_router.get("/report/excel")
async def download_audit_report_excel(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Download audit report as Excel file."""
    audit_trail = AuditTrail(db)
    try:
        excel_bytes = await audit_trail.export_audit_report_excel(start_date, end_date)
        return Response(
            content=excel_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=AuditReport_{start_date}_{end_date}.xlsx"
            },
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Excel export requires openpyxl. Install with: pip install openpyxl",
        )


@audit_router.get("/statistics")
async def get_audit_statistics(
    start_date: date,
    end_date: date,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get audit event statistics for a period."""
    audit_trail = AuditTrail(db)
    return await audit_trail.get_event_statistics(start_date, end_date)

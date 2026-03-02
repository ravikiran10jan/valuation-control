"""Reports and Audit routes — proxy to Agent 6 (Regulatory Reporting).

Provides regulatory report generation (Pillar 3, IFRS 13, PRA110, FR Y-14Q),
submission workflows, and comprehensive audit trail functionality.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.upstream import agent6_get, agent6_post, get_client
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["Reports & Audit"])


# ═══════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════


# ── Generic Reports ─────────────────────────────────────────────


@router.get("/reports")
async def list_reports() -> list[dict[str, Any]]:
    """List available report types and recent reports.

    Returns static list of supported report types.
    """
    return [
        {
            "id": "pillar3",
            "name": "Pillar 3 Disclosure",
            "description": "Basel III prudent valuation adjustments (Table 3.2)",
            "frequency": "quarterly",
            "regulator": "ECB/PRA",
        },
        {
            "id": "ifrs13",
            "name": "IFRS 13 Fair Value Hierarchy",
            "description": "Fair value classification and Level 3 reconciliation",
            "frequency": "quarterly",
            "regulator": "IFRS Foundation",
        },
        {
            "id": "pra110",
            "name": "PRA110 Return",
            "description": "UK regulatory return with prudent valuation section",
            "frequency": "quarterly",
            "regulator": "PRA",
        },
        {
            "id": "fry14q",
            "name": "FR Y-14Q",
            "description": "US Federal Reserve quarterly trading risk return",
            "frequency": "quarterly",
            "regulator": "Federal Reserve",
        },
    ]


@router.post("/reports/{report_id}/generate")
async def generate_report(
    report_id: str,
    reporting_date: Optional[str] = Query(None),
) -> dict[str, Any]:
    """Generate a report by type.

    Routes to the appropriate report generation endpoint.
    """
    endpoint_map = {
        "pillar3": "/reports/pillar3",
        "ifrs13": "/reports/ifrs13",
        "pra110": "/reports/pra110",
        "fry14q": "/reports/fry14q",
    }

    if report_id not in endpoint_map:
        raise HTTPException(status_code=404, detail=f"Unknown report type: {report_id}")

    params = {}
    if reporting_date:
        params["reporting_date"] = reporting_date

    try:
        return await agent6_post(endpoint_map[report_id], json=params if params else None)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate {report_id} report: {exc}")


# ── Pillar 3 (Basel III) ────────────────────────────────────────


@router.post("/reports/pillar3")
async def generate_pillar3(
    reporting_date: str = Query(..., description="Reporting date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Generate Pillar 3 regulatory report.

    Proxies to Agent 6 POST /reports/pillar3.
    """
    try:
        return await agent6_post("/reports/pillar3", json={"reporting_date": reporting_date})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate Pillar 3: {exc}")


@router.post("/reports/pillar3/{report_id}/approve")
async def approve_pillar3(
    report_id: int,
    approved_by: str = Query(...),
) -> dict[str, Any]:
    """Approve a Pillar 3 report.

    Proxies to Agent 6 POST /reports/pillar3/{report_id}/approve.
    """
    try:
        return await agent6_post(
            f"/reports/pillar3/{report_id}/approve",
            json={"approved_by": approved_by},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to approve Pillar 3: {exc}")


@router.post("/reports/pillar3/{report_id}/submit")
async def submit_pillar3(
    report_id: int,
    regulator: str = Query(default="ECB"),
) -> dict[str, Any]:
    """Submit Pillar 3 report to regulator.

    Proxies to Agent 6 POST /reports/pillar3/{report_id}/submit.
    """
    try:
        return await agent6_post(
            f"/reports/pillar3/{report_id}/submit",
            json={"regulator": regulator},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to submit Pillar 3: {exc}")


# ── IFRS 13 ─────────────────────────────────────────────────────


@router.post("/reports/ifrs13")
async def generate_ifrs13(
    reporting_date: str = Query(..., description="Reporting date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Generate IFRS 13 fair value hierarchy report.

    Proxies to Agent 6 POST /reports/ifrs13.
    """
    try:
        return await agent6_post("/reports/ifrs13", json={"reporting_date": reporting_date})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate IFRS 13: {exc}")


# ── PRA110 (UK) ─────────────────────────────────────────────────


@router.post("/reports/pra110")
async def generate_pra110(
    reporting_date: str = Query(..., description="Reporting date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Generate PRA110 regulatory return.

    Proxies to Agent 6 POST /reports/pra110.
    """
    try:
        return await agent6_post("/reports/pra110", json={"reporting_date": reporting_date})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate PRA110: {exc}")


@router.post("/reports/pra110/{report_id}/submit")
async def submit_pra110(report_id: int) -> dict[str, Any]:
    """Submit PRA110 report to regulator.

    Proxies to Agent 6 POST /reports/pra110/{report_id}/submit.
    """
    try:
        return await agent6_post(f"/reports/pra110/{report_id}/submit")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to submit PRA110: {exc}")


@router.get("/reports/pra110/{report_id}/xml")
async def download_pra110_xml(report_id: int):
    """Download PRA110 as XML file.

    Proxies to Agent 6 GET /reports/pra110/{report_id}/xml.
    """
    client = await get_client()
    url = f"{settings.agent6_url}/reports/pra110/{report_id}/xml"

    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return StreamingResponse(
            iter([resp.content]),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename=pra110_{report_id}.xml"},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to download PRA110 XML: {exc}")


# ── FR Y-14Q (US Fed) ───────────────────────────────────────────


@router.post("/reports/fry14q")
async def generate_fry14q(
    reporting_date: str = Query(..., description="Reporting date (YYYY-MM-DD)"),
) -> dict[str, Any]:
    """Generate FR Y-14Q quarterly return.

    Proxies to Agent 6 POST /reports/fry14q.
    """
    try:
        return await agent6_post("/reports/fry14q", json={"reporting_date": reporting_date})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate FR Y-14Q: {exc}")


@router.post("/reports/fry14q/{report_id}/submit")
async def submit_fry14q(report_id: int) -> dict[str, Any]:
    """Submit FR Y-14Q report to Federal Reserve.

    Proxies to Agent 6 POST /reports/fry14q/{report_id}/submit.
    """
    try:
        return await agent6_post(f"/reports/fry14q/{report_id}/submit")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to submit FR Y-14Q: {exc}")


@router.get("/reports/fry14q/{report_id}/csv")
async def download_fry14q_csv(report_id: int):
    """Download FR Y-14Q as CSV file.

    Proxies to Agent 6 GET /reports/fry14q/{report_id}/csv.
    """
    client = await get_client()
    url = f"{settings.agent6_url}/reports/fry14q/{report_id}/csv"

    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return StreamingResponse(
            iter([resp.content]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=fry14q_{report_id}.csv"},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to download FR Y-14Q CSV: {exc}")


# ═══════════════════════════════════════════════════════════════
# AUDIT TRAIL
# ═══════════════════════════════════════════════════════════════


@router.get("/audit/trail")
async def get_audit_trail(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    event_type: Optional[str] = None,
    user: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query audit events with filters.

    Proxies to Agent 6 GET /audit/trail.
    """
    params = {
        "start_date": start_date,
        "end_date": end_date,
        "limit": limit,
        "offset": offset,
    }
    if event_type:
        params["event_type"] = event_type
    if user:
        params["user"] = user

    try:
        return await agent6_get("/audit/trail", params=params)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch audit trail: {exc}")


@router.get("/audit/trail/{event_id}")
async def get_audit_event(event_id: str) -> dict[str, Any]:
    """Get single audit event by ID.

    Proxies to Agent 6 GET /audit/trail/{event_id}.
    """
    try:
        return await agent6_get(f"/audit/trail/{event_id}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch audit event: {exc}")


@router.get("/audit/report")
async def get_audit_report(
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict[str, Any]:
    """Generate audit report for period.

    Proxies to Agent 6 GET /audit/report.
    """
    try:
        return await agent6_get("/audit/report", params={"start_date": start_date, "end_date": end_date})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to generate audit report: {exc}")


@router.get("/audit/report/excel")
async def download_audit_excel(
    start_date: str = Query(...),
    end_date: str = Query(...),
):
    """Download audit report as Excel file.

    Proxies to Agent 6 GET /audit/report/excel.
    """
    client = await get_client()
    url = f"{settings.agent6_url}/audit/report/excel"
    params = {"start_date": start_date, "end_date": end_date}

    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return StreamingResponse(
            iter([resp.content]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=audit_report_{start_date}_{end_date}.xlsx"},
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to download audit Excel: {exc}")


@router.get("/audit/statistics")
async def get_audit_statistics(
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict[str, Any]:
    """Get audit event statistics.

    Proxies to Agent 6 GET /audit/statistics.
    """
    try:
        return await agent6_get("/audit/statistics", params={"start_date": start_date, "end_date": end_date})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch audit statistics: {exc}")


# ═══════════════════════════════════════════════════════════════
# DATA EXPORT
# ═══════════════════════════════════════════════════════════════


@router.post("/export/{export_type}")
async def export_data(
    export_type: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Export data to various formats.

    Supports: positions, exceptions, reserves, comparisons.
    """
    # For now, return a placeholder indicating the export would be generated
    # In production, this would trigger an async export job
    return {
        "status": "queued",
        "export_type": export_type,
        "params": params or {},
        "download_url": f"/api/export/{export_type}/download",
        "message": "Export job queued. Download will be available shortly.",
    }

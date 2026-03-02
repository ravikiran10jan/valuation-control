"""API endpoints for the Validation Agent.

Provides endpoints to trigger validation of each category individually
or all at once, retrieve the latest report, and list identified gaps.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    GapsResponse,
    ValidationRequest,
    ValidationResponse,
)
from app.services.validation_runner import ValidationRunner, get_latest_report

router = APIRouter(prefix="/validate", tags=["validation"])


# ── Helpers ──────────────────────────────────────────────────────────

def _build_response(report, elapsed: float) -> ValidationResponse:
    """Wrap a ValidationReport into a ValidationResponse."""
    return ValidationResponse(
        success=report.total_errors == 0,
        report=report,
        execution_time_seconds=round(elapsed, 3),
    )


# ── POST endpoints (run validations) ────────────────────────────────

@router.post("/all", response_model=ValidationResponse)
async def validate_all(request: ValidationRequest | None = None) -> ValidationResponse:
    """Run ALL validation checks across all categories.

    Validates positions, tolerances, reserves (FVA, AVA, Model Reserve,
    Day 1 PnL), pricing, capital adequacy, and FV hierarchy against the
    Excel model expected values.
    """
    runner = ValidationRunner()
    start = time.monotonic()

    categories = request.categories if request else None
    report = await runner.run_all(categories=categories)

    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


@router.post("/positions", response_model=ValidationResponse)
async def validate_positions() -> ValidationResponse:
    """Validate position data against Excel expected values."""
    runner = ValidationRunner()
    start = time.monotonic()
    report = await runner.run_positions()
    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


@router.post("/tolerances", response_model=ValidationResponse)
async def validate_tolerances() -> ValidationResponse:
    """Validate tolerance thresholds and RAG status classification."""
    runner = ValidationRunner()
    start = time.monotonic()
    report = await runner.run_tolerances()
    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


@router.post("/reserves", response_model=ValidationResponse)
async def validate_reserves() -> ValidationResponse:
    """Validate FVA, AVA, Model Reserve, and Day 1 PnL calculations."""
    runner = ValidationRunner()
    start = time.monotonic()
    report = await runner.run_reserves()
    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


@router.post("/pricing", response_model=ValidationResponse)
async def validate_pricing() -> ValidationResponse:
    """Validate barrier pricing methods and survival probabilities."""
    runner = ValidationRunner()
    start = time.monotonic()
    report = await runner.run_pricing()
    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


@router.post("/capital", response_model=ValidationResponse)
async def validate_capital() -> ValidationResponse:
    """Validate capital adequacy calculations (CET1, RWA, ratios)."""
    runner = ValidationRunner()
    start = time.monotonic()
    report = await runner.run_capital()
    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


@router.post("/hierarchy", response_model=ValidationResponse)
async def validate_hierarchy() -> ValidationResponse:
    """Validate FV hierarchy classification and book value totals."""
    runner = ValidationRunner()
    start = time.monotonic()
    report = await runner.run_hierarchy()
    elapsed = time.monotonic() - start
    return _build_response(report, elapsed)


# ── GET endpoints (retrieve results) ────────────────────────────────

@router.get("/report", response_model=ValidationResponse)
async def get_validation_report() -> ValidationResponse:
    """Get the latest validation report.

    Run ``POST /validate/all`` first to generate a report.
    """
    report = get_latest_report()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No validation report available. Run POST /validate/all first.",
        )
    return ValidationResponse(
        success=report.total_errors == 0,
        report=report,
        execution_time_seconds=0.0,
    )


@router.get("/gaps", response_model=GapsResponse)
async def get_validation_gaps() -> GapsResponse:
    """Get all identified gaps from the latest validation run.

    Run ``POST /validate/all`` first to generate a report.
    """
    report = get_latest_report()
    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No validation report available. Run POST /validate/all first.",
        )
    return GapsResponse(
        total_gaps=len(report.gaps),
        high_severity=sum(1 for g in report.gaps if g.severity == "HIGH"),
        medium_severity=sum(1 for g in report.gaps if g.severity == "MEDIUM"),
        low_severity=sum(1 for g in report.gaps if g.severity == "LOW"),
        gaps=report.gaps,
    )


@router.get("/health")
async def validation_health() -> dict:
    """Health check with validation status summary."""
    report = get_latest_report()
    return {
        "status": "healthy",
        "has_report": report is not None,
        "last_score_pct": report.overall_score_pct if report else None,
        "last_report_id": report.report_id if report else None,
        "last_timestamp": report.timestamp.isoformat() if report else None,
    }

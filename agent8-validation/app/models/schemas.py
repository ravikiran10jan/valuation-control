"""Pydantic models for validation results and reporting."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Check result statuses ───────────────────────────────────────────
class CheckStatus(str, Enum):
    """Outcome of a single validation check."""

    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"
    ERROR = "ERROR"


class ValidationCategory(str, Enum):
    """Categories of validation."""

    POSITIONS = "POSITIONS"
    TOLERANCES = "TOLERANCES"
    FVA = "FVA"
    AVA = "AVA"
    MODEL_RESERVE = "MODEL_RESERVE"
    DAY1_PNL = "DAY1_PNL"
    PRICING = "PRICING"
    CAPITAL = "CAPITAL"
    FV_HIERARCHY = "FV_HIERARCHY"
    SUMMARY = "SUMMARY"


# ── Individual check result ─────────────────────────────────────────
class ValidationCheck(BaseModel):
    """Result of a single validation check."""

    check_id: str = Field(description="Unique identifier for the check")
    category: ValidationCategory
    description: str = Field(description="Human-readable description of what is being checked")
    status: CheckStatus
    expected_value: Any = Field(default=None, description="Expected value from the Excel model")
    actual_value: Any = Field(default=None, description="Actual value from the agent")
    difference: Optional[float] = Field(
        default=None, description="Numeric difference (actual - expected)"
    )
    tolerance: Optional[float] = Field(
        default=None, description="Tolerance threshold applied"
    )
    message: str = Field(default="", description="Detail message explaining the result")
    position_id: Optional[str] = Field(
        default=None, description="Position ID if check is position-specific"
    )


# ── Category summary ────────────────────────────────────────────────
class CategorySummary(BaseModel):
    """Aggregated result for a validation category."""

    category: ValidationCategory
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warned: int = 0
    skipped: int = 0
    errors: int = 0
    accuracy_pct: float = Field(
        default=0.0,
        description="Percentage of checks that passed (excluding skipped)",
    )
    checks: list[ValidationCheck] = []

    def compute_accuracy(self) -> None:
        """Recalculate accuracy from individual check counts."""
        evaluable = self.total_checks - self.skipped
        if evaluable > 0:
            self.accuracy_pct = round((self.passed / evaluable) * 100, 2)
        else:
            self.accuracy_pct = 100.0


# ── Gap / discrepancy ───────────────────────────────────────────────
class ValidationGap(BaseModel):
    """A specific discrepancy identified during validation."""

    gap_id: str
    category: ValidationCategory
    severity: str = Field(description="HIGH / MEDIUM / LOW")
    position_id: Optional[str] = None
    field_name: str
    expected_value: Any
    actual_value: Any
    difference: Optional[float] = None
    recommendation: str = ""


# ── Full validation report ──────────────────────────────────────────
class ValidationReport(BaseModel):
    """Comprehensive validation report across all categories."""

    report_id: str
    timestamp: datetime
    overall_score_pct: float = Field(
        description="Percentage of all evaluable checks that passed"
    )
    total_checks: int = 0
    total_passed: int = 0
    total_failed: int = 0
    total_warned: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    categories: list[CategorySummary] = []
    gaps: list[ValidationGap] = []
    recommendations: list[str] = []
    agents_reachable: dict[str, bool] = Field(
        default_factory=dict,
        description="Health check results for each upstream agent",
    )


# ── Request / response wrappers ─────────────────────────────────────
class ValidationRequest(BaseModel):
    """Optional parameters for a validation run."""

    categories: Optional[list[ValidationCategory]] = Field(
        default=None,
        description="Specific categories to validate; None means all",
    )
    tolerance_override_pct: Optional[float] = Field(
        default=None,
        description="Override default numeric tolerance for this run",
    )
    include_skipped: bool = Field(
        default=False,
        description="Include skipped checks in the report",
    )


class ValidationResponse(BaseModel):
    """Top-level response wrapping the validation report."""

    success: bool
    report: ValidationReport
    execution_time_seconds: float


class GapsResponse(BaseModel):
    """Response containing all identified gaps."""

    total_gaps: int
    high_severity: int
    medium_severity: int
    low_severity: int
    gaps: list[ValidationGap]

"""Pydantic schemas for regulatory reporting API request/response validation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from enum import Enum

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────
class FairValueLevel(str, Enum):
    LEVEL_1 = "Level 1"
    LEVEL_2 = "Level 2"
    LEVEL_3 = "Level 3"


class AuditEventType(str, Enum):
    VALUATION_RUN = "VALUATION_RUN"
    MARK_ADJUSTMENT = "MARK_ADJUSTMENT"
    EXCEPTION_CREATED = "EXCEPTION_CREATED"
    EXCEPTION_RESOLVED = "EXCEPTION_RESOLVED"
    REPORT_GENERATED = "REPORT_GENERATED"
    REPORT_SUBMITTED = "REPORT_SUBMITTED"
    AVA_CALCULATED = "AVA_CALCULATED"
    LEVEL_TRANSFER = "LEVEL_TRANSFER"


class ReportStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    REJECTED = "REJECTED"


class ReportType(str, Enum):
    PILLAR3 = "PILLAR3"
    IFRS13 = "IFRS13"
    PRA110 = "PRA110"
    FRY14Q = "FRY14Q"
    ECB = "ECB"


# ── AVA breakdown schemas ─────────────────────────────────────────
class AVABreakdown(BaseModel):
    market_price_uncertainty: Decimal = Field(default=Decimal("0"), alias="mpu")
    close_out_costs: Decimal = Field(default=Decimal("0"), alias="close_out")
    model_risk: Decimal = Field(default=Decimal("0"))
    unearned_credit_spreads: Decimal = Field(default=Decimal("0"), alias="credit_spreads")
    investment_funding: Decimal = Field(default=Decimal("0"), alias="funding")
    concentrated_positions: Decimal = Field(default=Decimal("0"), alias="concentration")
    future_admin_costs: Decimal = Field(default=Decimal("0"), alias="admin")

    @property
    def total(self) -> Decimal:
        return (
            self.market_price_uncertainty
            + self.close_out_costs
            + self.model_risk
            + self.unearned_credit_spreads
            + self.investment_funding
            + self.concentrated_positions
            + self.future_admin_costs
        )


# ── Pillar 3 schemas ──────────────────────────────────────────────
class Pillar3Table32(BaseModel):
    """Pillar 3 Table 3.2: Prudent Valuation Adjustments."""
    total_ava: str
    breakdown: dict[str, Decimal]
    as_pct_of_cet1: str


class Pillar3ReportRequest(BaseModel):
    reporting_date: date


class Pillar3ReportOut(BaseModel):
    report_id: int
    reporting_date: date
    status: ReportStatus
    tables: dict[str, Pillar3Table32]
    generated_at: datetime
    submitted_at: Optional[datetime] = None
    submitted_to: Optional[str] = None


# ── IFRS 13 schemas ───────────────────────────────────────────────
class FairValueLevelSummary(BaseModel):
    level: FairValueLevel
    count: int
    total_fair_value: Decimal
    percentage_of_total: Decimal


class Level3Movement(BaseModel):
    opening_balance: Decimal
    purchases: Decimal
    issuances: Decimal = Decimal("0")
    transfers_in: Decimal
    transfers_out: Decimal
    settlements: Decimal
    pnl: Decimal
    oci: Decimal = Decimal("0")
    closing_balance: Decimal
    check_passed: bool


class ValuationTechnique(BaseModel):
    product_type: str
    technique: str
    inputs: list[str]
    observable_inputs: bool


class IFRS13ReportRequest(BaseModel):
    reporting_date: date


class IFRS13ReportOut(BaseModel):
    report_id: int
    reporting_date: date
    status: ReportStatus
    fair_value_hierarchy: list[FairValueLevelSummary]
    level3_reconciliation: Level3Movement
    valuation_techniques: list[ValuationTechnique]
    generated_at: datetime


# ── PRA110 schemas ────────────────────────────────────────────────
class PRA110SectionD(BaseModel):
    """PRA110 Section D: Prudent Valuation Adjustments."""
    d010_mpu: Decimal
    d020_close_out: Decimal
    d030_model_risk: Decimal
    d040_credit_spreads: Decimal
    d050_funding: Decimal
    d060_concentration: Decimal
    d070_admin: Decimal
    d080_total_ava: Decimal


class PRA110ReportRequest(BaseModel):
    reporting_date: date


class PRA110ReportOut(BaseModel):
    report_id: int
    reporting_date: date
    firm_reference: str
    status: ReportStatus
    section_d: PRA110SectionD
    xml_content: Optional[str] = None
    generated_at: datetime
    submitted_at: Optional[datetime] = None


# ── FR Y-14Q schemas ──────────────────────────────────────────────
class VaRMetrics(BaseModel):
    var_1day_99: Decimal
    var_10day_99: Decimal
    stressed_var: Optional[Decimal] = None


class FRY14QScheduleH1(BaseModel):
    """FR Y-14Q Schedule H.1: Trading Risk."""
    fair_value_hierarchy: list[FairValueLevelSummary]
    prudent_valuation: AVABreakdown
    var_metrics: VaRMetrics


class FRY14QReportRequest(BaseModel):
    reporting_date: date


class FRY14QReportOut(BaseModel):
    report_id: int
    reporting_date: date
    firm_reference: str
    status: ReportStatus
    schedule_h1: FRY14QScheduleH1
    csv_content: Optional[str] = None
    generated_at: datetime
    submitted_at: Optional[datetime] = None


# ── Audit trail schemas ───────────────────────────────────────────
class AuditEventCreate(BaseModel):
    event_type: AuditEventType
    user: str
    details: dict
    ip_address: Optional[str] = None


class AuditEventOut(BaseModel):
    event_id: str
    event_type: AuditEventType
    user: str
    timestamp: datetime
    details: dict
    ip_address: Optional[str] = None

    model_config = {"from_attributes": True}


class AuditTrailQuery(BaseModel):
    start_date: date
    end_date: date
    event_type: Optional[AuditEventType] = None
    user: Optional[str] = None
    limit: int = Field(default=1000, le=10000)
    offset: int = 0


class AuditReportOut(BaseModel):
    period_start: date
    period_end: date
    total_events: int
    events_by_type: dict[str, int]
    users: list[str]
    events: list[AuditEventOut]


# ── Report generation schemas ─────────────────────────────────────
class ReportGenerationStatus(BaseModel):
    report_id: int
    report_type: ReportType
    status: ReportStatus
    message: str
    generated_at: Optional[datetime] = None


class ReportSubmissionRequest(BaseModel):
    report_id: int
    report_type: ReportType
    regulator: str  # ECB, PRA, FED


class ReportSubmissionResponse(BaseModel):
    report_id: int
    submitted_at: datetime
    regulator: str
    confirmation_id: Optional[str] = None
    status: str


# ── Regulatory report storage schemas ─────────────────────────────
class RegulatoryReportCreate(BaseModel):
    report_type: ReportType
    reporting_date: date
    firm_reference: str
    content: dict
    file_format: Optional[str] = None  # PDF, XML, CSV


class RegulatoryReportOut(BaseModel):
    report_id: int
    report_type: ReportType
    reporting_date: date
    firm_reference: str
    status: ReportStatus
    content: dict
    file_format: Optional[str] = None
    generated_at: datetime
    approved_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    submitted_at: Optional[datetime] = None
    submission_ref: Optional[str] = None

    model_config = {"from_attributes": True}


# ── CET1 capital schemas ──────────────────────────────────────────
class CET1CapitalOut(BaseModel):
    reporting_date: date
    cet1_capital: Decimal
    total_ava: Decimal
    ava_as_pct_of_cet1: Decimal

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
    CAPITAL_ADEQUACY_CALCULATED = "CAPITAL_ADEQUACY_CALCULATED"


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
    CAPITAL_ADEQUACY = "CAPITAL_ADEQUACY"


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


# ── Capital Adequacy schemas ─────────────────────────────────────
class CET1CapitalComponents(BaseModel):
    """CET1 capital calculation components from Excel Capital_Adequacy sheet."""
    shareholders_equity: Decimal = Field(description="Total shareholders equity")
    retained_earnings: Decimal = Field(description="Retained earnings")
    aoci: Decimal = Field(description="Accumulated Other Comprehensive Income")
    goodwill_intangibles: Decimal = Field(description="Goodwill and intangible assets (deducted)")
    deferred_tax_assets: Decimal = Field(description="Deferred tax assets (deducted)")
    ava_deduction: Decimal = Field(description="AVA deduction from Level 3 positions")
    other_regulatory_deductions: Decimal = Field(description="Other regulatory deductions")
    total_cet1: Decimal = Field(description="Total CET1 capital after deductions")


class CreditRiskRWA(BaseModel):
    """Credit risk RWA breakdown."""
    corporate_exposure: Decimal = Field(description="Corporate exposure amount")
    corporate_weight: Decimal = Field(default=Decimal("1.00"), description="Corporate risk weight (100%)")
    corporate_rwa: Decimal = Field(description="Corporate RWA")
    bank_exposure: Decimal = Field(description="Bank exposure amount")
    bank_weight: Decimal = Field(default=Decimal("0.50"), description="Bank risk weight (50%)")
    bank_rwa: Decimal = Field(description="Bank RWA")
    retail_exposure: Decimal = Field(description="Retail exposure amount")
    retail_weight: Decimal = Field(default=Decimal("0.75"), description="Retail risk weight (75%)")
    retail_rwa: Decimal = Field(description="Retail RWA")
    total_credit_rwa: Decimal = Field(description="Total credit risk RWA")


class MarketRiskRWA(BaseModel):
    """Market risk RWA breakdown."""
    fx_exposure: Decimal = Field(description="FX exposure amount")
    fx_weight: Decimal = Field(default=Decimal("0.08"), description="FX risk weight (8%)")
    fx_rwa: Decimal = Field(description="FX RWA")
    ir_exposure: Decimal = Field(description="Interest rate exposure amount")
    ir_weight: Decimal = Field(default=Decimal("0.06"), description="IR risk weight (6%)")
    ir_rwa: Decimal = Field(description="Interest rate RWA")
    equity_exposure: Decimal = Field(description="Equity exposure amount")
    equity_weight: Decimal = Field(default=Decimal("0.25"), description="Equity risk weight (25%)")
    equity_rwa: Decimal = Field(description="Equity RWA")
    total_market_rwa: Decimal = Field(description="Total market risk RWA")


class OperationalRiskRWA(BaseModel):
    """Operational risk RWA calculation."""
    gross_income: Decimal = Field(description="Gross income for BIA calculation")
    bia_factor: Decimal = Field(default=Decimal("0.15"), description="Basic Indicator Approach factor (15%)")
    total_operational_rwa: Decimal = Field(description="Total operational risk RWA")


class RWAComponents(BaseModel):
    """Total RWA breakdown across risk categories."""
    credit_risk: CreditRiskRWA
    market_risk: MarketRiskRWA
    operational_risk: OperationalRiskRWA
    total_rwa: Decimal = Field(description="Total risk-weighted assets")


class CapitalRatios(BaseModel):
    """Capital adequacy ratios and regulatory minimums."""
    cet1_ratio: Decimal = Field(description="CET1 ratio = CET1 / Total RWA")
    cet1_minimum: Decimal = Field(default=Decimal("0.045"), description="Minimum CET1 ratio (4.5%)")
    cet1_with_ccb: Decimal = Field(default=Decimal("0.070"), description="CET1 with Capital Conservation Buffer (7.0%)")
    cet1_with_ccyb: Decimal = Field(default=Decimal("0.075"), description="CET1 with Countercyclical Buffer (7.5%)")
    leverage_ratio: Optional[Decimal] = Field(default=None, description="Leverage ratio = CET1 / Total Exposure")
    leverage_minimum: Decimal = Field(default=Decimal("0.03"), description="Minimum leverage ratio (3.0%)")
    cet1_surplus: Decimal = Field(description="CET1 surplus above minimum requirement")
    cet1_surplus_with_buffers: Decimal = Field(description="CET1 surplus above minimum + all buffers")
    passes_minimum: bool = Field(description="Whether CET1 ratio meets minimum requirement")
    passes_with_ccb: bool = Field(description="Whether CET1 ratio meets minimum + CCB")
    passes_with_ccyb: bool = Field(description="Whether CET1 ratio meets minimum + CCB + CCyB")


class CapitalAdequacyRequest(BaseModel):
    """Request to generate a capital adequacy report."""
    reporting_date: date

    # CET1 components
    shareholders_equity: Decimal = Field(default=Decimal("50000000"))
    retained_earnings: Decimal = Field(default=Decimal("25000000"))
    aoci: Decimal = Field(default=Decimal("2000000"))
    goodwill_intangibles: Decimal = Field(default=Decimal("5000000"))
    deferred_tax_assets: Decimal = Field(default=Decimal("1000000"))
    ava_deduction: Optional[Decimal] = None  # If None, fetched from AVA calculations
    other_regulatory_deductions: Decimal = Field(default=Decimal("500000"))

    # Credit Risk Exposures
    corporate_exposure: Decimal = Field(default=Decimal("150000000"))
    bank_exposure: Decimal = Field(default=Decimal("75000000"))
    retail_exposure: Decimal = Field(default=Decimal("50000000"))

    # Market Risk Exposures
    fx_exposure: Decimal = Field(default=Decimal("485750000"))
    ir_exposure: Decimal = Field(default=Decimal("25000000"))
    equity_exposure: Decimal = Field(default=Decimal("10000000"))

    # Operational Risk
    gross_income: Decimal = Field(default=Decimal("200000000"))

    # Leverage
    total_exposure: Optional[Decimal] = None  # For leverage ratio calculation


class CapitalAdequacyResult(BaseModel):
    """Full capital adequacy report matching Excel Capital_Adequacy sheet."""
    report_id: Optional[int] = None
    reporting_date: date
    status: ReportStatus = ReportStatus.DRAFT

    # Components
    cet1_components: CET1CapitalComponents
    rwa_components: RWAComponents
    capital_ratios: CapitalRatios

    # Summary
    total_cet1: Decimal
    total_rwa: Decimal
    cet1_ratio_pct: Decimal = Field(description="CET1 ratio as percentage (e.g. 23.7)")

    generated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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

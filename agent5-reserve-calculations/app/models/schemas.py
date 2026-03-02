"""Pydantic schemas for reserve calculation API request/response validation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Shared position input ────────────────────────────────────────
class PositionInput(BaseModel):
    """Minimal position data consumed by reserve calculators."""

    position_id: int
    trade_id: str
    product_type: Optional[str] = None
    asset_class: Optional[str] = None
    notional: Optional[Decimal] = None
    currency: Optional[str] = None
    trade_date: Optional[date] = None
    maturity_date: Optional[date] = None
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None
    classification: str = "Level2"  # Level1, Level2, Level3
    position_direction: str = "LONG"  # LONG, SHORT
    transaction_price: Optional[Decimal] = None


# ── Dealer quotes ────────────────────────────────────────────────
class DealerQuoteInput(BaseModel):
    """Individual dealer quote for MPU calculation."""
    dealer_name: str
    value: Decimal
    quote_date: Optional[date] = None


# ── Model comparison ─────────────────────────────────────────────
class ModelComparisonEntry(BaseModel):
    """Result from a single pricing model for model risk assessment."""
    model: str
    value: float


class ModelComparisonInput(BaseModel):
    """Extended model comparison input with metadata for detailed model risk AVA."""
    model_name: str
    fair_value: Decimal
    model_type: Optional[str] = None  # e.g. "Black-Scholes", "Local Vol", "Heston", "Monte Carlo"
    confidence_level: Optional[Decimal] = None
    parameter_sensitivity: Optional[Decimal] = None  # sensitivity measure for parameter approach


# ── FVA ──────────────────────────────────────────────────────────
class FVAResult(BaseModel):
    position_id: int
    fva_amount: Decimal
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None
    rationale: str
    calculation_date: date


class FVAAmortizationEntry(BaseModel):
    """Single period in FVA amortization schedule."""
    period_number: int
    period_date: date
    opening_balance: Decimal
    monthly_release: Decimal
    closing_balance: Decimal


class FVAWithAmortization(FVAResult):
    """FVA result with full amortization schedule (premium-based FVA)."""
    premium_paid: Optional[Decimal] = None
    fair_value_at_inception: Optional[Decimal] = None
    total_fva: Optional[Decimal] = None
    months_to_maturity: Optional[int] = None
    monthly_release: Optional[Decimal] = None
    amortization_schedule: list[FVAAmortizationEntry] = []


class FVAAggregateResult(BaseModel):
    total_fva: Decimal
    position_count: int
    asset_class: Optional[str] = None
    details: list[FVAResult]


# ── AVA ──────────────────────────────────────────────────────────
class AVAComponents(BaseModel):
    mpu: Decimal = Field(description="Market Price Uncertainty")
    close_out: Decimal = Field(description="Close-Out Costs")
    model_risk: Decimal = Field(description="Model Risk")
    credit_spreads: Decimal = Field(description="Unearned Credit Spreads")
    funding: Decimal = Field(description="Investment & Funding Costs")
    concentration: Decimal = Field(description="Concentrated Positions")
    admin: Decimal = Field(description="Future Administrative Costs")


# ── Detailed AVA sub-calculation breakdowns ──────────────────────
class MPUSubCalculation(BaseModel):
    """Detailed breakdown of Market Price Uncertainty AVA."""
    dealer_quotes: list[DealerQuoteInput] = []
    quote_high: Optional[Decimal] = None
    quote_low: Optional[Decimal] = None
    spread: Optional[Decimal] = None
    mpu_base: Optional[Decimal] = None
    level_classification: str = "Level2"
    illiquidity_multiplier: Decimal = Decimal("1.0")
    mpu_adjusted: Decimal = Decimal("0")
    method_used: str = "dealer_quotes"  # dealer_quotes, fallback_pct


class CloseOutSubCalculation(BaseModel):
    """Detailed breakdown of Close-Out Costs AVA."""
    mpu_ava: Decimal = Decimal("0")
    close_out_pct: Decimal = Decimal("0.50")
    close_out_amount: Decimal = Decimal("0")
    validation_fv: Optional[Decimal] = None
    validation_pct: Optional[Decimal] = None
    validation_amount: Optional[Decimal] = None


class ModelRiskSubCalculation(BaseModel):
    """Detailed breakdown of Model Risk AVA."""
    model_comparisons: list[ModelComparisonInput] = []
    model_high: Optional[Decimal] = None
    model_low: Optional[Decimal] = None
    model_range: Optional[Decimal] = None
    method1_range_half: Optional[Decimal] = None
    method2_industry_pct: Optional[Decimal] = None
    method2_industry_ava: Optional[Decimal] = None
    method3_param_sensitivity: Optional[Decimal] = None
    method3_param_multiplier: Decimal = Decimal("2.5")
    method3_param_ava: Optional[Decimal] = None
    selected_method: str = "conservative_max"
    model_risk_ava: Decimal = Decimal("0")


class CreditSpreadsSubCalculation(BaseModel):
    """Detailed breakdown of Unearned Credit Spreads AVA."""
    applicable: bool = False
    asset_class: Optional[str] = None
    credit_spread_ava: Decimal = Decimal("0")
    reason: str = "Not applicable for this product type"


class FundingSubCalculation(BaseModel):
    """Detailed breakdown of Investment & Funding Costs AVA."""
    applicable: bool = False
    position_direction: str = "LONG"
    fair_value: Optional[Decimal] = None
    funding_spread_bps: Optional[Decimal] = None
    time_to_maturity_years: Optional[Decimal] = None
    funding_ava: Decimal = Decimal("0")
    reason: str = ""


class ConcentrationSubCalculation(BaseModel):
    """Detailed breakdown of Concentrated Positions AVA."""
    flagged: bool = False
    position_pct_of_book: Optional[Decimal] = None
    threshold_pct: Decimal = Decimal("0.05")
    concentration_ava: Decimal = Decimal("0")
    reason: str = ""


class AdminSubCalculation(BaseModel):
    """Detailed breakdown of Future Administrative Costs AVA."""
    fair_value: Optional[Decimal] = None
    admin_rate_bps: Decimal = Decimal("10")
    time_to_maturity_years: Optional[Decimal] = None
    base_admin_ava: Optional[Decimal] = None
    level_classification: str = "Level2"
    level3_multiplier: Decimal = Decimal("1.58")
    admin_ava: Decimal = Decimal("0")


class DetailedAVAResult(BaseModel):
    """Comprehensive AVA result with full sub-calculation breakdowns for all 7 categories."""
    position_id: int
    total_ava: Decimal
    components: AVAComponents
    calculation_date: date

    # Detailed sub-calculations
    mpu_detail: MPUSubCalculation
    close_out_detail: CloseOutSubCalculation
    model_risk_detail: ModelRiskSubCalculation
    credit_spreads_detail: CreditSpreadsSubCalculation
    funding_detail: FundingSubCalculation
    concentration_detail: ConcentrationSubCalculation
    admin_detail: AdminSubCalculation

    # Level multiplier reference
    level_multipliers: dict[str, Decimal] = {
        "Level1": Decimal("1.0"),
        "Level2": Decimal("1.5"),
        "Level3": Decimal("2.83"),
    }

    # CET1 deduction indicator
    cet1_deduction: Decimal = Decimal("0")

    model_config = {"from_attributes": True}


class AVAResult(BaseModel):
    position_id: int
    total_ava: Decimal
    components: AVAComponents
    calculation_date: date

    model_config = {"from_attributes": True}


class AVAAggregateResult(BaseModel):
    total_ava: Decimal
    position_count: int
    category_totals: AVAComponents
    details: list[AVAResult]


# ── Model Reserve ────────────────────────────────────────────────
class ModelReserveResult(BaseModel):
    position_id: int
    model_reserve: Decimal
    model_range: Decimal
    model_comparison: list[ModelComparisonEntry]
    calculation_date: date


# ── Day 1 P&L ────────────────────────────────────────────────────
class Day1PnLResult(BaseModel):
    position_id: int
    transaction_price: Decimal
    fair_value: Decimal
    day1_pnl: Decimal
    recognition_status: str  # RECOGNIZED, DEFERRED
    recognized_amount: Decimal
    deferred_amount: Decimal
    trade_date: Optional[date] = None

    model_config = {"from_attributes": True}


class AmortizationEntry(BaseModel):
    period_date: date
    amortization_amount: Decimal
    cumulative_recognized: Decimal
    remaining_deferred: Decimal


class Day1PnLWithSchedule(Day1PnLResult):
    amortization_schedule: list[AmortizationEntry] = []


# ── Red Flag Detection ───────────────────────────────────────────
class RedFlagSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SEVERE = "SEVERE"


class RedFlag(BaseModel):
    """Individual red flag detection result."""
    flag_id: str
    flag_name: str
    severity: RedFlagSeverity
    description: str
    triggered: bool
    details: Optional[dict] = None
    threshold: Optional[str] = None
    actual_value: Optional[str] = None


class RedFlagReport(BaseModel):
    """Complete red flag analysis for a Day 1 P&L position."""
    position_id: int
    trade_id: str
    total_flags_triggered: int
    max_severity: Optional[RedFlagSeverity] = None
    flags: list[RedFlag]
    assessment_date: date
    requires_escalation: bool = False
    escalation_reason: Optional[str] = None


class Day1PnLWithRedFlags(Day1PnLWithSchedule):
    """Day 1 P&L result with red flag analysis."""
    red_flag_report: Optional[RedFlagReport] = None


# ── Reserve summary ──────────────────────────────────────────────
class ReserveOut(BaseModel):
    reserve_id: int
    position_id: int
    reserve_type: str
    amount: Decimal
    calculation_date: date
    rationale: Optional[str] = None
    components: Optional[dict] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReserveSummary(BaseModel):
    total_fva: Decimal
    total_ava: Decimal
    total_model_reserve: Decimal
    total_day1_deferred: Decimal
    grand_total: Decimal
    position_count: int
    calculation_date: date


# ── Batch request ────────────────────────────────────────────────
class BatchReserveRequest(BaseModel):
    position_ids: Optional[list[int]] = None
    asset_class: Optional[str] = None


# ── Composite per-position result ────────────────────────────────
class PositionReserveRequest(BaseModel):
    position: PositionInput
    dealer_quotes: Optional[list[DealerQuoteInput]] = None
    model_results: Optional[list[ModelComparisonEntry]] = None
    model_comparisons: Optional[list[ModelComparisonInput]] = None
    total_book_value: Optional[Decimal] = None


class PositionReserveResult(BaseModel):
    position_id: int
    fva: FVAResult
    ava: AVAResult
    model_reserve: Optional[ModelReserveResult] = None
    day1_pnl: Day1PnLWithSchedule
    total_reserve: Decimal
    calculation_date: date


class FVAByAssetClass(BaseModel):
    asset_class: str
    total_fva: Decimal
    position_count: int

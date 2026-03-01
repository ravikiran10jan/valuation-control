"""Pydantic schemas for reserve calculation API request/response validation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
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


# ── FVA ──────────────────────────────────────────────────────────
class FVAResult(BaseModel):
    position_id: int
    fva_amount: Decimal
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None
    rationale: str
    calculation_date: date


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
class ModelComparisonEntry(BaseModel):
    model: str
    value: float


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


class DealerQuoteInput(BaseModel):
    dealer_name: str
    value: Decimal
    quote_date: Optional[date] = None


# ── Composite per-position result ────────────────────────────────
class PositionReserveRequest(BaseModel):
    position: PositionInput
    dealer_quotes: Optional[list[DealerQuoteInput]] = None
    model_results: Optional[list[ModelComparisonEntry]] = None
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

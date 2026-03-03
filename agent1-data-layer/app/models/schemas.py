"""Pydantic schemas for API request/response validation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── Position schemas ──────────────────────────────────────────────
class PositionBase(BaseModel):
    trade_id: str = Field(..., max_length=50)
    product_type: Optional[str] = None
    asset_class: Optional[str] = None
    currency_pair: Optional[str] = None
    notional: Optional[Decimal] = None
    notional_usd: Optional[Decimal] = None
    currency: Optional[str] = Field(None, max_length=3)
    trade_date: Optional[date] = None
    maturity_date: Optional[date] = None
    settlement_date: Optional[date] = None
    counterparty: Optional[str] = None
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None
    book_value_usd: Optional[Decimal] = None
    valuation_date: Optional[date] = None
    fair_value_level: Optional[str] = None
    pricing_source: Optional[str] = None
    fva_usd: Optional[Decimal] = None


class PositionCreate(PositionBase):
    pass


class PositionUpdate(BaseModel):
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None
    book_value_usd: Optional[Decimal] = None
    exception_status: Optional[str] = None
    valuation_date: Optional[date] = None
    fva_usd: Optional[Decimal] = None


class PositionOut(PositionBase):
    position_id: int
    difference: Optional[Decimal] = None
    difference_pct: Optional[Decimal] = None
    exception_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── FX Barrier detail schemas ────────────────────────────────────
class FXBarrierDetailCreate(BaseModel):
    currency_pair: Optional[str] = None
    spot_ref: Optional[Decimal] = None
    lower_barrier: Optional[Decimal] = None
    upper_barrier: Optional[Decimal] = None
    barrier_type: Optional[str] = None
    volatility: Optional[Decimal] = None
    time_to_expiry: Optional[Decimal] = None
    domestic_rate: Optional[Decimal] = None
    foreign_rate: Optional[Decimal] = None
    survival_probability: Optional[Decimal] = None
    premium_market: Optional[Decimal] = None
    premium_model: Optional[Decimal] = None


class FXBarrierDetailOut(FXBarrierDetailCreate):
    position_id: int

    model_config = {"from_attributes": True}


# ── Rates swap detail schemas ────────────────────────────────────
class RatesSwapDetailCreate(BaseModel):
    fixed_rate: Optional[Decimal] = None
    float_index: Optional[str] = None
    pay_frequency: Optional[str] = None
    receive_frequency: Optional[str] = None
    day_count_convention: Optional[str] = None
    discount_curve: Optional[str] = None


class RatesSwapDetailOut(RatesSwapDetailCreate):
    position_id: int

    model_config = {"from_attributes": True}


# ── Commodity detail schemas ───────────────────────────────────────
class CommodityDetailCreate(BaseModel):
    commodity: Optional[str] = None
    contract_unit: Optional[str] = None
    fixed_price: Optional[Decimal] = None
    float_index: Optional[str] = None
    settlement_type: Optional[str] = None
    delivery_point: Optional[str] = None


class CommodityDetailOut(CommodityDetailCreate):
    position_id: int

    model_config = {"from_attributes": True}


# ── Structured product detail schemas ──────────────────────────────
class StructuredProductDetailCreate(BaseModel):
    tranche: Optional[str] = None
    attachment_pct: Optional[Decimal] = None
    detachment_pct: Optional[Decimal] = None
    pool_size: Optional[int] = None
    wac: Optional[Decimal] = None
    wam: Optional[Decimal] = None
    credit_rating: Optional[str] = None
    collateral_type: Optional[str] = None


class StructuredProductDetailOut(StructuredProductDetailCreate):
    position_id: int

    model_config = {"from_attributes": True}


# ── Bond detail schemas ────────────────────────────────────────────
class BondDetailCreate(BaseModel):
    issuer: Optional[str] = None
    coupon_rate: Optional[Decimal] = None
    coupon_frequency: Optional[str] = None
    credit_rating: Optional[str] = None
    yield_to_maturity: Optional[Decimal] = None
    duration: Optional[Decimal] = None
    convexity: Optional[Decimal] = None
    contract_size: Optional[Decimal] = None
    futures_ticker: Optional[str] = None


class BondDetailOut(BondDetailCreate):
    position_id: int

    model_config = {"from_attributes": True}


# ── Market data snapshot schemas ─────────────────────────────────
class MarketDataSnapshotCreate(BaseModel):
    valuation_date: date
    data_source: str
    field_name: str
    field_value: Decimal


class MarketDataSnapshotOut(MarketDataSnapshotCreate):
    snapshot_id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── Dealer quote schemas ─────────────────────────────────────────
class DealerQuoteCreate(BaseModel):
    position_id: int
    dealer_name: str
    quote_value: Decimal
    quote_date: date
    quote_type: Optional[str] = None


class DealerQuoteOut(DealerQuoteCreate):
    quote_id: int

    model_config = {"from_attributes": True}


# ── Market data query helpers ────────────────────────────────────
class SpotRateOut(BaseModel):
    currency_pair: str
    value: Decimal
    source: str
    timestamp: datetime


class VolSurfacePointOut(BaseModel):
    delta: str
    volatility: Decimal


class VolSurfaceOut(BaseModel):
    currency_pair: str
    tenor: str
    points: list[VolSurfacePointOut]
    source: str
    timestamp: datetime


# ── Data quality schemas ─────────────────────────────────────────
class DataQualityMetric(BaseModel):
    metric: str
    value: float
    status: str  # OK, WARNING, CRITICAL
    detail: Optional[str] = None


class DataQualitySummary(BaseModel):
    valuation_date: date
    freshness_pct: float
    validation_failures: int
    cross_validation_alerts: int
    data_gaps: int
    metrics: list[DataQualityMetric]


# ── Exception schemas ────────────────────────────────────────────
class ExceptionBase(BaseModel):
    position_id: int
    difference: Decimal
    difference_pct: Decimal
    severity: str = Field(..., pattern="^(AMBER|RED)$")


class ExceptionCreate(ExceptionBase):
    assigned_to: Optional[str] = None


class ExceptionUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(OPEN|INVESTIGATING|RESOLVED|ESCALATED)$")
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None


class ExceptionOut(ExceptionBase):
    exception_id: int
    status: str
    created_date: date
    assigned_to: Optional[str] = None
    days_open: int
    escalation_level: int
    resolution_notes: Optional[str] = None
    resolved_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExceptionSummary(BaseModel):
    total_exceptions: int
    red_count: int
    amber_count: int
    avg_days_to_resolve: float


# ── Exception comment schemas ────────────────────────────────────
class ExceptionCommentCreate(BaseModel):
    user_name: str
    comment_text: str
    attachments: Optional[dict] = None  # {files: ['file1.xlsx', 'file2.pdf']}


class ExceptionCommentOut(ExceptionCommentCreate):
    comment_id: int
    exception_id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── Valuation comparison schemas ─────────────────────────────────
class ValuationComparisonCreate(BaseModel):
    position_id: int
    desk_mark: Decimal
    vc_fair_value: Decimal
    comparison_date: date


class ValuationComparisonOut(BaseModel):
    comparison_id: int
    position_id: int
    desk_mark: Decimal
    vc_fair_value: Decimal
    difference: Decimal
    difference_pct: Decimal
    status: str
    comparison_date: date
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Resolution schemas ───────────────────────────────────────────
class ResolutionData(BaseModel):
    resolution_notes: str
    resolved_by: str


# ── Committee agenda schemas ─────────────────────────────────────
class CommitteeAgendaItemOut(BaseModel):
    agenda_id: int
    exception_id: int
    position_id: int
    difference: Decimal
    status: str
    meeting_date: date
    resolution: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Exception detail with position info ──────────────────────────
class ExceptionDetailOut(ExceptionOut):
    position: Optional[PositionOut] = None
    comments: list[ExceptionCommentOut] = []

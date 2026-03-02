"""Pydantic schemas for IPV Orchestrator API request/response validation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enumerations ─────────────────────────────────────────────────
class RAGStatus(str, Enum):
    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class FairValueLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class IPVStepName(str, Enum):
    GATHER_MARKET_DATA = "GATHER_MARKET_DATA"
    RUN_VALUATION_MODEL = "RUN_VALUATION_MODEL"
    COMPARE_DESK_VS_VC = "COMPARE_DESK_VS_VC"
    FLAG_EXCEPTIONS = "FLAG_EXCEPTIONS"
    INVESTIGATE_DISPUTE = "INVESTIGATE_DISPUTE"
    ESCALATE_TO_COMMITTEE = "ESCALATE_TO_COMMITTEE"
    RESOLVE_AND_ADJUST = "RESOLVE_AND_ADJUST"
    REPORT = "REPORT"


class IPVRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ProductCategory(str, Enum):
    G10_SPOT = "G10_SPOT"
    EM_SPOT = "EM_SPOT"
    FX_FORWARD = "FX_FORWARD"
    FX_OPTION = "FX_OPTION"


# ── Position schemas ─────────────────────────────────────────────
class PositionInput(BaseModel):
    """Position data as input to the IPV pipeline."""
    position_id: str
    currency_pair: str
    product_type: str
    notional: Decimal
    desk_mark: Decimal
    fair_value_level: FairValueLevel = FairValueLevel.L1
    trade_date: Optional[date] = None
    maturity_date: Optional[date] = None
    counterparty: Optional[str] = None
    desk: Optional[str] = None
    # Barrier-specific fields
    lower_barrier: Optional[Decimal] = None
    upper_barrier: Optional[Decimal] = None
    barrier_type: Optional[str] = None
    volatility: Optional[Decimal] = None
    time_to_expiry: Optional[Decimal] = None
    domestic_rate: Optional[Decimal] = None
    foreign_rate: Optional[Decimal] = None


class PositionResult(BaseModel):
    """Result of IPV processing for a single position."""
    position_id: str
    currency_pair: str
    product_type: str
    notional: Decimal
    desk_mark: Decimal
    ipv_price: Decimal
    difference: Decimal
    difference_pct: Decimal
    rag_status: RAGStatus
    fair_value_level: FairValueLevel
    product_category: ProductCategory
    threshold_green: Decimal
    threshold_amber: Decimal
    breach_amount_usd: Optional[Decimal] = None
    exception_raised: bool = False
    dispute_id: Optional[int] = None
    escalated: bool = False
    reserve_amount: Optional[Decimal] = None
    notes: Optional[str] = None


# ── Market data schemas ──────────────────────────────────────────
class MarketDataSnapshot(BaseModel):
    """Market data gathered for a position."""
    position_id: str
    currency_pair: str
    spot_rate: Optional[Decimal] = None
    forward_points: Optional[Decimal] = None
    forward_rate: Optional[Decimal] = None
    vol_surface: Optional[dict[str, Any]] = None
    yield_curve_dom: Optional[dict[str, Any]] = None
    yield_curve_for: Optional[dict[str, Any]] = None
    data_source: str = "agent1"
    timestamp: Optional[datetime] = None
    quality_score: Optional[float] = None


# ── Valuation result schemas ────────────────────────────────────
class ValuationResult(BaseModel):
    """Result from running the pricing model."""
    position_id: str
    ipv_price: Decimal
    pricing_method: str = "mid_market"
    model_name: Optional[str] = None
    greeks: Optional[dict[str, float]] = None
    confidence: Optional[float] = None
    pricing_source: str = "agent2"


# ── Comparison schemas ───────────────────────────────────────────
class ComparisonResult(BaseModel):
    """Result of comparing desk mark vs VC fair value."""
    position_id: str
    desk_mark: Decimal
    ipv_price: Decimal
    difference: Decimal
    difference_pct: Decimal
    product_category: ProductCategory
    rag_status: RAGStatus
    threshold_green: Decimal
    threshold_amber: Decimal
    breach: bool


# ── Exception schemas ────────────────────────────────────────────
class ExceptionRecord(BaseModel):
    """An exception flagged during IPV processing."""
    position_id: str
    severity: RAGStatus
    difference: Decimal
    difference_pct: Decimal
    breach_amount_usd: Optional[Decimal] = None
    product_category: ProductCategory
    fair_value_level: FairValueLevel
    auto_action: str  # "NONE", "DISPUTE", "ESCALATE"


# ── Escalation schemas ──────────────────────────────────────────
class EscalationRecord(BaseModel):
    """Record of dispute or escalation action taken."""
    position_id: str
    action: str  # "DISPUTE_CREATED", "ESCALATED_TO_COMMITTEE", "NO_ACTION"
    dispute_id: Optional[int] = None
    committee_agenda_id: Optional[int] = None
    reason: str
    target: Optional[str] = None  # "DESK", "MANAGER", "COMMITTEE"


# ── Resolution schemas ──────────────────────────────────────────
class ResolutionRecord(BaseModel):
    """Record of adjustment or resolution for a position."""
    position_id: str
    action: str  # "RESERVE_CREATED", "ADJUSTMENT_POSTED", "NO_ACTION"
    reserve_type: Optional[str] = None
    reserve_amount: Optional[Decimal] = None
    adjustment_amount: Optional[Decimal] = None
    notes: str


# ── Report trigger schemas ──────────────────────────────────────
class ReportTriggerResult(BaseModel):
    """Result of triggering regulatory report generation."""
    report_type: str
    report_id: Optional[int] = None
    status: str  # "GENERATED", "FAILED", "SKIPPED"
    details: Optional[dict[str, Any]] = None


# ── Step result schemas ──────────────────────────────────────────
class StepResult(BaseModel):
    """Result of a single IPV pipeline step."""
    step_number: int
    step_name: IPVStepName
    status: StepStatus
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    positions_processed: int = 0
    errors: list[str] = Field(default_factory=list)
    data: Optional[dict[str, Any]] = None


# ── IPV Run schemas ──────────────────────────────────────────────
class IPVRunRequest(BaseModel):
    """Request to start an IPV run."""
    valuation_date: date = Field(default_factory=date.today)
    position_ids: Optional[list[str]] = None  # None = all positions
    run_type: str = "FULL"  # FULL, INCREMENTAL, RERUN
    triggered_by: str = "system"
    skip_steps: list[IPVStepName] = Field(default_factory=list)


class IPVRunSummary(BaseModel):
    """Summary of an IPV run matching the Excel Summary_Dashboard."""
    run_id: str
    valuation_date: date
    run_type: str
    status: IPVRunStatus
    triggered_by: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Position counts
    total_positions: int = 0
    green_count: int = 0
    amber_count: int = 0
    red_count: int = 0

    # Level breakdown
    l1_count: int = 0
    l2_count: int = 0
    l3_count: int = 0

    # Exception summary
    exceptions_raised: int = 0
    disputes_created: int = 0
    escalations_triggered: int = 0

    # Financial impact
    total_breach_amount_usd: Decimal = Decimal("0")
    total_reserves_usd: Decimal = Decimal("0")

    # Step progress
    steps_completed: int = 0
    steps_total: int = 8
    current_step: Optional[IPVStepName] = None

    # Detailed results
    steps: list[StepResult] = Field(default_factory=list)
    position_results: list[PositionResult] = Field(default_factory=list)

    # Reports generated
    reports_generated: list[ReportTriggerResult] = Field(default_factory=list)


class IPVRunListItem(BaseModel):
    """Summary item for listing IPV runs."""
    run_id: str
    valuation_date: date
    run_type: str
    status: IPVRunStatus
    triggered_by: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_positions: int = 0
    green_count: int = 0
    amber_count: int = 0
    red_count: int = 0
    exceptions_raised: int = 0


# ── WebSocket progress schemas ──────────────────────────────────
class ProgressUpdate(BaseModel):
    """Real-time progress update sent via WebSocket."""
    run_id: str
    event_type: str  # "STEP_STARTED", "STEP_COMPLETED", "STEP_FAILED", "POSITION_PROCESSED", "RUN_COMPLETED"
    step_number: Optional[int] = None
    step_name: Optional[IPVStepName] = None
    step_status: Optional[StepStatus] = None
    position_id: Optional[str] = None
    rag_status: Optional[RAGStatus] = None
    message: str
    progress_pct: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Optional[dict[str, Any]] = None

"""SQLAlchemy ORM models for IPV Orchestrator persistence."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class IPVRun(Base):
    """A single IPV cycle execution."""

    __tablename__ = "ipv_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    run_type: Mapped[str] = mapped_column(String(20), nullable=False)  # FULL, INCREMENTAL, RERUN
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING, RUNNING, COMPLETED, FAILED, PARTIAL
    triggered_by: Mapped[str] = mapped_column(String(50), default="system")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)

    # Aggregate counts
    total_positions: Mapped[int] = mapped_column(Integer, default=0)
    green_count: Mapped[int] = mapped_column(Integer, default=0)
    amber_count: Mapped[int] = mapped_column(Integer, default=0)
    red_count: Mapped[int] = mapped_column(Integer, default=0)
    l1_count: Mapped[int] = mapped_column(Integer, default=0)
    l2_count: Mapped[int] = mapped_column(Integer, default=0)
    l3_count: Mapped[int] = mapped_column(Integer, default=0)
    exceptions_raised: Mapped[int] = mapped_column(Integer, default=0)
    disputes_created: Mapped[int] = mapped_column(Integer, default=0)
    escalations_triggered: Mapped[int] = mapped_column(Integer, default=0)
    total_breach_amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    total_reserves_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    # Configuration snapshot
    config_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    step_results: Mapped[List[IPVStepResult]] = relationship(
        back_populates="ipv_run", cascade="all, delete-orphan",
        order_by="IPVStepResult.step_number",
    )
    position_results: Mapped[List[IPVPositionResult]] = relationship(
        back_populates="ipv_run", cascade="all, delete-orphan",
    )
    audit_entries: Mapped[List[IPVAuditEntry]] = relationship(
        back_populates="ipv_run", cascade="all, delete-orphan",
    )


class IPVStepResult(Base):
    """Result of a single step in the IPV pipeline."""

    __tablename__ = "ipv_step_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("ipv_runs.run_id"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="PENDING"
    )  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)
    positions_processed: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[Optional[dict]] = mapped_column(JSONB)  # list of error strings as JSON
    data: Mapped[Optional[dict]] = mapped_column(JSONB)  # step-specific output data

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ipv_run: Mapped[IPVRun] = relationship(back_populates="step_results")


class IPVPositionResult(Base):
    """Per-position result within an IPV run."""

    __tablename__ = "ipv_position_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("ipv_runs.run_id"), nullable=False, index=True
    )
    position_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    currency_pair: Mapped[str] = mapped_column(String(10), nullable=False)
    product_type: Mapped[str] = mapped_column(String(50), nullable=False)
    product_category: Mapped[str] = mapped_column(String(20), nullable=False)
    notional: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    desk_mark: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    ipv_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    difference_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    rag_status: Mapped[str] = mapped_column(String(10), nullable=False)  # GREEN, AMBER, RED
    fair_value_level: Mapped[str] = mapped_column(String(5), nullable=False)  # L1, L2, L3
    threshold_green: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    threshold_amber: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    breach_amount_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    exception_raised: Mapped[bool] = mapped_column(default=False)
    dispute_id: Mapped[Optional[int]] = mapped_column(Integer)
    escalated: Mapped[bool] = mapped_column(default=False)
    reserve_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Market data snapshot
    market_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    # Pricing details
    pricing_details: Mapped[Optional[dict]] = mapped_column(JSONB)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ipv_run: Mapped[IPVRun] = relationship(back_populates="position_results")


class IPVAuditEntry(Base):
    """Audit trail entry for an IPV run action."""

    __tablename__ = "ipv_audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("ipv_runs.run_id"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    step_name: Mapped[Optional[str]] = mapped_column(String(50))
    position_id: Mapped[Optional[str]] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(50), default="system")
    details: Mapped[Optional[dict]] = mapped_column(JSONB)

    ipv_run: Mapped[IPVRun] = relationship(back_populates="audit_entries")

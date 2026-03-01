"""SQLAlchemy models for regulatory reporting and audit trail."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from app.core.database import Base


class AuditEvent(Base):
    """Immutable audit trail for SOX compliance.
    
    Stores all valuation-related events for regulatory audit.
    """
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_timestamp", "timestamp"),
        Index("ix_audit_events_event_type", "event_type"),
        Index("ix_audit_events_user", "user"),
        {"schema": "regulatory"},
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Event type: VALUATION_RUN, MARK_ADJUSTMENT, EXCEPTION_CREATED, etc.",
    )
    user: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)


class RegulatoryReport(Base):
    """Stores generated regulatory reports."""
    __tablename__ = "regulatory_reports"
    __table_args__ = (
        Index("ix_regulatory_reports_type_date", "report_type", "reporting_date"),
        Index("ix_regulatory_reports_status", "status"),
        {"schema": "regulatory"},
    )

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Report type: PILLAR3, IFRS13, PRA110, FRY14Q, ECB",
    )
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False)
    firm_reference: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        comment="Status: DRAFT, PENDING_REVIEW, APPROVED, SUBMITTED, REJECTED",
    )
    content: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    file_format: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    file_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    submission_ref: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)


class FairValueHierarchy(Base):
    """Tracks fair value level classifications for IFRS 13 reporting."""
    __tablename__ = "fair_value_hierarchy"
    __table_args__ = (
        Index("ix_fv_hierarchy_position_date", "position_id", "classification_date"),
        {"schema": "regulatory"},
    )

    hierarchy_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False)
    classification_date: Mapped[date] = mapped_column(Date, nullable=False)
    fair_value_level: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Fair value level: Level 1, Level 2, Level 3",
    )
    fair_value: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    classification_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class LevelTransfer(Base):
    """Records transfers between fair value levels for IFRS 13."""
    __tablename__ = "level_transfers"
    __table_args__ = (
        Index("ix_level_transfers_date", "transfer_date"),
        {"schema": "regulatory"},
    )

    transfer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)
    from_level: Mapped[str] = mapped_column(String(10), nullable=False)
    to_level: Mapped[str] = mapped_column(String(10), nullable=False)
    fair_value: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AVASnapshot(Base):
    """Stores AVA calculations for regulatory reporting."""
    __tablename__ = "ava_snapshots"
    __table_args__ = (
        Index("ix_ava_snapshots_date", "valuation_date"),
        {"schema": "regulatory"},
    )

    snapshot_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    position_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ava_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="AVA type: MPU, CLOSE_OUT, MODEL_RISK, CREDIT_SPREADS, FUNDING, CONCENTRATION, ADMIN",
    )
    ava_amount: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    calculation_details: Mapped[dict] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class CET1Capital(Base):
    """Stores CET1 capital figures for AVA % calculation."""
    __tablename__ = "cet1_capital"
    __table_args__ = {"schema": "regulatory"}

    capital_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    cet1_capital: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
    at1_capital: Mapped[Optional[float]] = mapped_column(Numeric(20, 2), nullable=True)
    tier2_capital: Mapped[Optional[float]] = mapped_column(Numeric(20, 2), nullable=True)
    total_capital: Mapped[Optional[float]] = mapped_column(Numeric(20, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

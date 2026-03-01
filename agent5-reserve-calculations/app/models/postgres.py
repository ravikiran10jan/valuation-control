"""SQLAlchemy ORM models for reserve calculations."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Reserve(Base):
    """Unified reserve table for FVA, AVA, Model Reserve, and Day 1 P&L."""

    __tablename__ = "reserves"

    reserve_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reserve_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # FVA, AVA, Model_Reserve, Day1_PnL
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    calculation_date: Mapped[date] = mapped_column(Date, nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    components: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AVADetail(Base):
    """Breakdown of AVA by the 7 Basel III Article 105 categories."""

    __tablename__ = "ava_detail"

    ava_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_ava: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    mpu: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    close_out: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    model_risk: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    credit_spreads: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    funding: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    concentration: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    admin: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    calculation_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Day1PnL(Base):
    """Day 1 P&L recognition per IFRS 13 / ASC 820."""

    __tablename__ = "day1_pnl"

    pnl_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    transaction_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fair_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    day1_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    recognition_status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # RECOGNIZED, DEFERRED
    recognized_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    deferred_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    trade_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AmortizationSchedule(Base):
    """Amortization schedule for deferred Day 1 P&L (Level 3 positions)."""

    __tablename__ = "amortization_schedule"

    schedule_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period_date: Mapped[date] = mapped_column(Date, nullable=False)
    amortization_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cumulative_recognized: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    remaining_deferred: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

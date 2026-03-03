"""SQLAlchemy ORM models for the Valuation Control data layer."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Date,
    DateTime,
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


# ── Positions ─────────────────────────────────────────────────────
class Position(Base):
    __tablename__ = "positions"

    position_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_type: Mapped[Optional[str]] = mapped_column(String(50))
    asset_class: Mapped[Optional[str]] = mapped_column(String(20))
    currency_pair: Mapped[Optional[str]] = mapped_column(String(10))
    notional: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    notional_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    currency: Mapped[Optional[str]] = mapped_column(String(3))
    trade_date: Mapped[Optional[date]] = mapped_column(Date)
    maturity_date: Mapped[Optional[date]] = mapped_column(Date)
    settlement_date: Mapped[Optional[date]] = mapped_column(Date)
    counterparty: Mapped[Optional[str]] = mapped_column(String(100))
    desk_mark: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    vc_fair_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    book_value_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6))
    difference_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    exception_status: Mapped[Optional[str]] = mapped_column(String(10))  # GREEN / AMBER / RED
    fair_value_level: Mapped[Optional[str]] = mapped_column(String(5))  # L1, L2, L3
    pricing_source: Mapped[Optional[str]] = mapped_column(String(50))
    fva_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    valuation_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    fx_barrier_detail: Mapped[Optional[FXBarrierDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    rates_swap_detail: Mapped[Optional[RatesSwapDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    credit_detail: Mapped[Optional[CreditDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    equity_detail: Mapped[Optional[EquityDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    commodity_detail: Mapped[Optional[CommodityDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    structured_product_detail: Mapped[Optional[StructuredProductDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    bond_detail: Mapped[Optional[BondDetail]] = relationship(
        back_populates="position", uselist=False, cascade="all, delete-orphan"
    )
    dealer_quotes: Mapped[List[DealerQuote]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )
    exceptions: Mapped[List[VCException]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )
    comparisons: Mapped[List[ValuationComparison]] = relationship(
        back_populates="position", cascade="all, delete-orphan"
    )


# ── Asset-class detail tables ────────────────────────────────────
class FXBarrierDetail(Base):
    __tablename__ = "fx_barrier_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    currency_pair: Mapped[Optional[str]] = mapped_column(String(10))
    spot_ref: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    lower_barrier: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    upper_barrier: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 5))
    barrier_type: Mapped[Optional[str]] = mapped_column(String(20))  # DNT, KI, KO
    volatility: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    time_to_expiry: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    domestic_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    foreign_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    survival_probability: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    premium_market: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    premium_model: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    position: Mapped[Position] = relationship(back_populates="fx_barrier_detail")


class RatesSwapDetail(Base):
    __tablename__ = "rates_swap_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    fixed_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 5))
    float_index: Mapped[Optional[str]] = mapped_column(String(20))  # SOFR, EURIBOR
    pay_frequency: Mapped[Optional[str]] = mapped_column(String(10))  # 3M, 6M, 1Y
    receive_frequency: Mapped[Optional[str]] = mapped_column(String(10))
    day_count_convention: Mapped[Optional[str]] = mapped_column(String(20))  # ACT/360
    discount_curve: Mapped[Optional[str]] = mapped_column(String(30))

    position: Mapped[Position] = relationship(back_populates="rates_swap_detail")


class CreditDetail(Base):
    __tablename__ = "credit_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    reference_entity: Mapped[Optional[str]] = mapped_column(String(100))
    seniority: Mapped[Optional[str]] = mapped_column(String(20))  # Senior, Sub
    cds_spread_bps: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    recovery_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    restructuring_type: Mapped[Optional[str]] = mapped_column(String(20))  # CR, MR, MM, XR

    position: Mapped[Position] = relationship(back_populates="credit_detail")


class EquityDetail(Base):
    __tablename__ = "equity_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    underlying_ticker: Mapped[Optional[str]] = mapped_column(String(20))
    spot_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    dividend_yield: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4))
    implied_vol: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    strike: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    option_type: Mapped[Optional[str]] = mapped_column(String(10))  # Call, Put

    position: Mapped[Position] = relationship(back_populates="equity_detail")


class CommodityDetail(Base):
    __tablename__ = "commodity_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    commodity: Mapped[Optional[str]] = mapped_column(String(30))  # WTI, Brent, Gold, NatGas
    contract_unit: Mapped[Optional[str]] = mapped_column(String(20))  # bbl, MMBtu, oz
    fixed_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    float_index: Mapped[Optional[str]] = mapped_column(String(30))  # ICE Brent, NYMEX WTI
    settlement_type: Mapped[Optional[str]] = mapped_column(String(10))  # Cash, Physical
    delivery_point: Mapped[Optional[str]] = mapped_column(String(50))

    position: Mapped[Position] = relationship(back_populates="commodity_detail")


class StructuredProductDetail(Base):
    __tablename__ = "structured_product_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    tranche: Mapped[Optional[str]] = mapped_column(String(20))  # Senior, Mezzanine, Equity
    attachment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    detachment_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    pool_size: Mapped[Optional[int]] = mapped_column(Integer)
    wac: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))  # Weighted avg coupon
    wam: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 2))  # Weighted avg maturity (years)
    credit_rating: Mapped[Optional[str]] = mapped_column(String(10))  # AAA, AA, BBB, etc.
    collateral_type: Mapped[Optional[str]] = mapped_column(String(50))

    position: Mapped[Position] = relationship(back_populates="structured_product_detail")


class BondDetail(Base):
    __tablename__ = "bond_details"

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), primary_key=True
    )
    issuer: Mapped[Optional[str]] = mapped_column(String(100))
    coupon_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    coupon_frequency: Mapped[Optional[str]] = mapped_column(String(10))  # Semi, Annual, Quarterly
    credit_rating: Mapped[Optional[str]] = mapped_column(String(10))
    yield_to_maturity: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 4))
    duration: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 3))  # Modified duration
    convexity: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    contract_size: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    futures_ticker: Mapped[Optional[str]] = mapped_column(String(20))

    position: Mapped[Position] = relationship(back_populates="bond_detail")


# ── Market data snapshot ──────────────────────────────────────────
class MarketDataSnapshot(Base):
    __tablename__ = "market_data_snapshots"

    snapshot_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_source: Mapped[str] = mapped_column(String(20), nullable=False)
    field_name: Mapped[str] = mapped_column(String(50), nullable=False)
    field_value: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ── Dealer quotes ─────────────────────────────────────────────────
class DealerQuote(Base):
    __tablename__ = "dealer_quotes"

    quote_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.position_id"), nullable=False)
    dealer_name: Mapped[str] = mapped_column(String(50), nullable=False)
    quote_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    quote_date: Mapped[date] = mapped_column(Date, nullable=False)
    quote_type: Mapped[Optional[str]] = mapped_column(String(20))  # Bid, Offer, Mid

    position: Mapped[Position] = relationship(back_populates="dealer_quotes")


# ── Exceptions ────────────────────────────────────────────────────
class VCException(Base):
    """Exception records for VC vs Desk mark discrepancies."""

    __tablename__ = "exceptions"

    exception_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), nullable=False
    )
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    difference_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="OPEN"
    )  # OPEN, INVESTIGATING, RESOLVED, ESCALATED
    severity: Mapped[str] = mapped_column(String(10), nullable=False)  # AMBER, RED
    created_date: Mapped[date] = mapped_column(Date, nullable=False)
    assigned_to: Mapped[Optional[str]] = mapped_column(String(50))
    days_open: Mapped[int] = mapped_column(Integer, default=0)
    escalation_level: Mapped[int] = mapped_column(
        Integer, default=1
    )  # 1=Analyst, 2=Manager, 3=Committee
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)
    resolved_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    position: Mapped[Position] = relationship(back_populates="exceptions")
    comments: Mapped[List[ExceptionComment]] = relationship(
        back_populates="exception", cascade="all, delete-orphan"
    )


class ExceptionComment(Base):
    """Comments and dispute tracking for exceptions."""

    __tablename__ = "exception_comments"

    comment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(
        ForeignKey("exceptions.exception_id"), nullable=False
    )
    user_name: Mapped[str] = mapped_column(String(50), nullable=False)
    comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[Optional[dict]] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exception: Mapped[VCException] = relationship(back_populates="comments")


# ── Valuation Comparisons (historical tracking) ───────────────────
class ValuationComparison(Base):
    """Historical record of VC vs Desk comparisons."""

    __tablename__ = "valuation_comparisons"

    comparison_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), nullable=False
    )
    desk_mark: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    vc_fair_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    difference_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # GREEN, AMBER, RED
    comparison_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    position: Mapped[Position] = relationship(back_populates="comparisons")


# ── Committee Agenda Items ────────────────────────────────────────
class CommitteeAgendaItem(Base):
    """Valuation Committee meeting agenda items."""

    __tablename__ = "committee_agenda_items"

    agenda_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(
        ForeignKey("exceptions.exception_id"), nullable=False
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"), nullable=False
    )
    difference: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default="PENDING_COMMITTEE"
    )  # PENDING_COMMITTEE, DISCUSSED, RESOLVED
    meeting_date: Mapped[date] = mapped_column(Date, nullable=False)
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    exception: Mapped[VCException] = relationship()
    position: Mapped[Position] = relationship()

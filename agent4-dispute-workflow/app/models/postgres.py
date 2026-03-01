"""SQLAlchemy ORM models for the Dispute Workflow & Collaboration system."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── Disputes ──────────────────────────────────────────────────────
class Dispute(Base):
    """Main dispute record linking an exception to a structured workflow."""

    __tablename__ = "disputes"

    dispute_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exception_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    position_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    state: Mapped[str] = mapped_column(
        String(30), nullable=False, default="INITIATED"
    )
    # Valid states: INITIATED, DESK_REVIEWING, DESK_RESPONDED,
    # VC_REVIEWING, NEGOTIATING, ESCALATED,
    # RESOLVED_VC_WIN, RESOLVED_DESK_WIN, RESOLVED_COMPROMISE

    vc_position: Mapped[Optional[str]] = mapped_column(Text)
    desk_position: Mapped[Optional[str]] = mapped_column(Text)

    vc_analyst: Mapped[str] = mapped_column(String(100), nullable=False)
    desk_trader: Mapped[Optional[str]] = mapped_column(String(100))

    desk_mark: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    vc_fair_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    difference_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    resolution_type: Mapped[Optional[str]] = mapped_column(String(30))
    final_mark: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    audit_trail: Mapped[Optional[Dict]] = mapped_column(JSON, default=list)

    created_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    resolved_date: Mapped[Optional[datetime]] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # relationships
    messages: Mapped[List[DisputeMessage]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan",
        order_by="DisputeMessage.timestamp",
    )
    approvals: Mapped[List[DisputeApproval]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan",
    )
    attachments: Mapped[List[DisputeAttachment]] = relationship(
        back_populates="dispute", cascade="all, delete-orphan",
    )


# ── Dispute Messages (chat / email thread) ────────────────────────
class DisputeMessage(Base):
    """Individual messages within a dispute conversation thread."""

    __tablename__ = "dispute_messages"

    message_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(
        ForeignKey("disputes.dispute_id"), nullable=False, index=True
    )
    sender: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_role: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # VC, DESK, MANAGER
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    attachments: Mapped[Optional[Dict]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="platform"
    )  # platform, email
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    dispute: Mapped[Dispute] = relationship(back_populates="messages")


# ── Dispute Approvals (mark adjustment requests) ──────────────────
class DisputeApproval(Base):
    """Approval records for mark adjustment requests."""

    __tablename__ = "dispute_approvals"

    approval_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(
        ForeignKey("disputes.dispute_id"), nullable=False, index=True
    )
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    old_mark: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    new_mark: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING, APPROVED, REJECTED
    requested_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    approved_date: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # relationships
    dispute: Mapped[Dispute] = relationship(back_populates="approvals")


# ── Dispute Attachments ───────────────────────────────────────────
class DisputeAttachment(Base):
    """Uploaded document metadata for dispute evidence."""

    __tablename__ = "dispute_attachments"

    attachment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dispute_id: Mapped[int] = mapped_column(
        ForeignKey("disputes.dispute_id"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(100))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer)
    document_type: Mapped[Optional[str]] = mapped_column(
        String(50)
    )  # model_output, term_sheet, email, other
    version: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # relationships
    dispute: Mapped[Dispute] = relationship(back_populates="attachments")

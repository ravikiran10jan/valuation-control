"""Pydantic schemas for Dispute Workflow API request/response validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── Dispute schemas ───────────────────────────────────────────────
VALID_STATES = {
    "INITIATED", "DESK_REVIEWING", "DESK_RESPONDED",
    "VC_REVIEWING", "NEGOTIATING", "ESCALATED",
    "RESOLVED_VC_WIN", "RESOLVED_DESK_WIN", "RESOLVED_COMPROMISE",
}

VALID_RESOLUTION_TYPES = {"VC_WIN", "DESK_WIN", "COMPROMISE"}
VALID_SENDER_ROLES = {"VC", "DESK", "MANAGER"}
VALID_APPROVAL_STATUSES = {"PENDING", "APPROVED", "REJECTED"}


class DisputeCreate(BaseModel):
    exception_id: int
    position_id: int
    vc_position: str = Field(..., min_length=1)
    vc_analyst: str = Field(..., max_length=100)
    desk_trader: Optional[str] = Field(None, max_length=100)
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None


class DisputeUpdate(BaseModel):
    desk_position: Optional[str] = None
    desk_trader: Optional[str] = Field(None, max_length=100)


class DisputeOut(BaseModel):
    dispute_id: int
    exception_id: int
    position_id: int
    state: str
    vc_position: Optional[str] = None
    desk_position: Optional[str] = None
    vc_analyst: str
    desk_trader: Optional[str] = None
    desk_mark: Optional[Decimal] = None
    vc_fair_value: Optional[Decimal] = None
    difference: Optional[Decimal] = None
    difference_pct: Optional[Decimal] = None
    resolution_type: Optional[str] = None
    final_mark: Optional[Decimal] = None
    audit_trail: Optional[list] = None
    created_date: datetime
    resolved_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DisputeDetailOut(DisputeOut):
    messages: list[DisputeMessageOut] = []
    approvals: list[DisputeApprovalOut] = []
    attachments: list[DisputeAttachmentOut] = []


class DisputeSummary(BaseModel):
    total_disputes: int
    initiated: int
    in_progress: int
    escalated: int
    resolved: int
    avg_days_to_resolve: float


# ── Dispute Message schemas ───────────────────────────────────────
class DisputeMessageCreate(BaseModel):
    sender: str = Field(..., max_length=100)
    sender_role: str = Field(..., pattern="^(VC|DESK|MANAGER)$")
    message_text: str = Field(..., min_length=1)
    attachments: Optional[dict] = None


class DisputeMessageOut(BaseModel):
    message_id: int
    dispute_id: int
    sender: str
    sender_role: str
    message_text: str
    attachments: Optional[dict] = None
    source: str
    timestamp: datetime

    model_config = {"from_attributes": True}


# ── Dispute Approval schemas ─────────────────────────────────────
class DisputeApprovalCreate(BaseModel):
    requested_by: str = Field(..., max_length=100)
    old_mark: Decimal
    new_mark: Decimal
    justification: str = Field(..., min_length=1)


class DisputeApprovalDecision(BaseModel):
    approver: str = Field(..., max_length=100)
    decision: str = Field(..., pattern="^(APPROVED|REJECTED)$")


class DisputeApprovalOut(BaseModel):
    approval_id: int
    dispute_id: int
    requested_by: str
    approved_by: Optional[str] = None
    old_mark: Decimal
    new_mark: Decimal
    justification: str
    status: str
    requested_date: datetime
    approved_date: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Dispute Attachment schemas ────────────────────────────────────
class DisputeAttachmentOut(BaseModel):
    attachment_id: int
    dispute_id: int
    filename: str
    content_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    document_type: Optional[str] = None
    version: int
    uploaded_by: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DisputeAttachmentUploadOut(DisputeAttachmentOut):
    presigned_url: str


# ── State transition request ──────────────────────────────────────
class DisputeStateTransition(BaseModel):
    new_state: str
    actor: str = Field(..., max_length=100)
    reason: Optional[str] = None


class DeskResponse(BaseModel):
    desk_position: str = Field(..., min_length=1)
    desk_trader: str = Field(..., max_length=100)
    proposed_mark: Optional[Decimal] = None


class DisputeResolve(BaseModel):
    resolution_type: str = Field(..., pattern="^(VC_WIN|DESK_WIN|COMPROMISE)$")
    final_mark: Decimal
    actor: str = Field(..., max_length=100)
    notes: Optional[str] = None


# Forward reference updates
DisputeDetailOut.model_rebuild()

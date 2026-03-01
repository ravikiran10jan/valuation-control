"""Dispute approval workflow API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    DisputeApprovalCreate,
    DisputeApprovalDecision,
    DisputeApprovalOut,
)
from app.services.approvals import ApprovalWorkflow

router = APIRouter(prefix="/disputes/{dispute_id}/approvals", tags=["Dispute Approvals"])
_workflow = ApprovalWorkflow()


@router.get("/", response_model=list[DisputeApprovalOut])
async def list_approvals(
    dispute_id: int,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List approval requests for a dispute."""
    return await _workflow.list_approvals(db, dispute_id=dispute_id, status=status)


@router.post("/", response_model=DisputeApprovalOut, status_code=201)
async def request_approval(
    dispute_id: int,
    data: DisputeApprovalCreate,
    db: AsyncSession = Depends(get_db),
):
    """Request a mark adjustment approval."""
    try:
        return await _workflow.request_mark_adjustment(db, dispute_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{approval_id}/decide", response_model=DisputeApprovalOut)
async def decide_approval(
    dispute_id: int,
    approval_id: int,
    data: DisputeApprovalDecision,
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject a mark adjustment request."""
    try:
        approval = await _workflow.decide_approval(db, approval_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if approval.dispute_id != dispute_id:
        raise HTTPException(status_code=404, detail="Approval not found for this dispute")
    return approval

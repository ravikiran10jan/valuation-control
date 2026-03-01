"""Dispute CRUD and workflow API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import (
    DeskResponse,
    DisputeCreate,
    DisputeDetailOut,
    DisputeOut,
    DisputeResolve,
    DisputeStateTransition,
    DisputeSummary,
    DisputeUpdate,
)
from app.services import disputes as dispute_svc
from app.services.email_integration import EmailIntegration

router = APIRouter(prefix="/disputes", tags=["Disputes"])
_email = EmailIntegration()


@router.get("/summary", response_model=DisputeSummary)
async def dispute_summary(db: AsyncSession = Depends(get_db)):
    """Get aggregate dispute statistics."""
    return await dispute_svc.get_dispute_summary(db)


@router.get("/", response_model=list[DisputeOut])
async def list_disputes(
    state: Optional[str] = None,
    exception_id: Optional[int] = None,
    vc_analyst: Optional[str] = None,
    desk_trader: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List disputes with optional filters."""
    return await dispute_svc.list_disputes(
        db, state, exception_id, vc_analyst, desk_trader, limit, offset
    )


@router.get("/{dispute_id}", response_model=DisputeDetailOut)
async def get_dispute(dispute_id: int, db: AsyncSession = Depends(get_db)):
    """Get full dispute detail including messages, approvals, attachments."""
    dispute = await dispute_svc.get_dispute_detail(db, dispute_id)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return dispute


@router.post("/", response_model=DisputeOut, status_code=201)
async def create_dispute(data: DisputeCreate, db: AsyncSession = Depends(get_db)):
    """VC analyst initiates a new dispute."""
    dispute = await dispute_svc.create_dispute(db, data)

    # Transition to DESK_REVIEWING and notify desk
    if data.desk_trader:
        dispute = await dispute_svc.transition_state(
            db, dispute.dispute_id, "DESK_REVIEWING", data.vc_analyst,
            "Auto-transition: desk trader assigned",
        )
        await _email.notify_dispute_initiated(
            {
                "dispute_id": dispute.dispute_id,
                "position_id": dispute.position_id,
                "vc_fair_value": str(dispute.vc_fair_value),
                "desk_mark": str(dispute.desk_mark),
                "difference": str(dispute.difference),
                "difference_pct": str(dispute.difference_pct),
                "vc_position": dispute.vc_position,
            },
            data.desk_trader,
        )

    return dispute


@router.patch("/{dispute_id}", response_model=DisputeOut)
async def update_dispute(
    dispute_id: int, data: DisputeUpdate, db: AsyncSession = Depends(get_db)
):
    dispute = await dispute_svc.update_dispute(db, dispute_id, data)
    if not dispute:
        raise HTTPException(status_code=404, detail="Dispute not found")
    return dispute


@router.post("/{dispute_id}/transition", response_model=DisputeOut)
async def transition_dispute(
    dispute_id: int,
    data: DisputeStateTransition,
    db: AsyncSession = Depends(get_db),
):
    """Manually transition a dispute to a new state."""
    try:
        dispute = await dispute_svc.transition_state(
            db, dispute_id, data.new_state, data.actor, data.reason or ""
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Send escalation email if escalated
    if data.new_state == "ESCALATED":
        await _email.notify_escalation({
            "dispute_id": dispute.dispute_id,
            "position_id": dispute.position_id,
            "vc_fair_value": str(dispute.vc_fair_value),
            "desk_mark": str(dispute.desk_mark),
            "difference": str(dispute.difference),
            "difference_pct": str(dispute.difference_pct),
        })

    return dispute


@router.post("/{dispute_id}/desk-respond", response_model=DisputeOut)
async def desk_respond(
    dispute_id: int, data: DeskResponse, db: AsyncSession = Depends(get_db)
):
    """Desk trader responds to a dispute."""
    try:
        dispute = await dispute_svc.desk_respond(db, dispute_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Notify VC analyst
    await _email.notify_desk_responded(
        {
            "dispute_id": dispute.dispute_id,
            "position_id": dispute.position_id,
            "desk_position": dispute.desk_position,
        },
        dispute.vc_analyst,
    )
    return dispute


@router.post("/{dispute_id}/resolve", response_model=DisputeOut)
async def resolve_dispute(
    dispute_id: int, data: DisputeResolve, db: AsyncSession = Depends(get_db)
):
    """Resolve a dispute with a final mark."""
    try:
        dispute = await dispute_svc.resolve_dispute(db, dispute_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Notify all parties
    recipients = [dispute.vc_analyst]
    if dispute.desk_trader:
        recipients.append(dispute.desk_trader)
    await _email.notify_resolved(
        {
            "dispute_id": dispute.dispute_id,
            "position_id": dispute.position_id,
            "resolution_type": dispute.resolution_type,
            "final_mark": str(dispute.final_mark),
        },
        recipients,
    )
    return dispute

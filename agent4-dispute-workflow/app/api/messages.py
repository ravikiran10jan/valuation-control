"""Dispute message thread API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import DisputeMessageCreate, DisputeMessageOut
from app.services.approvals import add_message, list_messages

router = APIRouter(prefix="/disputes/{dispute_id}/messages", tags=["Dispute Messages"])


@router.get("/", response_model=list[DisputeMessageOut])
async def get_messages(dispute_id: int, db: AsyncSession = Depends(get_db)):
    """List all messages in a dispute thread."""
    return await list_messages(db, dispute_id)


@router.post("/", response_model=DisputeMessageOut, status_code=201)
async def post_message(
    dispute_id: int,
    data: DisputeMessageCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a message to the dispute thread."""
    try:
        return await add_message(
            db,
            dispute_id,
            sender=data.sender,
            sender_role=data.sender_role,
            message_text=data.message_text,
            attachments=data.attachments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

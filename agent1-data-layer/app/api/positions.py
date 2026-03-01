"""Position CRUD API endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.schemas import PositionCreate, PositionOut, PositionUpdate
from app.services import positions as pos_svc

router = APIRouter(prefix="/positions", tags=["Positions"])


@router.get("/", response_model=list[PositionOut])
async def list_positions(
    asset_class: Optional[str] = None,
    exception_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List positions with optional filters."""
    return await pos_svc.list_positions(db, asset_class, exception_status, limit, offset)


@router.get("/{position_id}", response_model=PositionOut)
async def get_position(position_id: int, db: AsyncSession = Depends(get_db)):
    pos = await pos_svc.get_position(db, position_id)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return pos


@router.post("/", response_model=PositionOut, status_code=201)
async def create_position(data: PositionCreate, db: AsyncSession = Depends(get_db)):
    """Create a new position from a trading system feed."""
    try:
        return await pos_svc.create_position(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/{position_id}", response_model=PositionOut)
async def update_position(
    position_id: int, data: PositionUpdate, db: AsyncSession = Depends(get_db)
):
    pos = await pos_svc.update_position(db, position_id, data)
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    return pos


@router.delete("/{position_id}", status_code=204)
async def delete_position(position_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await pos_svc.delete_position(db, position_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Position not found")

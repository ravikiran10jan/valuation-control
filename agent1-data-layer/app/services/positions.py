"""Position CRUD service with validation."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.models.postgres import Position
from app.models.schemas import PositionCreate, PositionUpdate
from app.services.validation import DataValidator

log = structlog.get_logger()
_validator = DataValidator()


async def create_position(db: AsyncSession, data: PositionCreate) -> Position:
    # Validate before persisting
    report = _validator.validate_position(
        trade_id=data.trade_id,
        notional=data.notional,
        trade_date=data.trade_date,
        maturity_date=data.maturity_date,
        product_type=data.product_type,
        asset_class=data.asset_class,
    )
    if report.critical_failures:
        raise ValueError(
            f"Position validation failed: "
            + "; ".join(f.message for f in report.critical_failures)
        )

    pos = Position(**data.model_dump())

    # Auto-compute difference if both marks present
    if pos.desk_mark is not None and pos.vc_fair_value is not None:
        pos.difference = pos.desk_mark - pos.vc_fair_value
        if pos.vc_fair_value != 0:
            pos.difference_pct = (pos.difference / abs(pos.vc_fair_value)) * 100

    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    log.info("position_created", trade_id=data.trade_id, position_id=pos.position_id)
    return pos


async def get_position(db: AsyncSession, position_id: int) -> Position | None:
    return await db.get(Position, position_id)


async def get_position_by_trade_id(db: AsyncSession, trade_id: str) -> Position | None:
    result = await db.execute(select(Position).where(Position.trade_id == trade_id))
    return result.scalar_one_or_none()


async def list_positions(
    db: AsyncSession,
    asset_class: Optional[str] = None,
    exception_status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Position]:
    stmt = select(Position)
    if asset_class:
        stmt = stmt.where(Position.asset_class == asset_class)
    if exception_status:
        stmt = stmt.where(Position.exception_status == exception_status)
    stmt = stmt.order_by(Position.position_id.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_position(
    db: AsyncSession, position_id: int, data: PositionUpdate
) -> Position | None:
    pos = await db.get(Position, position_id)
    if pos is None:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(pos, field, value)

    # Recompute difference
    if pos.desk_mark is not None and pos.vc_fair_value is not None:
        pos.difference = pos.desk_mark - pos.vc_fair_value
        if pos.vc_fair_value != 0:
            pos.difference_pct = (pos.difference / abs(pos.vc_fair_value)) * 100

    await db.commit()
    await db.refresh(pos)
    log.info("position_updated", position_id=position_id)
    return pos


async def delete_position(db: AsyncSession, position_id: int) -> bool:
    pos = await db.get(Position, position_id)
    if pos is None:
        return False
    await db.delete(pos)
    await db.commit()
    log.info("position_deleted", position_id=position_id)
    return True

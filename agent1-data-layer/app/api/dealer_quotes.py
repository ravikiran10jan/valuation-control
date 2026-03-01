"""Dealer quote endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.postgres import DealerQuote
from app.models.schemas import DealerQuoteCreate, DealerQuoteOut

router = APIRouter(prefix="/dealer-quotes", tags=["Dealer Quotes"])


@router.get("/", response_model=list[DealerQuoteOut])
async def list_quotes(
    position_id: Optional[int] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DealerQuote)
    if position_id is not None:
        stmt = stmt.where(DealerQuote.position_id == position_id)
    stmt = stmt.order_by(DealerQuote.quote_id.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/", response_model=DealerQuoteOut, status_code=201)
async def create_quote(data: DealerQuoteCreate, db: AsyncSession = Depends(get_db)):
    quote = DealerQuote(**data.model_dump())
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote

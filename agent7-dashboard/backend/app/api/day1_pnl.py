"""Proxy routes for Agent 5 Day 1 P&L reserve endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from app.services.upstream import agent5_get, agent5_post

router = APIRouter(prefix="/api/day1-pnl", tags=["Day 1 P&L"])


@router.post("/reserve/calculate")
async def calculate_day1_reserve(req: dict):
    """Calculate Day 1 P&L reserve with classification and accounting."""
    return await agent5_post("/reserves/day1-pnl/reserve/calculate", json=req)


@router.post("/reserve/portfolio")
async def calculate_portfolio_reserve(req: dict):
    """Calculate Day 1 P&L reserves for a portfolio."""
    return await agent5_post("/reserves/day1-pnl/reserve/portfolio", json=req)


@router.post("/reserve/release-expired")
async def release_expired(req: dict):
    """Release Day 1 P&L reserve for expired position."""
    return await agent5_post("/reserves/day1-pnl/reserve/release-expired", json=req)


@router.get("/history/{position_id}")
async def day1_pnl_history(position_id: int):
    """Get Day 1 P&L history for a position."""
    return await agent5_get(f"/reserves/day1-pnl/history/{position_id}")

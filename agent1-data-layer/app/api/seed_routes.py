"""Seed data API endpoints.

Provides REST API for populating the Valuation Control system with
reference data from the Excel model. Supports seeding positions,
market data, and all data in one call.

Routes:
    POST /seed/positions     - Seed all 7 FX positions
    POST /seed/market-data   - Seed market data (spot, forward curve, vol surface)
    POST /seed/all           - Seed everything in the correct order
    GET  /seed/status        - Check what has been seeded
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.seed_data import (
    compute_fv_hierarchy_summary,
    get_seed_status,
    seed_all,
    seed_barrier_detail,
    seed_committee_agenda,
    seed_dealer_quotes,
    seed_exception_comments,
    seed_exceptions,
    seed_forward_curve,
    seed_market_data,
    seed_market_data_mongo,
    seed_positions,
    seed_valuation_comparisons,
    seed_vol_surface_mongo,
    seed_vol_surface_pg,
)

router = APIRouter(prefix="/seed", tags=["Seed Data"])


@router.post("/positions")
async def seed_positions_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed all 7 FX positions from the Excel model.

    Creates positions with pre-calculated differences and exception statuses.
    Also seeds the FX barrier detail for the DNT option and dealer quotes.
    Idempotent: skips positions whose trade_id already exists.
    """
    positions = await seed_positions(db)

    # Also seed barrier detail and dealer quotes alongside positions
    barrier = await seed_barrier_detail(db, positions)
    quotes = await seed_dealer_quotes(db, positions)

    # Seed comparisons and exceptions as they depend on positions
    comparisons = await seed_valuation_comparisons(db, positions)
    exceptions = await seed_exceptions(db, positions)
    comments = await seed_exception_comments(db, exceptions)
    agenda = await seed_committee_agenda(db, exceptions)

    await db.commit()

    return {
        "message": "Positions seeded successfully",
        "positions_created": len(positions),
        "barrier_detail_created": 1 if barrier else 0,
        "dealer_quotes_created": len(quotes),
        "valuation_comparisons_created": len(comparisons),
        "exceptions_created": len(exceptions),
        "exception_comments_created": len(comments),
        "committee_agenda_items_created": len(agenda),
    }


@router.post("/market-data")
async def seed_market_data_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed all market data: spot rates, forward curve, and vol surface.

    Seeds into both PostgreSQL (snapshots) and MongoDB (time-series history).
    Idempotent: skips data points that already exist.
    """
    # PostgreSQL
    md_snapshots = await seed_market_data(db)
    fwd_snapshots = await seed_forward_curve(db)
    vol_snapshots = await seed_vol_surface_pg(db)
    await db.commit()

    # MongoDB
    mongo_results = {}
    try:
        mongo_results["market_data_mongo_created"] = await seed_market_data_mongo()
    except Exception as e:
        mongo_results["market_data_mongo_error"] = str(e)

    try:
        mongo_results["vol_surface_mongo_created"] = await seed_vol_surface_mongo()
    except Exception as e:
        mongo_results["vol_surface_mongo_error"] = str(e)

    return {
        "message": "Market data seeded successfully",
        "market_data_snapshots_created": len(md_snapshots),
        "forward_curve_points_created": len(fwd_snapshots),
        "vol_surface_pg_created": len(vol_snapshots),
        **mongo_results,
    }


@router.post("/all")
async def seed_all_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed everything: positions, market data, dealer quotes, exceptions, and more.

    This is the master seed endpoint that populates the entire system
    with all data from the Excel model in the correct dependency order.
    Idempotent: skips data that already exists.

    Seeding order:
    1. Positions (7 FX positions)
    2. FX Barrier detail
    3. Market data snapshots (PostgreSQL)
    4. Forward curve (PostgreSQL)
    5. Vol surface (PostgreSQL + MongoDB)
    6. Market data time-series (MongoDB)
    7. Dealer quotes
    8. Valuation comparisons (IPV results)
    9. Exceptions (AMBER/RED)
    10. Exception comments
    11. Committee agenda items
    12. FV hierarchy summary
    """
    results = await seed_all(db)
    return {
        "message": "All data seeded successfully",
        **results,
    }


@router.get("/status")
async def seed_status_endpoint(db: AsyncSession = Depends(get_db)):
    """Check what data has been seeded into the system.

    Returns counts for all entity types and a boolean indicating
    whether the seed is complete (all expected data present).
    """
    status = await get_seed_status(db)

    # Also include FV hierarchy summary if positions exist
    if status["counts"]["positions"] > 0:
        status["fv_hierarchy_summary"] = await compute_fv_hierarchy_summary(db)

    return status

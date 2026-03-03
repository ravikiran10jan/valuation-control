"""Seed data API endpoints.

Provides REST API for populating the Valuation Control system with
reference data. Supports seeding positions across all asset classes,
market data, and all data in one call.

Routes:
    POST /seed/positions        - Seed original 7 FX positions
    POST /seed/rates            - Seed 14 Rates positions (IRS, Futures, Options, Munis)
    POST /seed/fx-products      - Seed 12 FX product positions (Forwards, Options, Exotics)
    POST /seed/credit-commodity - Seed 15 Credit/Commodity positions (CDS, CLO, CDO, MBS, Swaps)
    POST /seed/market-data      - Seed market data (spot, forward curve, vol surface, yield curves)
    POST /seed/all              - Seed everything in the correct order
    GET  /seed/status           - Check what has been seeded
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

    barrier = await seed_barrier_detail(db, positions)
    quotes = await seed_dealer_quotes(db, positions)
    comparisons = await seed_valuation_comparisons(db, positions)
    exceptions = await seed_exceptions(db, positions)
    comments = await seed_exception_comments(db, exceptions)
    agenda = await seed_committee_agenda(db, exceptions)

    await db.commit()

    return {
        "message": "FX positions seeded successfully",
        "positions_created": len(positions),
        "barrier_detail_created": 1 if barrier else 0,
        "dealer_quotes_created": len(quotes),
        "valuation_comparisons_created": len(comparisons),
        "exceptions_created": len(exceptions),
        "exception_comments_created": len(comments),
        "committee_agenda_items_created": len(agenda),
    }


@router.post("/rates")
async def seed_rates_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed 14 Rates positions: IRS, IR Futures (Bond/SOFR), IR Options, Municipal Bonds.

    Idempotent: skips positions whose trade_id already exists.
    """
    from app.seed_rates import seed_rates_positions, seed_rates_details

    positions = await seed_rates_positions(db)
    details = {}
    if positions:
        details = await seed_rates_details(db, positions)
    await db.commit()

    return {
        "message": "Rates positions seeded successfully",
        "positions_created": len(positions),
        "swap_details_created": len(details.get("swap_details", [])),
        "bond_details_created": len(details.get("bond_details", [])),
    }


@router.post("/fx-products")
async def seed_fx_products_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed 12 FX product positions: Forwards, Vanilla Options, Exotic Options.

    Idempotent: skips positions whose trade_id already exists.
    """
    from app.seed_fx_products import seed_fx_positions, seed_fx_details, seed_fx_dealer_quotes

    positions = await seed_fx_positions(db)
    details_count = 0
    quotes_count = 0
    if positions:
        details = await seed_fx_details(db, positions)
        details_count = len(details) if isinstance(details, (list, dict)) else 0
        quotes = await seed_fx_dealer_quotes(db, positions)
        quotes_count = len(quotes)
    await db.commit()

    return {
        "message": "FX product positions seeded successfully",
        "positions_created": len(positions),
        "barrier_details_created": details_count,
        "dealer_quotes_created": quotes_count,
    }


@router.post("/credit-commodity")
async def seed_credit_commodity_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed 15 Credit/Commodity positions: CDS, CLO, CDO, MBS, Commodity Swaps.

    Idempotent: skips positions whose trade_id already exists.
    """
    from app.seed_credit_commodity import (
        seed_credit_commodity_positions,
        seed_credit_details,
        seed_structured_product_details,
        seed_commodity_details,
        seed_credit_commodity_dealer_quotes,
    )

    positions = await seed_credit_commodity_positions(db)
    credit_count = 0
    struct_count = 0
    comm_count = 0
    quotes_count = 0
    if positions:
        credit_dets = await seed_credit_details(db, positions)
        credit_count = len(credit_dets)
        struct_dets = await seed_structured_product_details(db, positions)
        struct_count = len(struct_dets)
        comm_dets = await seed_commodity_details(db, positions)
        comm_count = len(comm_dets)
        quotes = await seed_credit_commodity_dealer_quotes(db, positions)
        quotes_count = len(quotes)
    await db.commit()

    return {
        "message": "Credit/Commodity positions seeded successfully",
        "positions_created": len(positions),
        "credit_details_created": credit_count,
        "structured_product_details_created": struct_count,
        "commodity_details_created": comm_count,
        "dealer_quotes_created": quotes_count,
    }


@router.post("/market-data")
async def seed_market_data_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed all market data: FX spot, forward curve, vol surface, yield curves, CDS spreads, commodities.

    Seeds into both PostgreSQL (snapshots) and MongoDB (time-series history).
    Idempotent: skips data points that already exist.
    """
    from app.seed_xva_market_data import seed_new_market_data

    # Original FX market data
    md_snapshots = await seed_market_data(db)
    fwd_snapshots = await seed_forward_curve(db)
    vol_snapshots = await seed_vol_surface_pg(db)

    # New market data (yield curves, CDS spreads, commodity prices, muni yields)
    new_md = await seed_new_market_data(db)

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
        "new_market_data_created": len(new_md),
        **mongo_results,
    }


@router.post("/all")
async def seed_all_endpoint(db: AsyncSession = Depends(get_db)):
    """Seed everything across all asset classes.

    Populates the entire system with 48 positions across FX, Rates, Credit,
    and Commodity asset classes, along with market data, XVA adjustments,
    dealer quotes, exceptions, comparisons, and committee agenda items.

    Idempotent: skips data that already exists.
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

    if status["counts"]["positions"] > 0:
        status["fv_hierarchy_summary"] = await compute_fv_hierarchy_summary(db)

    return status

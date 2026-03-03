"""Comprehensive data seeder for the Valuation Control system.

Seeds all 7 FX positions from the Excel model, along with market data,
dealer quotes, forward curves, vol surface, IPV tolerance results,
exception records, and FV hierarchy summary.

Can be run as a standalone script or invoked via the /seed/* API routes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory, get_mongo
from app.models.postgres import (
    CommitteeAgendaItem,
    DealerQuote,
    ExceptionComment,
    FXBarrierDetail,
    MarketDataSnapshot,
    Position,
    ValuationComparison,
    VCException,
)

logger = logging.getLogger(__name__)

# ── Valuation date used across all seed data ─────────────────────
VALUATION_DATE = date(2025, 2, 14)


# ══════════════════════════════════════════════════════════════════
# EMBEDDED REFERENCE DATA FROM EXCEL MODEL
# ══════════════════════════════════════════════════════════════════

POSITIONS: list[dict[str, Any]] = [
    {
        "position_id": "FX-SPOT-001",
        "trade_id": "T-20250214-001",
        "currency_pair": "EUR/USD",
        "product_type": "Spot",
        "asset_class": "FX",
        "notional": 150_000_000,
        "notional_usd": 150_000_000,
        "currency": "EUR",
        "desk_mark": 1.0825,
        "vc_fair_value": 1.0823,
        "book_value_usd": 162_375_000,
        "trade_date": "2025-02-14",
        "maturity_date": "2025-02-18",
        "settlement_date": "2025-02-18",
        "fair_value_level": "L1",
        "pricing_source": "WM/Reuters WMCO",
        "direction": "LONG",
        "desk": "G10 FX Spot",
        "trader": "J. Smith",
        "notes": "Long EUR 150m. G10 liquid. Minimal spread.",
    },
    {
        "position_id": "FX-SPOT-002",
        "trade_id": "T-20250213-002",
        "currency_pair": "GBP/USD",
        "product_type": "Spot",
        "asset_class": "FX",
        "notional": 85_000_000,
        "notional_usd": 85_000_000,
        "currency": "GBP",
        "desk_mark": 1.2648,
        "vc_fair_value": 1.2645,
        "book_value_usd": 107_508_000,
        "trade_date": "2025-02-13",
        "maturity_date": "2025-02-18",
        "settlement_date": "2025-02-18",
        "fair_value_level": "L1",
        "pricing_source": "WM/Reuters WMCO",
        "direction": "LONG",
        "desk": "G10 FX Spot",
        "trader": "J. Smith",
        "notes": "Long GBP 85m. G10 liquid. Cable pair.",
    },
    {
        "position_id": "FX-SPOT-003",
        "trade_id": "T-20250212-003",
        "currency_pair": "USD/JPY",
        "product_type": "Spot",
        "asset_class": "FX",
        "notional": 50_000_000,
        "notional_usd": 50_000_000,
        "currency": "USD",
        "desk_mark": 149.85,
        "vc_fair_value": 149.88,
        "book_value_usd": 50_000_000,
        "trade_date": "2025-02-12",
        "maturity_date": "2025-02-18",
        "settlement_date": "2025-02-18",
        "fair_value_level": "L1",
        "pricing_source": "WM/Reuters WMCO",
        "direction": "SHORT",
        "desk": "G10 FX Spot",
        "trader": "A. Johnson",
        "notes": "Short JPY (long USD). Yen strength vs desk.",
    },
    {
        "position_id": "FX-SPOT-004",
        "trade_id": "T-20250210-004",
        "currency_pair": "USD/TRY",
        "product_type": "Spot",
        "asset_class": "FX",
        "notional": 25_000_000,
        "notional_usd": 25_000_000,
        "currency": "USD",
        "desk_mark": 32.45,
        "vc_fair_value": 35.12,
        "book_value_usd": 25_000_000,
        "trade_date": "2025-02-10",
        "maturity_date": "2025-02-18",
        "settlement_date": "2025-02-18",
        "fair_value_level": "L2",
        "pricing_source": "WM/Reuters WMCO",
        "direction": "LONG",
        "desk": "EM FX Spot",
        "trader": "M. Williams",
        "notes": "Long USD vs TRY. EM volatile. Desk stale. RED breach.",
    },
    {
        "position_id": "FX-SPOT-005",
        "trade_id": "T-20250211-005",
        "currency_pair": "USD/BRL",
        "product_type": "Spot",
        "asset_class": "FX",
        "notional": 10_000_000,
        "notional_usd": 10_000_000,
        "currency": "USD",
        "desk_mark": 5.12,
        "vc_fair_value": 5.18,
        "book_value_usd": 10_000_000,
        "trade_date": "2025-02-11",
        "maturity_date": "2025-02-18",
        "settlement_date": "2025-02-18",
        "fair_value_level": "L2",
        "pricing_source": "WM/Reuters WMCO",
        "direction": "LONG",
        "desk": "EM FX Spot",
        "trader": "M. Williams",
        "notes": "Long USD vs BRL. EM moderate vol. AMBER breach.",
    },
    {
        "position_id": "FX-FWD-001",
        "trade_id": "T-20250120-006",
        "currency_pair": "EUR/USD",
        "product_type": "Forward",
        "asset_class": "FX",
        "notional": 120_000_000,
        "notional_usd": 120_000_000,
        "currency": "EUR",
        "desk_mark": 1.095,
        "vc_fair_value": 1.0948,
        "book_value_usd": 131_400_000,
        "trade_date": "2025-01-20",
        "maturity_date": "2026-02-15",
        "settlement_date": "2026-02-17",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg FXFA",
        "direction": "LONG",
        "desk": "G10 FX Forwards",
        "trader": "R. Chen",
        "notes": "Long EUR forward. Forward points timing diff.",
    },
    {
        "position_id": "FX-OPT-001",
        "trade_id": "T-20250105-007",
        "currency_pair": "EUR/USD",
        "product_type": "Barrier",
        "asset_class": "FX",
        "notional": 50_000_000,
        "notional_usd": 50_000_000,
        "currency": "EUR",
        "desk_mark": 425_000,
        "vc_fair_value": 306_000,
        "book_value_usd": 850_000,
        "trade_date": "2025-01-05",
        "maturity_date": "2025-12-31",
        "settlement_date": "2026-01-02",
        "fair_value_level": "L3",
        "pricing_source": "Internal BS Model",
        "direction": "SHORT",
        "desk": "FX Exotics",
        "trader": "S. Park",
        "notes": "Double-no-touch 1.05/1.12 barriers. Vol surface calibration. RED breach.",
    },
]

MARKET_DATA: dict[str, dict[str, Any]] = {
    "EUR/USD": {"spot": 1.0823, "bid": 1.0822, "ask": 1.0824, "spread_bps": 2},
    "GBP/USD": {"spot": 1.2645, "bid": 1.2643, "ask": 1.2647, "spread_bps": 4},
    "USD/JPY": {"spot": 149.88, "bid": 149.86, "ask": 149.90, "spread_bps": 4},
    "USD/TRY": {"spot": 35.12, "bid": 35.08, "ask": 35.16, "spread_bps": 23},
    "USD/BRL": {"spot": 5.18, "bid": 5.17, "ask": 5.19, "spread_bps": 39},
}

FORWARD_CURVE: list[dict[str, Any]] = [
    {
        "tenor": "1M",
        "days": 30,
        "spot": 1.0823,
        "eur_rate": 0.0425,
        "usd_rate": 0.0525,
        "fwd_points_pips": 9,
        "outright": 1.0832,
    },
    {
        "tenor": "3M",
        "days": 90,
        "spot": 1.0823,
        "eur_rate": 0.0425,
        "usd_rate": 0.0525,
        "fwd_points_pips": 27,
        "outright": 1.0850,
    },
    {
        "tenor": "6M",
        "days": 180,
        "spot": 1.0823,
        "eur_rate": 0.0425,
        "usd_rate": 0.0525,
        "fwd_points_pips": 54,
        "outright": 1.0877,
    },
    {
        "tenor": "1Y",
        "days": 360,
        "spot": 1.0823,
        "eur_rate": 0.0425,
        "usd_rate": 0.0525,
        "fwd_points_pips": 108,
        "outright": 1.0931,
    },
]

VOL_SURFACE: dict[str, Any] = {
    "atm_vol": 0.068,
    "risk_reversal_25d": 0.008,
    "butterfly_25d": 0.003,
    "tenors": {"1M": 0.065, "3M": 0.067, "6M": 0.068, "1Y": 0.068},
}

DEALER_QUOTES: list[dict[str, Any]] = [
    {"dealer": "JPMorgan", "fair_value": 305_000, "survival_prob": 0.717},
    {"dealer": "Goldman Sachs", "fair_value": 308_000, "survival_prob": 0.724},
    {"dealer": "Citigroup", "fair_value": 302_000, "survival_prob": 0.710},
]

BARRIER_PARAMS: dict[str, Any] = {
    "spot": 1.0823,
    "lower_barrier": 1.05,
    "upper_barrier": 1.12,
    "volatility": 0.068,
    "time_to_maturity": 0.8767,
    "r_domestic": 0.0525,
    "r_foreign": 0.0425,
    "premium": 425_000,
    "notional": 50_000_000,
}

TOLERANCE_THRESHOLDS: dict[str, dict[str, float]] = {
    "G10_SPOT": {"green_bps": 5, "amber_bps": 10, "red_bps": 10},
    "EM_SPOT": {"green_pct": 2.0, "amber_pct": 5.0, "red_pct": 5.0},
    "FX_FORWARDS": {"green_bps": 10, "amber_bps": 20, "red_bps": 20},
    "FX_OPTIONS": {"green_pct": 5.0, "amber_pct": 10.0, "red_pct": 10.0},
}


# ══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════


def _parse_date(value: str) -> date:
    """Parse an ISO-format date string."""
    return date.fromisoformat(value)


def _compute_difference(desk_mark: float, vc_fair_value: float) -> tuple[Decimal, Decimal]:
    """Return (difference, difference_pct) between desk mark and VC fair value."""
    diff = Decimal(str(desk_mark)) - Decimal(str(vc_fair_value))
    if vc_fair_value != 0:
        diff_pct = (diff / abs(Decimal(str(vc_fair_value)))) * 100
    else:
        diff_pct = Decimal("0")
    return diff, diff_pct


def _classify_exception(
    position_data: dict[str, Any],
    desk_mark: float,
    vc_fair_value: float,
) -> str:
    """Classify a position as GREEN, AMBER, or RED based on IPV tolerance thresholds.

    Uses product-type-specific thresholds from the Excel model:
    - G10 Spot: bps-based (5 / 10)
    - EM Spot: percentage-based (2% / 5%)
    - FX Forwards: bps-based (10 / 20)
    - FX Options/Barrier: percentage-based (5% / 10%)
    """
    product_type = position_data["product_type"]
    desk_name = position_data.get("desk", "")

    if vc_fair_value == 0:
        return "RED"

    diff_pct = abs((desk_mark - vc_fair_value) / vc_fair_value) * 100

    # Determine which threshold bucket applies
    if product_type == "Spot" and "EM" in desk_name:
        # EM Spot: percentage thresholds
        thresholds = TOLERANCE_THRESHOLDS["EM_SPOT"]
        if diff_pct > thresholds["red_pct"]:
            return "RED"
        elif diff_pct > thresholds["green_pct"]:
            return "AMBER"
        else:
            return "GREEN"

    elif product_type == "Spot":
        # G10 Spot: bps thresholds (convert pct to bps: 1 bps = 0.01%)
        diff_bps = diff_pct * 100  # pct * 100 = bps
        thresholds = TOLERANCE_THRESHOLDS["G10_SPOT"]
        if diff_bps > thresholds["red_bps"]:
            return "RED"
        elif diff_bps > thresholds["green_bps"]:
            return "AMBER"
        else:
            return "GREEN"

    elif product_type == "Forward":
        # FX Forwards: bps thresholds
        diff_bps = diff_pct * 100
        thresholds = TOLERANCE_THRESHOLDS["FX_FORWARDS"]
        if diff_bps > thresholds["red_bps"]:
            return "RED"
        elif diff_bps > thresholds["green_bps"]:
            return "AMBER"
        else:
            return "GREEN"

    elif product_type in ("Barrier", "Option"):
        # FX Options: percentage thresholds
        thresholds = TOLERANCE_THRESHOLDS["FX_OPTIONS"]
        if diff_pct > thresholds["red_pct"]:
            return "RED"
        elif diff_pct > thresholds["green_pct"]:
            return "AMBER"
        else:
            return "GREEN"

    # Fallback: generic percentage-based
    if diff_pct > 10.0:
        return "RED"
    elif diff_pct > 5.0:
        return "AMBER"
    return "GREEN"


# ══════════════════════════════════════════════════════════════════
# SEEDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════


async def seed_positions(db: AsyncSession) -> list[Position]:
    """Seed all 7 FX positions. Returns the created ORM objects (with PK assigned).

    Handles idempotency: skips positions whose trade_id already exists.
    """
    created: list[Position] = []

    for pos_data in POSITIONS:
        # Check for existing
        existing = await db.execute(
            select(Position).where(Position.trade_id == pos_data["trade_id"])
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("Position %s already exists, skipping", pos_data["trade_id"])
            continue

        desk_mark = pos_data["desk_mark"]
        vc_fair_value = pos_data["vc_fair_value"]
        diff, diff_pct = _compute_difference(desk_mark, vc_fair_value)
        exception_status = _classify_exception(pos_data, desk_mark, vc_fair_value)

        pos = Position(
            trade_id=pos_data["trade_id"],
            product_type=pos_data["product_type"],
            asset_class=pos_data["asset_class"],
            currency_pair=pos_data["currency_pair"],
            notional=Decimal(str(pos_data["notional"])),
            notional_usd=Decimal(str(pos_data["notional_usd"])),
            currency=pos_data["currency"],
            trade_date=_parse_date(pos_data["trade_date"]),
            maturity_date=_parse_date(pos_data["maturity_date"]),
            settlement_date=_parse_date(pos_data["settlement_date"]),
            counterparty=pos_data.get("desk", None),  # store desk as counterparty context
            desk_mark=Decimal(str(desk_mark)),
            vc_fair_value=Decimal(str(vc_fair_value)),
            book_value_usd=Decimal(str(pos_data["book_value_usd"])),
            difference=diff,
            difference_pct=diff_pct,
            exception_status=exception_status,
            fair_value_level=pos_data["fair_value_level"],
            pricing_source=pos_data["pricing_source"],
            valuation_date=VALUATION_DATE,
        )
        db.add(pos)
        created.append(pos)

    if created:
        await db.flush()  # assign PKs
        logger.info("Seeded %d positions", len(created))

    return created


async def seed_barrier_detail(db: AsyncSession, positions: list[Position] | None = None) -> FXBarrierDetail | None:
    """Seed FX barrier detail for FX-OPT-001.

    If positions list is not provided, looks up the barrier position by trade_id.
    """
    # Find the barrier position
    barrier_pos: Position | None = None
    if positions:
        for p in positions:
            if p.trade_id == "T-20250105-007":
                barrier_pos = p
                break

    if barrier_pos is None:
        result = await db.execute(
            select(Position).where(Position.trade_id == "T-20250105-007")
        )
        barrier_pos = result.scalar_one_or_none()

    if barrier_pos is None:
        logger.warning("Barrier position T-20250105-007 not found, skipping barrier detail")
        return None

    # Check for existing detail
    existing = await db.get(FXBarrierDetail, barrier_pos.position_id)
    if existing is not None:
        logger.info("Barrier detail already exists for position %d, skipping", barrier_pos.position_id)
        return existing

    # Average survival probability from dealer quotes
    avg_survival = sum(q["survival_prob"] for q in DEALER_QUOTES) / len(DEALER_QUOTES)

    detail = FXBarrierDetail(
        position_id=barrier_pos.position_id,
        currency_pair="EUR/USD",
        spot_ref=Decimal(str(BARRIER_PARAMS["spot"])),
        lower_barrier=Decimal(str(BARRIER_PARAMS["lower_barrier"])),
        upper_barrier=Decimal(str(BARRIER_PARAMS["upper_barrier"])),
        barrier_type="DNT",  # Double-No-Touch
        volatility=Decimal(str(BARRIER_PARAMS["volatility"])),
        time_to_expiry=Decimal(str(BARRIER_PARAMS["time_to_maturity"])),
        domestic_rate=Decimal(str(BARRIER_PARAMS["r_domestic"])),
        foreign_rate=Decimal(str(BARRIER_PARAMS["r_foreign"])),
        survival_probability=Decimal(str(round(avg_survival, 4))),
        premium_market=Decimal(str(BARRIER_PARAMS["premium"])),
        premium_model=Decimal("306000"),  # VC fair value consensus
    )
    db.add(detail)
    await db.flush()
    logger.info("Seeded FX barrier detail for position %d", barrier_pos.position_id)
    return detail


async def seed_market_data(db: AsyncSession) -> list[MarketDataSnapshot]:
    """Seed market data snapshots (WM/Reuters 4pm Fix) into PostgreSQL.

    Stores spot, bid, ask, and spread for each currency pair.
    """
    created: list[MarketDataSnapshot] = []

    for pair, data in MARKET_DATA.items():
        for field_suffix, value in [
            ("spot", data["spot"]),
            ("bid", data["bid"]),
            ("ask", data["ask"]),
            ("spread_bps", data["spread_bps"]),
        ]:
            field_name = f"{pair}_{field_suffix}"

            # Idempotency check
            existing = await db.execute(
                select(MarketDataSnapshot).where(
                    MarketDataSnapshot.valuation_date == VALUATION_DATE,
                    MarketDataSnapshot.field_name == field_name,
                    MarketDataSnapshot.data_source == "WM/Reuters",
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            snapshot = MarketDataSnapshot(
                valuation_date=VALUATION_DATE,
                data_source="WM/Reuters",
                field_name=field_name,
                field_value=Decimal(str(value)),
            )
            db.add(snapshot)
            created.append(snapshot)

    if created:
        await db.flush()
        logger.info("Seeded %d market data snapshots", len(created))

    return created


async def seed_forward_curve(db: AsyncSession) -> list[MarketDataSnapshot]:
    """Seed EUR/USD forward curve data points into PostgreSQL."""
    created: list[MarketDataSnapshot] = []

    for point in FORWARD_CURVE:
        fields = {
            f"EURUSD_fwd_{point['tenor']}_eur_rate": point["eur_rate"],
            f"EURUSD_fwd_{point['tenor']}_usd_rate": point["usd_rate"],
            f"EURUSD_fwd_{point['tenor']}_fwd_points_pips": point["fwd_points_pips"],
            f"EURUSD_fwd_{point['tenor']}_outright": point["outright"],
            f"EURUSD_fwd_{point['tenor']}_days": point["days"],
        }

        for field_name, value in fields.items():
            existing = await db.execute(
                select(MarketDataSnapshot).where(
                    MarketDataSnapshot.valuation_date == VALUATION_DATE,
                    MarketDataSnapshot.field_name == field_name,
                    MarketDataSnapshot.data_source == "Bloomberg FXFA",
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            snapshot = MarketDataSnapshot(
                valuation_date=VALUATION_DATE,
                data_source="Bloomberg FXFA",
                field_name=field_name,
                field_value=Decimal(str(value)),
            )
            db.add(snapshot)
            created.append(snapshot)

    if created:
        await db.flush()
        logger.info("Seeded %d forward curve data points", len(created))

    return created


async def seed_vol_surface_pg(db: AsyncSession) -> list[MarketDataSnapshot]:
    """Seed EUR/USD vol surface data into PostgreSQL snapshots."""
    created: list[MarketDataSnapshot] = []

    # ATM vol and smile parameters
    vol_fields = {
        "EURUSD_vol_atm": VOL_SURFACE["atm_vol"],
        "EURUSD_vol_rr25d": VOL_SURFACE["risk_reversal_25d"],
        "EURUSD_vol_bf25d": VOL_SURFACE["butterfly_25d"],
    }

    # Per-tenor vols
    for tenor, vol in VOL_SURFACE["tenors"].items():
        vol_fields[f"EURUSD_vol_{tenor}"] = vol

    for field_name, value in vol_fields.items():
        existing = await db.execute(
            select(MarketDataSnapshot).where(
                MarketDataSnapshot.valuation_date == VALUATION_DATE,
                MarketDataSnapshot.field_name == field_name,
                MarketDataSnapshot.data_source == "Bloomberg",
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        snapshot = MarketDataSnapshot(
            valuation_date=VALUATION_DATE,
            data_source="Bloomberg",
            field_name=field_name,
            field_value=Decimal(str(value)),
        )
        db.add(snapshot)
        created.append(snapshot)

    if created:
        await db.flush()
        logger.info("Seeded %d vol surface data points", len(created))

    return created


async def seed_vol_surface_mongo() -> int:
    """Seed EUR/USD vol surface into MongoDB time-series history."""
    mongo = get_mongo()
    collection = mongo["vol_surface_history"]
    inserted = 0

    as_of_dt = datetime.combine(VALUATION_DATE, datetime.min.time())

    # ATM vol across tenors
    for tenor, vol in VOL_SURFACE["tenors"].items():
        existing = await collection.find_one({
            "currency_pair": "EUR/USD",
            "tenor": tenor,
            "delta": "ATM",
            "date": as_of_dt,
        })
        if existing:
            continue

        await collection.insert_one({
            "currency_pair": "EUR/USD",
            "tenor": tenor,
            "delta": "ATM",
            "volatility": vol,
            "date": as_of_dt,
            "source": "Bloomberg",
            "timestamp": datetime.utcnow(),
        })
        inserted += 1

    # 25-delta risk reversal and butterfly (for 1Y tenor as representative)
    for delta_label, value in [
        ("25D_RR", VOL_SURFACE["risk_reversal_25d"]),
        ("25D_BF", VOL_SURFACE["butterfly_25d"]),
    ]:
        existing = await collection.find_one({
            "currency_pair": "EUR/USD",
            "tenor": "1Y",
            "delta": delta_label,
            "date": as_of_dt,
        })
        if existing:
            continue

        await collection.insert_one({
            "currency_pair": "EUR/USD",
            "tenor": "1Y",
            "delta": delta_label,
            "volatility": value,
            "date": as_of_dt,
            "source": "Bloomberg",
            "timestamp": datetime.utcnow(),
        })
        inserted += 1

    if inserted:
        logger.info("Seeded %d vol surface points into MongoDB", inserted)

    return inserted


async def seed_market_data_mongo() -> int:
    """Seed spot rates into MongoDB market_data_history."""
    mongo = get_mongo()
    collection = mongo["market_data_history"]
    inserted = 0

    as_of_dt = datetime.combine(VALUATION_DATE, datetime.min.time())

    for pair, data in MARKET_DATA.items():
        for suffix, value in [("spot", data["spot"]), ("bid", data["bid"]), ("ask", data["ask"])]:
            field = f"{pair}_{suffix}"
            existing = await collection.find_one({
                "field": field,
                "date": as_of_dt,
                "source": "WM/Reuters",
            })
            if existing:
                continue

            await collection.insert_one({
                "field": field,
                "date": as_of_dt,
                "value": value,
                "source": "WM/Reuters",
                "timestamp": datetime.utcnow(),
            })
            inserted += 1

    # Forward curve spot data in mongo as well
    for point in FORWARD_CURVE:
        field = f"EUR/USD_fwd_outright_{point['tenor']}"
        existing = await collection.find_one({
            "field": field,
            "date": as_of_dt,
            "source": "Bloomberg FXFA",
        })
        if existing:
            continue

        await collection.insert_one({
            "field": field,
            "date": as_of_dt,
            "value": point["outright"],
            "source": "Bloomberg FXFA",
            "timestamp": datetime.utcnow(),
        })
        inserted += 1

    if inserted:
        logger.info("Seeded %d market data points into MongoDB", inserted)

    return inserted


async def seed_dealer_quotes(db: AsyncSession, positions: list[Position] | None = None) -> list[DealerQuote]:
    """Seed dealer quotes for the barrier option position (FX-OPT-001)."""
    # Find the barrier position
    barrier_pos: Position | None = None
    if positions:
        for p in positions:
            if p.trade_id == "T-20250105-007":
                barrier_pos = p
                break

    if barrier_pos is None:
        result = await db.execute(
            select(Position).where(Position.trade_id == "T-20250105-007")
        )
        barrier_pos = result.scalar_one_or_none()

    if barrier_pos is None:
        logger.warning("Barrier position not found, skipping dealer quotes")
        return []

    created: list[DealerQuote] = []

    for quote_data in DEALER_QUOTES:
        # Idempotency
        existing = await db.execute(
            select(DealerQuote).where(
                DealerQuote.position_id == barrier_pos.position_id,
                DealerQuote.dealer_name == quote_data["dealer"],
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        quote = DealerQuote(
            position_id=barrier_pos.position_id,
            dealer_name=quote_data["dealer"],
            quote_value=Decimal(str(quote_data["fair_value"])),
            quote_date=VALUATION_DATE,
            quote_type="Mid",
        )
        db.add(quote)
        created.append(quote)

    if created:
        await db.flush()
        logger.info("Seeded %d dealer quotes", len(created))

    return created


async def seed_valuation_comparisons(db: AsyncSession, positions: list[Position] | None = None) -> list[ValuationComparison]:
    """Create valuation comparison records for all positions (IPV tolerance results)."""
    if not positions:
        result = await db.execute(select(Position))
        positions = list(result.scalars().all())

    created: list[ValuationComparison] = []

    for pos in positions:
        # Idempotency
        existing = await db.execute(
            select(ValuationComparison).where(
                ValuationComparison.position_id == pos.position_id,
                ValuationComparison.comparison_date == VALUATION_DATE,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        desk_mark = float(pos.desk_mark) if pos.desk_mark is not None else 0
        vc_fair_value = float(pos.vc_fair_value) if pos.vc_fair_value is not None else 0
        diff = Decimal(str(desk_mark - vc_fair_value))

        if vc_fair_value != 0:
            diff_pct = Decimal(str(round((desk_mark - vc_fair_value) / abs(vc_fair_value) * 100, 2)))
        else:
            diff_pct = Decimal("0")

        status = pos.exception_status or "GREEN"

        comp = ValuationComparison(
            position_id=pos.position_id,
            desk_mark=Decimal(str(desk_mark)),
            vc_fair_value=Decimal(str(vc_fair_value)),
            difference=diff,
            difference_pct=diff_pct,
            status=status,
            comparison_date=VALUATION_DATE,
        )
        db.add(comp)
        created.append(comp)

    if created:
        await db.flush()
        logger.info("Seeded %d valuation comparisons", len(created))

    return created


async def seed_exceptions(db: AsyncSession, positions: list[Position] | None = None) -> list[VCException]:
    """Create exception records for AMBER and RED positions.

    Expected exceptions:
    - FX-SPOT-004 (USD/TRY): RED - desk mark 32.45 vs VC 35.12 (~7.6%)
    - FX-SPOT-005 (USD/BRL): AMBER - desk mark 5.12 vs VC 5.18 (~1.16% => ~2% using EM thresholds mapping)
    - FX-OPT-001 (EUR/USD Barrier): RED - desk mark 425k vs VC 306k (~28%)
    """
    if not positions:
        result = await db.execute(select(Position))
        positions = list(result.scalars().all())

    exception_positions = [p for p in positions if p.exception_status in ("AMBER", "RED")]
    created: list[VCException] = []

    for pos in exception_positions:
        # Idempotency
        existing = await db.execute(
            select(VCException).where(
                VCException.position_id == pos.position_id,
                VCException.status != "RESOLVED",
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        desk_mark = float(pos.desk_mark) if pos.desk_mark is not None else 0
        vc_fair_value = float(pos.vc_fair_value) if pos.vc_fair_value is not None else 0
        diff = round(desk_mark - vc_fair_value, 2)

        if vc_fair_value != 0:
            diff_pct = round((desk_mark - vc_fair_value) / abs(vc_fair_value) * 100, 2)
        else:
            diff_pct = 0

        severity = pos.exception_status  # AMBER or RED

        # Determine days open based on trade date
        trade_dt = pos.trade_date or VALUATION_DATE
        days_open = (VALUATION_DATE - trade_dt).days

        # Assign analyst
        if severity == "RED":
            assigned_to = "VC Senior Analyst"
            escalation_level = 2  # already escalated to Manager
        else:
            assigned_to = "VC Analyst"
            escalation_level = 1

        exc = VCException(
            position_id=pos.position_id,
            difference=Decimal(str(diff)),
            difference_pct=Decimal(str(diff_pct)),
            status="OPEN",
            severity=severity,
            created_date=VALUATION_DATE,
            assigned_to=assigned_to,
            days_open=days_open,
            escalation_level=escalation_level,
        )
        db.add(exc)
        created.append(exc)

    if created:
        await db.flush()
        logger.info("Seeded %d exception records", len(created))

    return created


async def seed_exception_comments(db: AsyncSession, exceptions: list[VCException] | None = None) -> list[ExceptionComment]:
    """Add initial investigation comments to exception records."""
    if not exceptions:
        result = await db.execute(select(VCException).where(VCException.status == "OPEN"))
        exceptions = list(result.scalars().all())

    created: list[ExceptionComment] = []

    # Predefined comments for context
    comment_map: dict[str, list[dict[str, str]]] = {}

    # Find positions linked to exceptions for context
    for exc in exceptions:
        pos = await db.get(Position, exc.position_id)
        if pos is None:
            continue

        # Idempotency: check if comments already exist
        existing = await db.execute(
            select(func.count(ExceptionComment.comment_id)).where(
                ExceptionComment.exception_id == exc.exception_id,
            )
        )
        count = existing.scalar()
        if count and count > 0:
            continue

        if pos.trade_id == "T-20250210-004":
            # USD/TRY RED
            comments = [
                {
                    "user_name": "VC Senior Analyst",
                    "comment_text": (
                        "USD/TRY desk mark 32.45 is significantly stale versus "
                        "WM/Reuters 4pm fix of 35.12. Difference of -7.60% exceeds "
                        "EM RED threshold of 5%. Desk appears to be marking off a "
                        "prior-day rate. Requesting trader to update mark."
                    ),
                },
                {
                    "user_name": "M. Williams (Trader)",
                    "comment_text": (
                        "Acknowledged. TRY market was volatile on 2/10 when trade was "
                        "booked. Will update mark to reflect current market conditions."
                    ),
                },
            ]
        elif pos.trade_id == "T-20250211-005":
            # USD/BRL AMBER
            comments = [
                {
                    "user_name": "VC Analyst",
                    "comment_text": (
                        "USD/BRL desk mark 5.12 vs VC fair value 5.18. Difference "
                        "of -1.16% is within AMBER range for EM pairs (2-5% threshold). "
                        "BRL experienced moderate volatility this week. Monitoring."
                    ),
                },
            ]
        elif pos.trade_id == "T-20250105-007":
            # EUR/USD Barrier RED
            comments = [
                {
                    "user_name": "VC Senior Analyst",
                    "comment_text": (
                        "EUR/USD DNT barrier option desk mark 425,000 vs VC consensus "
                        "306,000 (avg of 3 dealer quotes: JPM 305k, GS 308k, Citi 302k). "
                        "Difference of 38.89% far exceeds RED threshold. Desk model may "
                        "have incorrect vol surface calibration or barrier proximity "
                        "adjustment. Escalating to Valuation Committee."
                    ),
                },
                {
                    "user_name": "S. Park (Trader)",
                    "comment_text": (
                        "Our internal model uses a different vol smile interpolation "
                        "near the barriers. We believe the dealer marks do not properly "
                        "account for the barrier proximity premium. Requesting committee "
                        "review."
                    ),
                },
            ]
        else:
            comments = []

        for c in comments:
            comment = ExceptionComment(
                exception_id=exc.exception_id,
                user_name=c["user_name"],
                comment_text=c["comment_text"],
            )
            db.add(comment)
            created.append(comment)

    if created:
        await db.flush()
        logger.info("Seeded %d exception comments", len(created))

    return created


async def seed_committee_agenda(db: AsyncSession, exceptions: list[VCException] | None = None) -> list[CommitteeAgendaItem]:
    """Create committee agenda items for RED exceptions."""
    if not exceptions:
        result = await db.execute(
            select(VCException).where(VCException.severity == "RED", VCException.status != "RESOLVED")
        )
        exceptions = list(result.scalars().all())

    # Next Wednesday from valuation date
    from datetime import timedelta
    days_ahead = (2 - VALUATION_DATE.weekday()) % 7  # Wednesday = 2
    if days_ahead == 0:
        days_ahead = 7
    next_wednesday = VALUATION_DATE + timedelta(days=days_ahead)

    created: list[CommitteeAgendaItem] = []

    for exc in exceptions:
        if exc.severity != "RED":
            continue

        # Idempotency
        existing = await db.execute(
            select(CommitteeAgendaItem).where(
                CommitteeAgendaItem.exception_id == exc.exception_id,
                CommitteeAgendaItem.status == "PENDING_COMMITTEE",
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        agenda = CommitteeAgendaItem(
            exception_id=exc.exception_id,
            position_id=exc.position_id,
            difference=exc.difference,
            status="PENDING_COMMITTEE",
            meeting_date=next_wednesday,
        )
        db.add(agenda)
        created.append(agenda)

    if created:
        await db.flush()
        logger.info("Seeded %d committee agenda items", len(created))

    return created


# ══════════════════════════════════════════════════════════════════
# FV HIERARCHY SUMMARY
# ══════════════════════════════════════════════════════════════════


async def compute_fv_hierarchy_summary(db: AsyncSession) -> dict[str, Any]:
    """Compute and return Fair Value hierarchy summary across all positions.

    FV Levels:
    - L1: Observable market prices (G10 spots)
    - L2: Observable inputs (EM spots, forwards)
    - L3: Significant unobservable inputs (barrier options)
    """
    result = await db.execute(select(Position))
    positions = list(result.scalars().all())

    summary: dict[str, dict[str, Any]] = {
        "L1": {"count": 0, "total_notional_usd": Decimal("0"), "positions": []},
        "L2": {"count": 0, "total_notional_usd": Decimal("0"), "positions": []},
        "L3": {"count": 0, "total_notional_usd": Decimal("0"), "positions": []},
    }

    for pos in positions:
        level = pos.fair_value_level or "L2"
        if level not in summary:
            summary[level] = {"count": 0, "total_notional_usd": Decimal("0"), "positions": []}

        summary[level]["count"] += 1
        summary[level]["total_notional_usd"] += pos.notional_usd or Decimal("0")
        summary[level]["positions"].append({
            "position_id": pos.position_id,
            "trade_id": pos.trade_id,
            "currency_pair": pos.currency_pair,
            "product_type": pos.product_type,
            "notional_usd": float(pos.notional_usd) if pos.notional_usd else 0,
        })

    total_notional = sum(s["total_notional_usd"] for s in summary.values())

    return {
        "valuation_date": VALUATION_DATE.isoformat(),
        "total_positions": len(positions),
        "total_notional_usd": float(total_notional),
        "hierarchy": {
            level: {
                "count": data["count"],
                "total_notional_usd": float(data["total_notional_usd"]),
                "pct_of_total": round(
                    float(data["total_notional_usd"]) / float(total_notional) * 100, 2
                ) if total_notional > 0 else 0,
                "positions": data["positions"],
            }
            for level, data in summary.items()
        },
    }


# ══════════════════════════════════════════════════════════════════
# SEED STATUS CHECKER
# ══════════════════════════════════════════════════════════════════


async def get_seed_status(db: AsyncSession) -> dict[str, Any]:
    """Return a summary of what has been seeded."""
    pos_count = (await db.execute(select(func.count(Position.position_id)))).scalar() or 0
    mds_count = (await db.execute(select(func.count(MarketDataSnapshot.snapshot_id)))).scalar() or 0
    dq_count = (await db.execute(select(func.count(DealerQuote.quote_id)))).scalar() or 0
    exc_count = (await db.execute(select(func.count(VCException.exception_id)))).scalar() or 0
    comp_count = (await db.execute(select(func.count(ValuationComparison.comparison_id)))).scalar() or 0
    agenda_count = (await db.execute(select(func.count(CommitteeAgendaItem.agenda_id)))).scalar() or 0
    barrier_count = (await db.execute(select(func.count(FXBarrierDetail.position_id)))).scalar() or 0

    # MongoDB counts
    try:
        mongo = get_mongo()
        mongo_md_count = await mongo["market_data_history"].count_documents({})
        mongo_vol_count = await mongo["vol_surface_history"].count_documents({})
    except Exception:
        mongo_md_count = -1
        mongo_vol_count = -1

    is_complete = (
        pos_count >= 48
        and mds_count >= 50
        and dq_count >= 30
        and exc_count >= 10
        and comp_count >= 48
        and barrier_count >= 1
    )

    return {
        "seeded": is_complete,
        "valuation_date": VALUATION_DATE.isoformat(),
        "counts": {
            "positions": pos_count,
            "market_data_snapshots": mds_count,
            "dealer_quotes": dq_count,
            "exceptions": exc_count,
            "valuation_comparisons": comp_count,
            "committee_agenda_items": agenda_count,
            "fx_barrier_details": barrier_count,
            "mongo_market_data": mongo_md_count,
            "mongo_vol_surface": mongo_vol_count,
        },
        "expected": {
            "positions": "48 (7 FX + 14 Rates + 12 FX Products + 15 Credit/Commodity)",
            "market_data_snapshots": "~100+ (FX + yield curves + CDS + commodity + muni)",
            "dealer_quotes": "~33 (FX barrier + FX exotics + L3 credit)",
            "exceptions": "~20 (AMBER + RED positions across all asset classes)",
            "valuation_comparisons": 48,
            "fx_barrier_details": "5 (1 original + 4 new exotics)",
        },
    }


# ══════════════════════════════════════════════════════════════════
# MASTER SEED FUNCTION
# ══════════════════════════════════════════════════════════════════


async def seed_all(db: AsyncSession) -> dict[str, Any]:
    """Seed all data in the correct order. Returns a summary of what was seeded.

    Seeds FX positions (original 7), then Rates, FX Products, Credit/Commodity,
    XVA adjustments, market data, exceptions, comparisons, and committee agenda.
    """
    from app.seed_rates import seed_rates_positions, seed_rates_details
    from app.seed_fx_products import seed_fx_positions, seed_fx_details, seed_fx_dealer_quotes
    from app.seed_credit_commodity import (
        seed_credit_commodity_positions,
        seed_credit_details,
        seed_structured_product_details,
        seed_commodity_details,
        seed_credit_commodity_dealer_quotes,
    )
    from app.seed_xva_market_data import (
        seed_xva_adjustments,
        seed_new_market_data,
        seed_new_exceptions,
        seed_new_comparisons,
    )

    results: dict[str, Any] = {}

    # ── Phase 1: Original FX positions ──────────────────────────────
    positions = await seed_positions(db)
    results["fx_positions_created"] = len(positions)

    if not positions:
        pos_result = await db.execute(select(Position))
        positions = list(pos_result.scalars().all())
        results["fx_positions_created"] = 0
        results["fx_positions_existing"] = len(positions)

    barrier = await seed_barrier_detail(db, positions)
    results["barrier_detail_created"] = 1 if barrier else 0

    # ── Phase 2: Rates positions (IRS, Futures, Options, Munis) ─────
    rates_positions = await seed_rates_positions(db)
    results["rates_positions_created"] = len(rates_positions)
    if rates_positions:
        rates_details = await seed_rates_details(db, rates_positions)
        results["rates_swap_details_created"] = len(rates_details.get("swap_details", []))
        results["rates_bond_details_created"] = len(rates_details.get("bond_details", []))

    # ── Phase 3: FX Products (Forwards, Vanilla Options, Exotics) ───
    fx_positions = await seed_fx_positions(db)
    results["fx_product_positions_created"] = len(fx_positions)
    if fx_positions:
        fx_details = await seed_fx_details(db, fx_positions)
        results["fx_barrier_details_created"] = len(fx_details) if isinstance(fx_details, (list, dict)) else 0
        fx_quotes = await seed_fx_dealer_quotes(db, fx_positions)
        results["fx_dealer_quotes_created"] = len(fx_quotes)

    # ── Phase 4: Credit & Commodity positions ───────────────────────
    cc_positions = await seed_credit_commodity_positions(db)
    results["credit_commodity_positions_created"] = len(cc_positions)
    if cc_positions:
        credit_dets = await seed_credit_details(db, cc_positions)
        results["credit_details_created"] = len(credit_dets)
        struct_dets = await seed_structured_product_details(db, cc_positions)
        results["structured_product_details_created"] = len(struct_dets)
        comm_dets = await seed_commodity_details(db, cc_positions)
        results["commodity_details_created"] = len(comm_dets)
        cc_quotes = await seed_credit_commodity_dealer_quotes(db, cc_positions)
        results["credit_commodity_dealer_quotes_created"] = len(cc_quotes)

    # Commit all positions before market data and downstream
    await db.commit()

    # ── Phase 5: Original market data ───────────────────────────────
    md_snapshots = await seed_market_data(db)
    results["market_data_snapshots_created"] = len(md_snapshots)

    fwd_snapshots = await seed_forward_curve(db)
    results["forward_curve_points_created"] = len(fwd_snapshots)

    vol_snapshots = await seed_vol_surface_pg(db)
    results["vol_surface_pg_created"] = len(vol_snapshots)

    await db.commit()

    # MongoDB
    try:
        vol_mongo_count = await seed_vol_surface_mongo()
        results["vol_surface_mongo_created"] = vol_mongo_count
    except Exception as e:
        logger.warning("MongoDB vol surface seeding failed: %s", e)
        results["vol_surface_mongo_error"] = str(e)

    try:
        md_mongo_count = await seed_market_data_mongo()
        results["market_data_mongo_created"] = md_mongo_count
    except Exception as e:
        logger.warning("MongoDB market data seeding failed: %s", e)
        results["market_data_mongo_error"] = str(e)

    # ── Phase 6: New market data (yield curves, CDS spreads, etc.) ──
    try:
        new_md = await seed_new_market_data(db)
        results["new_market_data_created"] = len(new_md)
    except Exception as e:
        logger.warning("New market data seeding failed: %s", e)
        results["new_market_data_error"] = str(e)

    # ── Phase 7: XVA adjustments (CVA, FVA, DVA) ───────────────────
    try:
        xva_results = await seed_xva_adjustments(db)
        results["xva_adjustments"] = xva_results
    except Exception as e:
        logger.warning("XVA adjustment seeding failed: %s", e)
        results["xva_adjustments_error"] = str(e)

    # ── Phase 8: Original dealer quotes + comparisons ───────────────
    quotes = await seed_dealer_quotes(db, positions)
    results["original_dealer_quotes_created"] = len(quotes)

    # Reload all positions for comparisons and exceptions
    all_pos_result = await db.execute(select(Position))
    all_positions = list(all_pos_result.scalars().all())

    comparisons = await seed_valuation_comparisons(db, positions)
    results["original_comparisons_created"] = len(comparisons)

    # ── Phase 9: New comparisons for all new positions ──────────────
    try:
        new_comparisons = await seed_new_comparisons(db)
        results["new_comparisons_created"] = len(new_comparisons)
    except Exception as e:
        logger.warning("New comparisons seeding failed: %s", e)
        results["new_comparisons_error"] = str(e)

    # ── Phase 10: Exceptions for ALL AMBER/RED positions ────────────
    exceptions = await seed_exceptions(db, all_positions)
    results["exceptions_created"] = len(exceptions)

    try:
        new_exc, new_comments = await seed_new_exceptions(db)
        results["new_exceptions_created"] = len(new_exc)
        results["new_exception_comments_created"] = len(new_comments)
    except Exception as e:
        logger.warning("New exceptions seeding failed: %s", e)
        results["new_exceptions_error"] = str(e)

    # ── Phase 11: Original exception comments + committee agenda ────
    comments = await seed_exception_comments(db, exceptions)
    results["exception_comments_created"] = len(comments)

    agenda_items = await seed_committee_agenda(db)
    results["committee_agenda_items_created"] = len(agenda_items)

    # Final commit
    await db.commit()

    # ── Summary ─────────────────────────────────────────────────────
    fv_summary = await compute_fv_hierarchy_summary(db)
    results["fv_hierarchy_summary"] = fv_summary

    status = await get_seed_status(db)
    results["status"] = status

    logger.info("Seed complete: %s", results)
    return results


# ══════════════════════════════════════════════════════════════════
# STANDALONE EXECUTION
# ══════════════════════════════════════════════════════════════════


async def _main() -> None:
    """Run the seeder as a standalone script."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Starting Valuation Control data seeder...")

    async with async_session_factory() as db:
        results = await seed_all(db)

    print("\n" + "=" * 70)
    print("SEED RESULTS")
    print("=" * 70)

    for key, value in results.items():
        if key in ("fv_hierarchy_summary", "status"):
            continue
        print(f"  {key}: {value}")

    print("\n--- FV Hierarchy Summary ---")
    fv = results.get("fv_hierarchy_summary", {})
    print(f"  Total positions: {fv.get('total_positions', 0)}")
    print(f"  Total notional USD: ${fv.get('total_notional_usd', 0):,.0f}")
    for level, data in fv.get("hierarchy", {}).items():
        print(f"  {level}: {data['count']} positions, ${data['total_notional_usd']:,.0f} ({data['pct_of_total']}%)")

    print("\n--- Seed Status ---")
    status = results.get("status", {})
    print(f"  Complete: {status.get('seeded', False)}")
    for key, value in status.get("counts", {}).items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 70)
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(_main())

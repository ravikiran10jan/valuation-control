"""Seed data for additional FX products: Forwards, Vanilla Options, and Exotics.

Adds 12 new FX positions beyond the 7 already in seed_data.py.
Includes FXBarrierDetail for exotic options and DealerQuote for L3 positions.

Can be imported and called from the main seeder or run standalone.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import Position, FXBarrierDetail, DealerQuote
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)

# ── Valuation date used across all seed data ─────────────────────
VALUATION_DATE = date(2025, 2, 14)


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


# ══════════════════════════════════════════════════════════════════
# FX FORWARD POSITIONS (4)
# ══════════════════════════════════════════════════════════════════

FX_FORWARD_POSITIONS: list[dict[str, Any]] = [
    # 1. USD/JPY 6M Forward $75M — GREEN, L2, Bloomberg FXFA
    {
        "trade_id": "T-20250214-201",
        "product_type": "Forward",
        "asset_class": "FX",
        "currency_pair": "USD/JPY",
        "notional": 75_000_000,
        "notional_usd": 75_000_000,
        "currency": "USD",
        "trade_date": "2025-02-10",
        "maturity_date": "2025-08-14",
        "settlement_date": "2025-08-18",
        "counterparty": "JPMorgan",
        "desk": "G10 FX Forwards",
        "desk_mark": 148.32,
        "vc_fair_value": 148.35,
        "book_value_usd": 75_000_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg FXFA",
        "fva_usd": -18_750,
        "notes": "6M USD/JPY forward. Forward points reflect rate differential. Tight bid-offer.",
    },
    # 2. GBP/USD 1Y Forward £60M — GREEN, L2, Bloomberg FXFA
    {
        "trade_id": "T-20250214-202",
        "product_type": "Forward",
        "asset_class": "FX",
        "currency_pair": "GBP/USD",
        "notional": 60_000_000,
        "notional_usd": 75_870_000,
        "currency": "GBP",
        "trade_date": "2025-02-05",
        "maturity_date": "2026-02-05",
        "settlement_date": "2026-02-09",
        "counterparty": "Barclays",
        "desk": "G10 FX Forwards",
        "desk_mark": 1.2702,
        "vc_fair_value": 1.2698,
        "book_value_usd": 76_212_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg FXFA",
        "fva_usd": -32_400,
        "notes": "1Y GBP/USD forward. Cable forward points from Bloomberg. G10 liquid.",
    },
    # 3. USD/CNH 3M Forward $100M — AMBER, L2, offshore NDF, wider spread
    {
        "trade_id": "T-20250214-203",
        "product_type": "Forward",
        "asset_class": "FX",
        "currency_pair": "USD/CNH",
        "notional": 100_000_000,
        "notional_usd": 100_000_000,
        "currency": "USD",
        "trade_date": "2025-01-28",
        "maturity_date": "2025-05-14",
        "settlement_date": "2025-05-16",
        "counterparty": "Deutsche Bank",
        "desk": "EM NDF Desk",
        "desk_mark": 7.2985,
        "vc_fair_value": 7.2870,
        "book_value_usd": 100_000_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg FXFA",
        "fva_usd": -45_000,
        "notes": "3M offshore CNH NDF. Wider bid-offer spread vs onshore CNY. AMBER due to NDF basis.",
    },
    # 4. EUR/GBP 9M Forward EUR40M — GREEN, L2, Bloomberg FXFA
    {
        "trade_id": "T-20250214-204",
        "product_type": "Forward",
        "asset_class": "FX",
        "currency_pair": "EUR/GBP",
        "notional": 40_000_000,
        "notional_usd": 43_292_000,
        "currency": "EUR",
        "trade_date": "2025-01-15",
        "maturity_date": "2025-11-14",
        "settlement_date": "2025-11-18",
        "counterparty": "BNP Paribas",
        "desk": "G10 FX Forwards",
        "desk_mark": 0.8358,
        "vc_fair_value": 0.8355,
        "book_value_usd": 43_340_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg FXFA",
        "fva_usd": -12_200,
        "notes": "9M EUR/GBP forward. Cross-rate derived from EUR/USD and GBP/USD curves.",
    },
]


# ══════════════════════════════════════════════════════════════════
# FX PLAIN VANILLA OPTION POSITIONS (4)
# ══════════════════════════════════════════════════════════════════

FX_VANILLA_OPTION_POSITIONS: list[dict[str, Any]] = [
    # 5. EUR/USD 3M Call €50M, strike 1.10 — GREEN, L2, Garman-Kohlhagen
    {
        "trade_id": "T-20250214-205",
        "product_type": "Option",
        "asset_class": "FX",
        "currency_pair": "EUR/USD",
        "notional": 50_000_000,
        "notional_usd": 54_115_000,
        "currency": "EUR",
        "trade_date": "2025-02-03",
        "maturity_date": "2025-05-14",
        "settlement_date": "2025-05-16",
        "counterparty": "Goldman Sachs",
        "desk": "FX Options",
        "desk_mark": 312_500,
        "vc_fair_value": 310_200,
        "book_value_usd": 625_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg OVML",
        "fva_usd": -7_800,
        "notes": "3M EUR/USD call, strike 1.10. OTM ~1.6%. Garman-Kohlhagen pricing. Vol ~6.8%.",
    },
    # 6. USD/JPY 6M Put $80M, strike 145 — GREEN, L2, Garman-Kohlhagen
    {
        "trade_id": "T-20250214-206",
        "product_type": "Option",
        "asset_class": "FX",
        "currency_pair": "USD/JPY",
        "notional": 80_000_000,
        "notional_usd": 80_000_000,
        "currency": "USD",
        "trade_date": "2025-01-20",
        "maturity_date": "2025-08-14",
        "settlement_date": "2025-08-18",
        "counterparty": "Morgan Stanley",
        "desk": "FX Options",
        "desk_mark": 1_840_000,
        "vc_fair_value": 1_825_600,
        "book_value_usd": 3_680_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg OVML",
        "fva_usd": -22_400,
        "notes": "6M USD/JPY put, strike 145. Slightly OTM. Garman-Kohlhagen pricing. Vol ~9.2%.",
    },
    # 7. GBP/USD 1Y Call £45M, strike 1.30 — AMBER, L2, vol surface diff
    {
        "trade_id": "T-20250214-207",
        "product_type": "Option",
        "asset_class": "FX",
        "currency_pair": "GBP/USD",
        "notional": 45_000_000,
        "notional_usd": 56_902_500,
        "currency": "GBP",
        "trade_date": "2025-01-10",
        "maturity_date": "2026-02-10",
        "settlement_date": "2026-02-12",
        "counterparty": "Barclays",
        "desk": "FX Options",
        "desk_mark": 1_575_000,
        "vc_fair_value": 1_485_000,
        "book_value_usd": 3_150_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg OVML",
        "fva_usd": -38_500,
        "notes": "1Y GBP/USD call, strike 1.30. OTM ~2.8%. Vol surface divergence causing AMBER. Vol ~8.5%.",
    },
    # 8. AUD/USD 3M Put A$60M, strike 0.64 — GREEN, L2, Garman-Kohlhagen
    {
        "trade_id": "T-20250214-208",
        "product_type": "Option",
        "asset_class": "FX",
        "currency_pair": "AUD/USD",
        "notional": 60_000_000,
        "notional_usd": 38_520_000,
        "currency": "AUD",
        "trade_date": "2025-02-07",
        "maturity_date": "2025-05-14",
        "settlement_date": "2025-05-16",
        "counterparty": "Deutsche Bank",
        "desk": "FX Options",
        "desk_mark": 462_000,
        "vc_fair_value": 458_400,
        "book_value_usd": 924_000,
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg OVML",
        "fva_usd": -5_600,
        "notes": "3M AUD/USD put, strike 0.64. Near ATM (~0.642 spot). Garman-Kohlhagen. Vol ~10.4%.",
    },
]


# ══════════════════════════════════════════════════════════════════
# FX EXOTIC OPTION POSITIONS (4)
# ══════════════════════════════════════════════════════════════════

FX_EXOTIC_OPTION_POSITIONS: list[dict[str, Any]] = [
    # 9. EUR/USD Knock-In call barrier 1.15, €30M — RED, L3, Monte Carlo
    {
        "trade_id": "T-20250214-209",
        "product_type": "Barrier",
        "asset_class": "FX",
        "currency_pair": "EUR/USD",
        "notional": 30_000_000,
        "notional_usd": 32_469_000,
        "currency": "EUR",
        "trade_date": "2024-12-18",
        "maturity_date": "2025-12-18",
        "settlement_date": "2025-12-22",
        "counterparty": "JPMorgan",
        "desk": "FX Exotics",
        "desk_mark": 285_000,
        "vc_fair_value": 243_600,
        "book_value_usd": 570_000,
        "fair_value_level": "L3",
        "pricing_source": "Internal MC Model",
        "fva_usd": -15_200,
        "notes": "EUR/USD up-and-in call, barrier 1.15, strike 1.10. KI barrier ~6.2% above spot. MC 50k paths.",
    },
    # 10. USD/JPY TARF 12 fixings $50M — RED, L3, MC + local vol
    {
        "trade_id": "T-20250214-210",
        "product_type": "Barrier",
        "asset_class": "FX",
        "currency_pair": "USD/JPY",
        "notional": 50_000_000,
        "notional_usd": 50_000_000,
        "currency": "USD",
        "trade_date": "2024-11-15",
        "maturity_date": "2025-11-15",
        "settlement_date": "2025-11-19",
        "counterparty": "Goldman Sachs",
        "desk": "FX Exotics",
        "desk_mark": 2_350_000,
        "vc_fair_value": 1_975_000,
        "book_value_usd": 4_700_000,
        "fair_value_level": "L3",
        "pricing_source": "Internal MC Model",
        "fva_usd": -52_500,
        "notes": "USD/JPY TARF, 12 monthly fixings, target profit 3.00 JPY, KO at target. MC + local vol model.",
    },
    # 11. GBP/USD Double-No-Touch 1.20/1.30 £25M — AMBER, L3, dealer quotes
    {
        "trade_id": "T-20250214-211",
        "product_type": "Barrier",
        "asset_class": "FX",
        "currency_pair": "GBP/USD",
        "notional": 25_000_000,
        "notional_usd": 31_612_500,
        "currency": "GBP",
        "trade_date": "2025-01-06",
        "maturity_date": "2025-07-06",
        "settlement_date": "2025-07-08",
        "counterparty": "Morgan Stanley",
        "desk": "FX Exotics",
        "desk_mark": 387_500,
        "vc_fair_value": 362_000,
        "book_value_usd": 775_000,
        "fair_value_level": "L3",
        "pricing_source": "Vanna-Volga Model",
        "fva_usd": -9_800,
        "notes": "GBP/USD DNT, barriers 1.20/1.30. Spot 1.2645. 5.1% to lower, 2.8% to upper. Dealer quote consensus.",
    },
    # 12. EUR/USD Worst-of basket put €20M — RED, L3, copula MC
    {
        "trade_id": "T-20250214-212",
        "product_type": "Barrier",
        "asset_class": "FX",
        "currency_pair": "EUR/USD",
        "notional": 20_000_000,
        "notional_usd": 21_646_000,
        "currency": "EUR",
        "trade_date": "2024-12-02",
        "maturity_date": "2025-12-02",
        "settlement_date": "2025-12-04",
        "counterparty": "BNP Paribas",
        "desk": "FX Exotics",
        "desk_mark": 680_000,
        "vc_fair_value": 572_400,
        "book_value_usd": 1_360_000,
        "fair_value_level": "L3",
        "pricing_source": "Internal MC Model",
        "fva_usd": -18_900,
        "notes": "Worst-of basket put on EUR/USD, GBP/USD, AUD/USD. Correlation-sensitive. Copula MC 100k paths.",
    },
]


# ══════════════════════════════════════════════════════════════════
# COMBINED POSITIONS LIST
# ══════════════════════════════════════════════════════════════════

FX_POSITIONS: list[dict[str, Any]] = (
    FX_FORWARD_POSITIONS + FX_VANILLA_OPTION_POSITIONS + FX_EXOTIC_OPTION_POSITIONS
)


# ══════════════════════════════════════════════════════════════════
# FX BARRIER DETAIL DATA (for exotic options)
# ══════════════════════════════════════════════════════════════════

FX_BARRIER_DETAILS: dict[str, dict[str, Any]] = {
    # 9. EUR/USD Knock-In call
    "T-20250214-209": {
        "currency_pair": "EUR/USD",
        "spot_ref": 1.0823,
        "lower_barrier": None,
        "upper_barrier": 1.15,
        "barrier_type": "KI",
        "volatility": 0.0685,
        "time_to_expiry": 0.8384,
        "domestic_rate": 0.0525,
        "foreign_rate": 0.0425,
        "survival_probability": 0.7250,
        "premium_market": 285_000,
        "premium_model": 243_600,
    },
    # 10. USD/JPY TARF
    "T-20250214-210": {
        "currency_pair": "USD/JPY",
        "spot_ref": 149.88,
        "lower_barrier": 142.00,
        "upper_barrier": 155.00,
        "barrier_type": "KO",
        "volatility": 0.0925,
        "time_to_expiry": 0.7534,
        "domestic_rate": 0.0525,
        "foreign_rate": 0.0050,
        "survival_probability": 0.4820,
        "premium_market": 2_350_000,
        "premium_model": 1_975_000,
    },
    # 11. GBP/USD Double-No-Touch
    "T-20250214-211": {
        "currency_pair": "GBP/USD",
        "spot_ref": 1.2645,
        "lower_barrier": 1.20,
        "upper_barrier": 1.30,
        "barrier_type": "DNT",
        "volatility": 0.0850,
        "time_to_expiry": 0.3945,
        "domestic_rate": 0.0525,
        "foreign_rate": 0.0475,
        "survival_probability": 0.6180,
        "premium_market": 387_500,
        "premium_model": 362_000,
    },
    # 12. EUR/USD Worst-of basket put
    "T-20250214-212": {
        "currency_pair": "EUR/USD",
        "spot_ref": 1.0823,
        "lower_barrier": 1.02,
        "upper_barrier": None,
        "barrier_type": "KI",
        "volatility": 0.0780,
        "time_to_expiry": 0.7973,
        "domestic_rate": 0.0525,
        "foreign_rate": 0.0425,
        "survival_probability": 0.5540,
        "premium_market": 680_000,
        "premium_model": 572_400,
    },
}


# ══════════════════════════════════════════════════════════════════
# DEALER QUOTE DATA (for L3 exotic options)
# ══════════════════════════════════════════════════════════════════

FX_DEALER_QUOTES: dict[str, list[dict[str, Any]]] = {
    # 9. EUR/USD Knock-In call — RED
    "T-20250214-209": [
        {"dealer": "JPMorgan", "quote_value": 241_000, "quote_type": "Mid"},
        {"dealer": "Goldman Sachs", "quote_value": 248_500, "quote_type": "Mid"},
        {"dealer": "Deutsche Bank", "quote_value": 241_300, "quote_type": "Mid"},
    ],
    # 10. USD/JPY TARF — RED
    "T-20250214-210": [
        {"dealer": "Goldman Sachs", "quote_value": 1_960_000, "quote_type": "Mid"},
        {"dealer": "Morgan Stanley", "quote_value": 1_995_000, "quote_type": "Mid"},
        {"dealer": "BNP Paribas", "quote_value": 1_970_000, "quote_type": "Mid"},
    ],
    # 11. GBP/USD DNT — AMBER
    "T-20250214-211": [
        {"dealer": "Morgan Stanley", "quote_value": 358_000, "quote_type": "Mid"},
        {"dealer": "Barclays", "quote_value": 365_000, "quote_type": "Mid"},
        {"dealer": "JPMorgan", "quote_value": 363_000, "quote_type": "Mid"},
    ],
    # 12. EUR/USD Worst-of basket put — RED
    "T-20250214-212": [
        {"dealer": "BNP Paribas", "quote_value": 568_000, "quote_type": "Mid"},
        {"dealer": "Deutsche Bank", "quote_value": 575_800, "quote_type": "Mid"},
        {"dealer": "Goldman Sachs", "quote_value": 573_400, "quote_type": "Mid"},
    ],
}


# ══════════════════════════════════════════════════════════════════
# EXCEPTION STATUS CLASSIFICATION
# ══════════════════════════════════════════════════════════════════

# Pre-assigned exception statuses per the requirements
_EXCEPTION_STATUS_MAP: dict[str, str] = {
    "T-20250214-201": "GREEN",
    "T-20250214-202": "GREEN",
    "T-20250214-203": "AMBER",
    "T-20250214-204": "GREEN",
    "T-20250214-205": "GREEN",
    "T-20250214-206": "GREEN",
    "T-20250214-207": "AMBER",
    "T-20250214-208": "GREEN",
    "T-20250214-209": "RED",
    "T-20250214-210": "RED",
    "T-20250214-211": "AMBER",
    "T-20250214-212": "RED",
}


# ══════════════════════════════════════════════════════════════════
# SEEDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════


async def seed_fx_positions(db: AsyncSession) -> list[Position]:
    """Seed all 12 FX product positions (4 forwards, 4 vanilla options, 4 exotics).

    Returns the created ORM objects with PKs assigned.
    Handles idempotency: skips positions whose trade_id already exists.
    """
    created: list[Position] = []

    for pos_data in FX_POSITIONS:
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
        exception_status = _EXCEPTION_STATUS_MAP.get(pos_data["trade_id"], "GREEN")

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
            counterparty=pos_data["counterparty"],
            desk_mark=Decimal(str(desk_mark)),
            vc_fair_value=Decimal(str(vc_fair_value)),
            book_value_usd=Decimal(str(pos_data["book_value_usd"])),
            difference=diff,
            difference_pct=diff_pct,
            exception_status=exception_status,
            fair_value_level=pos_data["fair_value_level"],
            pricing_source=pos_data["pricing_source"],
            fva_usd=Decimal(str(pos_data["fva_usd"])),
            valuation_date=VALUATION_DATE,
        )
        db.add(pos)
        created.append(pos)

    if created:
        await db.flush()  # assign PKs
        logger.info("Seeded %d FX product positions", len(created))

    return created


async def seed_fx_details(db: AsyncSession, positions: list[Position]) -> dict:
    """Seed FXBarrierDetail records for the 4 exotic option positions.

    Returns a dict mapping trade_id to the created FXBarrierDetail object.
    """
    created: dict[str, FXBarrierDetail] = {}

    for pos in positions:
        if pos.trade_id not in FX_BARRIER_DETAILS:
            continue

        detail_data = FX_BARRIER_DETAILS[pos.trade_id]

        # Idempotency check
        existing = await db.get(FXBarrierDetail, pos.position_id)
        if existing is not None:
            logger.info(
                "FXBarrierDetail already exists for position %d (%s), skipping",
                pos.position_id,
                pos.trade_id,
            )
            created[pos.trade_id] = existing
            continue

        detail = FXBarrierDetail(
            position_id=pos.position_id,
            currency_pair=detail_data["currency_pair"],
            spot_ref=Decimal(str(detail_data["spot_ref"])),
            lower_barrier=(
                Decimal(str(detail_data["lower_barrier"]))
                if detail_data["lower_barrier"] is not None
                else None
            ),
            upper_barrier=(
                Decimal(str(detail_data["upper_barrier"]))
                if detail_data["upper_barrier"] is not None
                else None
            ),
            barrier_type=detail_data["barrier_type"],
            volatility=Decimal(str(detail_data["volatility"])),
            time_to_expiry=Decimal(str(detail_data["time_to_expiry"])),
            domestic_rate=Decimal(str(detail_data["domestic_rate"])),
            foreign_rate=Decimal(str(detail_data["foreign_rate"])),
            survival_probability=Decimal(str(detail_data["survival_probability"])),
            premium_market=Decimal(str(detail_data["premium_market"])),
            premium_model=Decimal(str(detail_data["premium_model"])),
        )
        db.add(detail)
        created[pos.trade_id] = detail

    if created:
        await db.flush()
        logger.info("Seeded %d FX barrier detail records", len(created))

    return created


async def seed_fx_dealer_quotes(db: AsyncSession, positions: list[Position]) -> list[DealerQuote]:
    """Seed dealer quotes for L3 exotic option positions.

    Provides 3 dealer mid quotes per exotic position for fair value consensus.
    """
    created: list[DealerQuote] = []

    for pos in positions:
        if pos.trade_id not in FX_DEALER_QUOTES:
            continue

        quotes_data = FX_DEALER_QUOTES[pos.trade_id]

        for quote_data in quotes_data:
            # Idempotency check
            existing = await db.execute(
                select(DealerQuote).where(
                    DealerQuote.position_id == pos.position_id,
                    DealerQuote.dealer_name == quote_data["dealer"],
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            quote = DealerQuote(
                position_id=pos.position_id,
                dealer_name=quote_data["dealer"],
                quote_value=Decimal(str(quote_data["quote_value"])),
                quote_date=VALUATION_DATE,
                quote_type=quote_data["quote_type"],
            )
            db.add(quote)
            created.append(quote)

    if created:
        await db.flush()
        logger.info("Seeded %d FX dealer quotes", len(created))

    return created


# ══════════════════════════════════════════════════════════════════
# MASTER SEED FUNCTION
# ══════════════════════════════════════════════════════════════════


async def seed_all_fx_products(db: AsyncSession) -> dict[str, Any]:
    """Seed all FX product data in the correct order. Returns a summary.

    Order:
    1. FX positions (12: 4 forwards, 4 vanilla options, 4 exotics)
    2. FX barrier details (for 4 exotic positions)
    3. FX dealer quotes (for 4 L3 exotic positions)
    """
    results: dict[str, Any] = {}

    # 1. Positions
    positions = await seed_fx_positions(db)
    results["fx_positions_created"] = len(positions)

    # If no new positions were created, load existing ones for downstream seeding
    if not positions:
        trade_ids = [p["trade_id"] for p in FX_POSITIONS]
        pos_result = await db.execute(
            select(Position).where(Position.trade_id.in_(trade_ids))
        )
        positions = list(pos_result.scalars().all())
        results["fx_positions_created"] = 0
        results["fx_positions_existing"] = len(positions)

    # 2. Barrier details
    barrier_details = await seed_fx_details(db, positions)
    results["fx_barrier_details_created"] = len(barrier_details)

    # 3. Dealer quotes
    dealer_quotes = await seed_fx_dealer_quotes(db, positions)
    results["fx_dealer_quotes_created"] = len(dealer_quotes)

    # Commit
    await db.commit()

    logger.info("FX products seed complete: %s", results)
    return results


# ══════════════════════════════════════════════════════════════════
# STANDALONE EXECUTION
# ══════════════════════════════════════════════════════════════════


async def _main() -> None:
    """Run the FX products seeder as a standalone script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting FX Products data seeder...")

    async with async_session_factory() as db:
        results = await seed_all_fx_products(db)

    print("\n" + "=" * 70)
    print("FX PRODUCTS SEED RESULTS")
    print("=" * 70)

    for key, value in results.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 70)
    print("FX products seeding complete.")


if __name__ == "__main__":
    asyncio.run(_main())

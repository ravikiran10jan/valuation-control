"""Seed data for Interest Rate positions in the Valuation Control system.

Seeds 14 Rates positions across four sub-products:
  - Interest Rate Swaps (IRS)          4 positions
  - IR Futures (Bond + SOFR)           4 positions
  - IR Options (swaptions, caps)       3 positions
  - Municipal Bonds                    3 positions

Along with RatesSwapDetail for IRS and BondDetail for futures/munis.

Can be run as a standalone script or invoked via the /seed/* API routes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import Position, RatesSwapDetail, BondDetail, DealerQuote
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
# EMBEDDED REFERENCE DATA — INTEREST RATE POSITIONS
# ══════════════════════════════════════════════════════════════════

POSITIONS: list[dict[str, Any]] = [
    # ── IRS (Interest Rate Swaps) ────────────────────────────────
    {
        "trade_id": "T-20250214-101",
        "product_type": "IRS",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 500_000_000,
        "notional_usd": 500_000_000,
        "currency": "USD",
        "desk_mark": 4.3275,
        "vc_fair_value": 4.3250,
        "book_value_usd": 2_450_000,
        "trade_date": "2025-02-10",
        "maturity_date": "2030-02-10",
        "settlement_date": "2025-02-12",
        "counterparty": "Goldman Sachs",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg SWAP",
        "fva_usd": -185_000,
        "exception_status": "GREEN",
        "desk": "Rates Trading US",
        "direction": "Pay Fixed",
        "notes": "USD 500M 5Y IRS pay-fixed 4.3275% vs SOFR. Tight to mid-market.",
    },
    {
        "trade_id": "T-20250214-102",
        "product_type": "IRS",
        "asset_class": "Rates",
        "currency_pair": "EUR/EUR",
        "notional": 300_000_000,
        "notional_usd": 324_690_000,
        "currency": "EUR",
        "desk_mark": 2.8150,
        "vc_fair_value": 2.8125,
        "book_value_usd": 3_120_000,
        "trade_date": "2025-01-15",
        "maturity_date": "2035-01-15",
        "settlement_date": "2025-01-17",
        "counterparty": "BNP Paribas",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg SWAP",
        "fva_usd": -275_000,
        "exception_status": "GREEN",
        "desk": "Rates Trading EU",
        "direction": "Pay Fixed",
        "notes": "EUR 300M 10Y IRS pay-fixed 2.815% vs 6M EURIBOR. Mid-market consensus.",
    },
    {
        "trade_id": "T-20250214-103",
        "product_type": "IRS",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 200_000_000,
        "notional_usd": 200_000_000,
        "currency": "USD",
        "desk_mark": 4.1850,
        "vc_fair_value": 4.2125,
        "book_value_usd": -875_000,
        "trade_date": "2025-02-03",
        "maturity_date": "2027-02-03",
        "settlement_date": "2025-02-05",
        "counterparty": "Citi",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg SWAP",
        "fva_usd": -62_000,
        "exception_status": "AMBER",
        "desk": "Rates Trading US",
        "direction": "Pay Float",
        "notes": "USD 200M 2Y IRS pay-float SOFR vs fixed 4.185%. Slight curve divergence desk vs VC.",
    },
    {
        "trade_id": "T-20250214-104",
        "product_type": "IRS",
        "asset_class": "Rates",
        "currency_pair": "GBP/GBP",
        "notional": 150_000_000,
        "notional_usd": 190_350_000,
        "currency": "GBP",
        "desk_mark": 3.9500,
        "vc_fair_value": 4.0875,
        "book_value_usd": -1_650_000,
        "trade_date": "2024-08-20",
        "maturity_date": "2031-08-20",
        "settlement_date": "2024-08-22",
        "counterparty": "Barclays",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg SWAP",
        "fva_usd": -142_000,
        "exception_status": "RED",
        "desk": "Rates Trading EU",
        "direction": "Pay Fixed",
        "notes": "GBP 150M 7Y IRS pay-fixed vs SONIA. Stale SONIA curve on desk side. RED breach 13.75bps.",
    },
    # ── IR Futures — Bond Futures ────────────────────────────────
    {
        "trade_id": "T-20250214-105",
        "product_type": "Bond Future",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 10_000_000,
        "notional_usd": 10_000_000,
        "currency": "USD",
        "desk_mark": 118.218750,
        "vc_fair_value": 118.203125,
        "book_value_usd": 11_821_875,
        "trade_date": "2025-02-12",
        "maturity_date": "2025-03-20",
        "settlement_date": "2025-03-20",
        "counterparty": "CME Clearing",
        "fair_value_level": "L1",
        "pricing_source": "CME Settlement",
        "fva_usd": 0,
        "exception_status": "GREEN",
        "desk": "Rates Trading US",
        "direction": "LONG",
        "notes": "US Treasury Bond Future ZBH5, 100 contracts x $100k face. CME settle price.",
    },
    {
        "trade_id": "T-20250214-106",
        "product_type": "Bond Future",
        "asset_class": "Rates",
        "currency_pair": "EUR/EUR",
        "notional": 7_500_000,
        "notional_usd": 8_117_250,
        "currency": "EUR",
        "desk_mark": 131.450000,
        "vc_fair_value": 131.430000,
        "book_value_usd": 10_687_863,
        "trade_date": "2025-02-11",
        "maturity_date": "2025-03-07",
        "settlement_date": "2025-03-07",
        "counterparty": "Eurex Clearing",
        "fair_value_level": "L1",
        "pricing_source": "Eurex Settlement",
        "fva_usd": 0,
        "exception_status": "GREEN",
        "desk": "Rates Trading EU",
        "direction": "LONG",
        "notes": "Euro-Bund Future FGBL Mar-25, 75 contracts x EUR 100k face. Eurex daily settle.",
    },
    # ── IR Futures — SOFR Futures ────────────────────────────────
    {
        "trade_id": "T-20250214-107",
        "product_type": "SOFR Future",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 200_000_000,
        "notional_usd": 200_000_000,
        "currency": "USD",
        "desk_mark": 95.7025,
        "vc_fair_value": 95.6975,
        "book_value_usd": 191_395_000,
        "trade_date": "2025-02-10",
        "maturity_date": "2025-06-18",
        "settlement_date": "2025-06-18",
        "counterparty": "CME Clearing",
        "fair_value_level": "L1",
        "pricing_source": "CME Settlement",
        "fva_usd": 0,
        "exception_status": "GREEN",
        "desk": "Rates Trading US",
        "direction": "LONG",
        "notes": "3M SOFR Future SRH5 Mar-25, 200 contracts. Implied rate 4.2975%. CME settle.",
    },
    {
        "trade_id": "T-20250214-108",
        "product_type": "SOFR Future",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 150_000_000,
        "notional_usd": 150_000_000,
        "currency": "USD",
        "desk_mark": 95.8750,
        "vc_fair_value": 95.8475,
        "book_value_usd": 143_771_250,
        "trade_date": "2025-02-07",
        "maturity_date": "2025-09-17",
        "settlement_date": "2025-09-17",
        "counterparty": "CME Clearing",
        "fair_value_level": "L1",
        "pricing_source": "CME Settlement",
        "fva_usd": 0,
        "exception_status": "AMBER",
        "desk": "Rates Trading US",
        "direction": "LONG",
        "notes": "3M SOFR Future SRM5 Jun-25, 150 contracts. Slight basis diff vs strip. AMBER breach.",
    },
    # ── IR Options ───────────────────────────────────────────────
    {
        "trade_id": "T-20250214-109",
        "product_type": "Swaption",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 250_000_000,
        "notional_usd": 250_000_000,
        "currency": "USD",
        "desk_mark": 3_875_000,
        "vc_fair_value": 3_850_000,
        "book_value_usd": 3_875_000,
        "trade_date": "2025-01-20",
        "maturity_date": "2026-01-20",
        "settlement_date": "2026-01-22",
        "counterparty": "Morgan Stanley",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg VCUB",
        "fva_usd": -45_000,
        "exception_status": "GREEN",
        "desk": "Rates Options US",
        "direction": "LONG",
        "notes": "USD 1Y into 5Y payer swaption, $250M notional. Hull-White model. 25k diff within tolerance.",
    },
    {
        "trade_id": "T-20250214-110",
        "product_type": "IR Cap",
        "asset_class": "Rates",
        "currency_pair": "EUR/EUR",
        "notional": 100_000_000,
        "notional_usd": 108_230_000,
        "currency": "EUR",
        "desk_mark": 1_425_000,
        "vc_fair_value": 1_380_000,
        "book_value_usd": 1_542_674,
        "trade_date": "2024-11-15",
        "maturity_date": "2027-11-15",
        "settlement_date": "2024-11-19",
        "counterparty": "Deutsche Bank",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg VCUB",
        "fva_usd": -28_000,
        "exception_status": "AMBER",
        "desk": "Rates Options EU",
        "direction": "LONG",
        "notes": "EUR 3Y cap strike 3.5% on 3M EURIBOR. Black-76 pricing. 45k diff — AMBER vol input divergence.",
    },
    {
        "trade_id": "T-20250214-111",
        "product_type": "Bermudan Swaption",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 175_000_000,
        "notional_usd": 175_000_000,
        "currency": "USD",
        "desk_mark": 5_250_000,
        "vc_fair_value": 4_725_000,
        "book_value_usd": 5_250_000,
        "trade_date": "2024-06-10",
        "maturity_date": "2026-06-10",
        "settlement_date": "2026-06-12",
        "counterparty": "JPMorgan",
        "fair_value_level": "L3",
        "pricing_source": "Internal LGM Model",
        "fva_usd": -92_000,
        "exception_status": "RED",
        "desk": "Rates Options US",
        "direction": "LONG",
        "notes": "USD 2Y into 10Y Bermudan payer swaption, $175M. LGM vs desk Hull-White. RED — model-dependent, $525k diff.",
    },
    # ── Municipal Bonds ──────────────────────────────────────────
    {
        "trade_id": "T-20250214-112",
        "product_type": "Municipal Bond",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 50_000_000,
        "notional_usd": 50_000_000,
        "currency": "USD",
        "desk_mark": 102.375000,
        "vc_fair_value": 102.250000,
        "book_value_usd": 51_187_500,
        "trade_date": "2024-09-15",
        "maturity_date": "2035-06-01",
        "settlement_date": "2024-09-18",
        "counterparty": "Wells Fargo",
        "fair_value_level": "L2",
        "pricing_source": "ICE Benchmark",
        "fva_usd": -15_000,
        "exception_status": "GREEN",
        "desk": "Muni Desk",
        "direction": "LONG",
        "notes": "NYC GO Bond 4.25% 2035, $50M face. Tax-exempt. ICE eval vs desk. Tight spread.",
    },
    {
        "trade_id": "T-20250214-113",
        "product_type": "Municipal Bond",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 30_000_000,
        "notional_usd": 30_000_000,
        "currency": "USD",
        "desk_mark": 104.750000,
        "vc_fair_value": 103.500000,
        "book_value_usd": 31_425_000,
        "trade_date": "2024-07-20",
        "maturity_date": "2040-01-01",
        "settlement_date": "2024-07-23",
        "counterparty": "Raymond James",
        "fair_value_level": "L2",
        "pricing_source": "ICE Benchmark",
        "fva_usd": -22_000,
        "exception_status": "AMBER",
        "desk": "Muni Desk",
        "direction": "LONG",
        "notes": "CA Revenue Bond 5.0% 2040, $30M face. Credit concern — CA wildfire exposure. AMBER 1.25pt diff.",
    },
    {
        "trade_id": "T-20250214-114",
        "product_type": "Municipal Bond",
        "asset_class": "Rates",
        "currency_pair": "USD/USD",
        "notional": 25_000_000,
        "notional_usd": 25_000_000,
        "currency": "USD",
        "desk_mark": 95.250000,
        "vc_fair_value": 91.750000,
        "book_value_usd": 23_812_500,
        "trade_date": "2024-03-10",
        "maturity_date": "2032-12-01",
        "settlement_date": "2024-03-13",
        "counterparty": "Stifel Financial",
        "fair_value_level": "L3",
        "pricing_source": "Dealer Consensus",
        "fva_usd": -35_000,
        "exception_status": "RED",
        "desk": "Muni Desk",
        "direction": "LONG",
        "notes": "IL GO Bond 4.75% 2032, $25M face. Downgrade risk — IL pension liability. RED 3.5pt diff. L3 — illiquid.",
    },
]

# ── RatesSwapDetail data for IRS positions ───────────────────────
RATES_SWAP_DETAILS: list[dict[str, Any]] = [
    {
        "trade_id": "T-20250214-101",
        "fixed_rate": 4.3275,
        "float_index": "SOFR",
        "pay_frequency": "6M",
        "receive_frequency": "3M",
        "day_count_convention": "ACT/360",
        "discount_curve": "USD SOFR OIS",
    },
    {
        "trade_id": "T-20250214-102",
        "fixed_rate": 2.8150,
        "float_index": "EURIBOR 6M",
        "pay_frequency": "1Y",
        "receive_frequency": "6M",
        "day_count_convention": "30/360",
        "discount_curve": "EUR ESTR OIS",
    },
    {
        "trade_id": "T-20250214-103",
        "fixed_rate": 4.1850,
        "float_index": "SOFR",
        "pay_frequency": "3M",
        "receive_frequency": "6M",
        "day_count_convention": "ACT/360",
        "discount_curve": "USD SOFR OIS",
    },
    {
        "trade_id": "T-20250214-104",
        "fixed_rate": 3.9500,
        "float_index": "SONIA",
        "pay_frequency": "6M",
        "receive_frequency": "3M",
        "day_count_convention": "ACT/365",
        "discount_curve": "GBP SONIA OIS",
    },
]

# ── BondDetail data for Bond Futures ─────────────────────────────
BOND_DETAILS_FUTURES: list[dict[str, Any]] = [
    {
        "trade_id": "T-20250214-105",
        "issuer": "US Treasury",
        "coupon_rate": 4.0000,
        "coupon_frequency": "Semi",
        "credit_rating": "AA+",
        "yield_to_maturity": 4.4250,
        "duration": 16.850,
        "convexity": 3.4520,
        "contract_size": 100_000.00,
        "futures_ticker": "ZBH5",
    },
    {
        "trade_id": "T-20250214-106",
        "issuer": "German Federal Government",
        "coupon_rate": 2.5000,
        "coupon_frequency": "Annual",
        "credit_rating": "AAA",
        "yield_to_maturity": 2.3750,
        "duration": 8.420,
        "convexity": 0.8350,
        "contract_size": 100_000.00,
        "futures_ticker": "FGBL",
    },
    {
        "trade_id": "T-20250214-107",
        "issuer": "CME Group",
        "coupon_rate": 0.0000,
        "coupon_frequency": "None",
        "credit_rating": "N/A",
        "yield_to_maturity": 4.2975,
        "duration": 0.250,
        "convexity": 0.0006,
        "contract_size": 1_000_000.00,
        "futures_ticker": "SRH5",
    },
    {
        "trade_id": "T-20250214-108",
        "issuer": "CME Group",
        "coupon_rate": 0.0000,
        "coupon_frequency": "None",
        "credit_rating": "N/A",
        "yield_to_maturity": 4.1250,
        "duration": 0.250,
        "convexity": 0.0006,
        "contract_size": 1_000_000.00,
        "futures_ticker": "SRM5",
    },
]

# ── BondDetail data for Municipal Bonds ──────────────────────────
BOND_DETAILS_MUNIS: list[dict[str, Any]] = [
    {
        "trade_id": "T-20250214-112",
        "issuer": "City of New York",
        "coupon_rate": 4.2500,
        "coupon_frequency": "Semi",
        "credit_rating": "AA",
        "yield_to_maturity": 4.0800,
        "duration": 7.620,
        "convexity": 0.7850,
        "contract_size": None,
        "futures_ticker": None,
    },
    {
        "trade_id": "T-20250214-113",
        "issuer": "State of California",
        "coupon_rate": 5.0000,
        "coupon_frequency": "Semi",
        "credit_rating": "A+",
        "yield_to_maturity": 4.5200,
        "duration": 10.340,
        "convexity": 1.3200,
        "contract_size": None,
        "futures_ticker": None,
    },
    {
        "trade_id": "T-20250214-114",
        "issuer": "State of Illinois",
        "coupon_rate": 4.7500,
        "coupon_frequency": "Semi",
        "credit_rating": "BBB-",
        "yield_to_maturity": 5.6500,
        "duration": 5.890,
        "convexity": 0.4950,
        "contract_size": None,
        "futures_ticker": None,
    },
]


# ══════════════════════════════════════════════════════════════════
# SEEDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════


async def seed_rates_positions(db: AsyncSession) -> list[Position]:
    """Seed all 14 Interest Rate positions. Returns the created ORM objects (with PK assigned).

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
            exception_status=pos_data["exception_status"],
            fair_value_level=pos_data["fair_value_level"],
            pricing_source=pos_data["pricing_source"],
            fva_usd=Decimal(str(pos_data["fva_usd"])),
            valuation_date=VALUATION_DATE,
        )
        db.add(pos)
        created.append(pos)

    if created:
        await db.flush()  # assign PKs
        logger.info("Seeded %d rates positions", len(created))

    return created


async def seed_rates_details(
    db: AsyncSession, positions: list[Position]
) -> dict[str, list]:
    """Seed RatesSwapDetail for IRS positions and BondDetail for futures/munis.

    Returns a dict with keys 'swap_details' and 'bond_details' containing the
    created ORM objects.
    """
    # Build a lookup from trade_id to position_id
    trade_id_to_position: dict[str, Position] = {}
    for p in positions:
        trade_id_to_position[p.trade_id] = p

    # If positions list is incomplete, try to look up missing ones from the DB
    all_trade_ids = set()
    for detail_list in [RATES_SWAP_DETAILS, BOND_DETAILS_FUTURES, BOND_DETAILS_MUNIS]:
        for d in detail_list:
            all_trade_ids.add(d["trade_id"])

    missing_ids = all_trade_ids - set(trade_id_to_position.keys())
    if missing_ids:
        for tid in missing_ids:
            result = await db.execute(
                select(Position).where(Position.trade_id == tid)
            )
            pos = result.scalar_one_or_none()
            if pos is not None:
                trade_id_to_position[pos.trade_id] = pos

    swap_details_created: list[RatesSwapDetail] = []
    bond_details_created: list[BondDetail] = []

    # ── Seed RatesSwapDetail for IRS positions ───────────────────
    for swap_data in RATES_SWAP_DETAILS:
        pos = trade_id_to_position.get(swap_data["trade_id"])
        if pos is None:
            logger.warning(
                "Position %s not found, skipping swap detail", swap_data["trade_id"]
            )
            continue

        # Idempotency check
        existing = await db.get(RatesSwapDetail, pos.position_id)
        if existing is not None:
            logger.info(
                "RatesSwapDetail already exists for position %d, skipping",
                pos.position_id,
            )
            continue

        detail = RatesSwapDetail(
            position_id=pos.position_id,
            fixed_rate=Decimal(str(swap_data["fixed_rate"])),
            float_index=swap_data["float_index"],
            pay_frequency=swap_data["pay_frequency"],
            receive_frequency=swap_data["receive_frequency"],
            day_count_convention=swap_data["day_count_convention"],
            discount_curve=swap_data["discount_curve"],
        )
        db.add(detail)
        swap_details_created.append(detail)

    # ── Seed BondDetail for Bond Futures and SOFR Futures ────────
    for bond_data in BOND_DETAILS_FUTURES:
        pos = trade_id_to_position.get(bond_data["trade_id"])
        if pos is None:
            logger.warning(
                "Position %s not found, skipping bond detail", bond_data["trade_id"]
            )
            continue

        existing = await db.get(BondDetail, pos.position_id)
        if existing is not None:
            logger.info(
                "BondDetail already exists for position %d, skipping",
                pos.position_id,
            )
            continue

        detail = BondDetail(
            position_id=pos.position_id,
            issuer=bond_data["issuer"],
            coupon_rate=Decimal(str(bond_data["coupon_rate"])),
            coupon_frequency=bond_data["coupon_frequency"],
            credit_rating=bond_data["credit_rating"],
            yield_to_maturity=Decimal(str(bond_data["yield_to_maturity"])),
            duration=Decimal(str(bond_data["duration"])),
            convexity=Decimal(str(bond_data["convexity"])),
            contract_size=Decimal(str(bond_data["contract_size"])),
            futures_ticker=bond_data["futures_ticker"],
        )
        db.add(detail)
        bond_details_created.append(detail)

    # ── Seed BondDetail for Municipal Bonds ──────────────────────
    for muni_data in BOND_DETAILS_MUNIS:
        pos = trade_id_to_position.get(muni_data["trade_id"])
        if pos is None:
            logger.warning(
                "Position %s not found, skipping muni bond detail", muni_data["trade_id"]
            )
            continue

        existing = await db.get(BondDetail, pos.position_id)
        if existing is not None:
            logger.info(
                "BondDetail already exists for position %d, skipping",
                pos.position_id,
            )
            continue

        detail = BondDetail(
            position_id=pos.position_id,
            issuer=muni_data["issuer"],
            coupon_rate=Decimal(str(muni_data["coupon_rate"])),
            coupon_frequency=muni_data["coupon_frequency"],
            credit_rating=muni_data["credit_rating"],
            yield_to_maturity=Decimal(str(muni_data["yield_to_maturity"])),
            duration=Decimal(str(muni_data["duration"])),
            convexity=Decimal(str(muni_data["convexity"])),
            contract_size=(
                Decimal(str(muni_data["contract_size"]))
                if muni_data["contract_size"] is not None
                else None
            ),
            futures_ticker=muni_data["futures_ticker"],
        )
        db.add(detail)
        bond_details_created.append(detail)

    if swap_details_created or bond_details_created:
        await db.flush()
        logger.info(
            "Seeded %d swap details and %d bond details",
            len(swap_details_created),
            len(bond_details_created),
        )

    return {
        "swap_details": swap_details_created,
        "bond_details": bond_details_created,
    }

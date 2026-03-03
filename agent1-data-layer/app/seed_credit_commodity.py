"""Seed data for Credit products (CDS, CLO, CDO, MBS) and Commodity Swaps.

Creates 15 synthetic positions with realistic financial data:
  - 4 CDS (Credit Default Swaps)
  - 3 CLO (Collateralized Loan Obligations)
  - 2 CDO (Collateralized Debt Obligations)
  - 3 MBS (Mortgage-Backed Securities)
  - 3 Commodity Swaps

All detail tables (CreditDetail, StructuredProductDetail, CommodityDetail)
and dealer quotes for Level 3 positions are populated.

Can be run as a standalone script or invoked via API routes.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.postgres import (
    Position,
    CreditDetail,
    CommodityDetail,
    StructuredProductDetail,
    DealerQuote,
)
from app.core.database import async_session_factory

logger = logging.getLogger(__name__)

# ── Valuation date used across all seed data ─────────────────────
VALUATION_DATE = date(2025, 2, 14)


# ══════════════════════════════════════════════════════════════════
# EMBEDDED POSITION DATA
# ══════════════════════════════════════════════════════════════════

# ── CDS Positions (4) ────────────────────────────────────────────
#
# desk_mark / vc_fair_value are in bps (CDS spread).
# book_value_usd is the notional * (spread / 10000) * remaining_years
# (roughly the premium leg PV for a par CDS).

CDS_POSITIONS: list[dict[str, Any]] = [
    {
        # 1. Ford Motor 5Y CDS $50M, Buy Protection, spread 185bps — GREEN, L2
        "trade_id": "T-20250214-301",
        "product_type": "CDS",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 50_000_000,
        "notional_usd": 50_000_000,
        "currency": "USD",
        "trade_date": "2025-02-14",
        "maturity_date": "2030-03-20",
        "settlement_date": "2025-02-19",
        "counterparty": "JPMorgan",
        "desk_mark": 185.00,
        "vc_fair_value": 183.50,
        "book_value_usd": 4_587_500,
        "fva_usd": -12_350,
        "exception_status": "GREEN",
        "fair_value_level": "L2",
        "pricing_source": "Markit CDS",
        "desk": "IG CDS",
        "notes": "Ford Motor Co 5Y CDS. Buy Protection. ISDA standard North American contract.",
    },
    {
        # 2. Tesla 3Y CDS $30M, Sell Protection, spread 225bps — AMBER, L2
        "trade_id": "T-20250214-302",
        "product_type": "CDS",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 30_000_000,
        "notional_usd": 30_000_000,
        "currency": "USD",
        "trade_date": "2025-02-12",
        "maturity_date": "2028-03-20",
        "settlement_date": "2025-02-19",
        "counterparty": "Goldman Sachs",
        "desk_mark": 225.00,
        "vc_fair_value": 218.40,
        "book_value_usd": 2_025_000,
        "fva_usd": -8_740,
        "exception_status": "AMBER",
        "fair_value_level": "L2",
        "pricing_source": "Markit CDS",
        "desk": "Credit Trading",
        "notes": "Tesla Inc 3Y CDS. Sell Protection. Spread volatility elevated — AMBER breach.",
    },
    {
        # 3. Brazil Sovereign 5Y CDS $75M, Buy Protection, spread 165bps — GREEN, L2
        "trade_id": "T-20250214-303",
        "product_type": "CDS",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 75_000_000,
        "notional_usd": 75_000_000,
        "currency": "USD",
        "trade_date": "2025-02-10",
        "maturity_date": "2030-03-20",
        "settlement_date": "2025-02-19",
        "counterparty": "Citi",
        "desk_mark": 165.00,
        "vc_fair_value": 163.80,
        "book_value_usd": 6_131_250,
        "fva_usd": -18_200,
        "exception_status": "GREEN",
        "fair_value_level": "L2",
        "pricing_source": "Markit CDS",
        "desk": "Credit Trading",
        "notes": "Federative Republic of Brazil 5Y sovereign CDS. Buy Protection.",
    },
    {
        # 4. Deutsche Bank 5Y CDS EUR 40M, Buy Protection, spread 95bps — GREEN, L2
        "trade_id": "T-20250214-304",
        "product_type": "CDS",
        "asset_class": "Credit",
        "currency_pair": "EUR/EUR",
        "notional": 40_000_000,
        "notional_usd": 43_292_000,
        "currency": "EUR",
        "trade_date": "2025-02-11",
        "maturity_date": "2030-03-20",
        "settlement_date": "2025-02-19",
        "counterparty": "BNP Paribas",
        "desk_mark": 95.00,
        "vc_fair_value": 94.25,
        "book_value_usd": 2_056_370,
        "fva_usd": -6_480,
        "exception_status": "GREEN",
        "fair_value_level": "L2",
        "pricing_source": "Markit CDS",
        "desk": "IG CDS",
        "notes": "Deutsche Bank AG 5Y CDS. Buy Protection. EUR-denominated, ISDA European convention.",
    },
]

# ── CLO Positions (3) ────────────────────────────────────────────
#
# desk_mark / vc_fair_value are price per $100 (clean price).

CLO_POSITIONS: list[dict[str, Any]] = [
    {
        # 5. CLO Senior AAA tranche $100M, 0-30% attachment — GREEN, L2
        "trade_id": "T-20250214-305",
        "product_type": "CLO",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 100_000_000,
        "notional_usd": 100_000_000,
        "currency": "USD",
        "trade_date": "2025-01-15",
        "maturity_date": "2035-04-15",
        "settlement_date": "2025-02-18",
        "counterparty": "Morgan Stanley",
        "desk_mark": 99.875,
        "vc_fair_value": 99.750,
        "book_value_usd": 99_875_000,
        "fva_usd": -22_500,
        "exception_status": "GREEN",
        "fair_value_level": "L2",
        "pricing_source": "Bloomberg CRVD",
        "desk": "Structured Credit",
        "notes": "CLO 2024-1A Senior AAA tranche. Mark-to-model with observable spread inputs.",
    },
    {
        # 6. CLO Mezzanine BBB tranche $25M, 10-15% — AMBER, L3
        "trade_id": "T-20250214-306",
        "product_type": "CLO",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 25_000_000,
        "notional_usd": 25_000_000,
        "currency": "USD",
        "trade_date": "2025-01-20",
        "maturity_date": "2035-04-15",
        "settlement_date": "2025-02-18",
        "counterparty": "Barclays",
        "desk_mark": 94.250,
        "vc_fair_value": 91.800,
        "book_value_usd": 23_562_500,
        "fva_usd": -45_600,
        "exception_status": "AMBER",
        "fair_value_level": "L3",
        "pricing_source": "Internal Model",
        "desk": "Structured Credit",
        "notes": "CLO 2024-1A Mezzanine BBB tranche. Limited observable quotes — AMBER breach.",
    },
    {
        # 7. CLO Equity tranche $10M, 0-3% — RED, L3
        "trade_id": "T-20250214-307",
        "product_type": "CLO",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 10_000_000,
        "notional_usd": 10_000_000,
        "currency": "USD",
        "trade_date": "2025-01-22",
        "maturity_date": "2035-04-15",
        "settlement_date": "2025-02-18",
        "counterparty": "Goldman Sachs",
        "desk_mark": 72.500,
        "vc_fair_value": 63.200,
        "book_value_usd": 7_250_000,
        "fva_usd": -82_300,
        "exception_status": "RED",
        "fair_value_level": "L3",
        "pricing_source": "Internal Model",
        "desk": "Structured Credit",
        "notes": "CLO 2024-1A Equity first-loss tranche. Illiquid, model-dependent — RED breach.",
    },
]

# ── CDO Positions (2) ────────────────────────────────────────────
#
# desk_mark / vc_fair_value are price per $100.

CDO_POSITIONS: list[dict[str, Any]] = [
    {
        # 8. Synthetic CDO Senior tranche $75M, AA rated — AMBER, L3
        "trade_id": "T-20250214-308",
        "product_type": "CDO",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 75_000_000,
        "notional_usd": 75_000_000,
        "currency": "USD",
        "trade_date": "2024-11-05",
        "maturity_date": "2032-06-20",
        "settlement_date": "2025-02-18",
        "counterparty": "JPMorgan",
        "desk_mark": 96.125,
        "vc_fair_value": 93.450,
        "book_value_usd": 72_093_750,
        "fva_usd": -125_400,
        "exception_status": "AMBER",
        "fair_value_level": "L3",
        "pricing_source": "Internal Model",
        "desk": "Structured Credit",
        "notes": "Synthetic CDO Senior AA tranche. Bespoke structure, limited comparables — AMBER breach.",
    },
    {
        # 9. Synthetic CDO Equity first-loss $15M — RED, L3
        "trade_id": "T-20250214-309",
        "product_type": "CDO",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 15_000_000,
        "notional_usd": 15_000_000,
        "currency": "USD",
        "trade_date": "2024-11-05",
        "maturity_date": "2032-06-20",
        "settlement_date": "2025-02-18",
        "counterparty": "Citi",
        "desk_mark": 58.750,
        "vc_fair_value": 48.200,
        "book_value_usd": 8_812_500,
        "fva_usd": -215_600,
        "exception_status": "RED",
        "fair_value_level": "L3",
        "pricing_source": "Internal Model",
        "desk": "Structured Credit",
        "notes": "Synthetic CDO Equity first-loss tranche. No market quotes — RED breach.",
    },
]

# ── MBS Positions (3) ────────────────────────────────────────────
#
# desk_mark / vc_fair_value are price per $100.

MBS_POSITIONS: list[dict[str, Any]] = [
    {
        # 10. Agency MBS (FNMA 30Y 5.5% TBA) $80M — GREEN, L1
        "trade_id": "T-20250214-310",
        "product_type": "MBS",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 80_000_000,
        "notional_usd": 80_000_000,
        "currency": "USD",
        "trade_date": "2025-02-10",
        "maturity_date": "2055-02-01",
        "settlement_date": "2025-03-13",
        "counterparty": "Morgan Stanley",
        "desk_mark": 101.625,
        "vc_fair_value": 101.500,
        "book_value_usd": 81_300_000,
        "fva_usd": -5_200,
        "exception_status": "GREEN",
        "fair_value_level": "L1",
        "pricing_source": "TRACE",
        "desk": "Securitized Products",
        "notes": "FNMA 30Y 5.5% TBA. Agency pass-through, highly liquid.",
    },
    {
        # 11. Non-Agency RMBS Mezzanine $20M — AMBER, L3
        "trade_id": "T-20250214-311",
        "product_type": "MBS",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 20_000_000,
        "notional_usd": 20_000_000,
        "currency": "USD",
        "trade_date": "2024-12-18",
        "maturity_date": "2054-07-25",
        "settlement_date": "2025-02-18",
        "counterparty": "Barclays",
        "desk_mark": 87.375,
        "vc_fair_value": 84.900,
        "book_value_usd": 17_475_000,
        "fva_usd": -68_900,
        "exception_status": "AMBER",
        "fair_value_level": "L3",
        "pricing_source": "Intex",
        "desk": "Securitized Products",
        "notes": "Non-Agency RMBS Mezzanine tranche. Credit-sensitive, limited liquidity — AMBER breach.",
    },
    {
        # 12. CMBS B-piece $15M — RED, L3
        "trade_id": "T-20250214-312",
        "product_type": "MBS",
        "asset_class": "Credit",
        "currency_pair": "USD/USD",
        "notional": 15_000_000,
        "notional_usd": 15_000_000,
        "currency": "USD",
        "trade_date": "2024-10-25",
        "maturity_date": "2057-11-15",
        "settlement_date": "2025-02-18",
        "counterparty": "BNP Paribas",
        "desk_mark": 68.250,
        "vc_fair_value": 59.400,
        "book_value_usd": 10_237_500,
        "fva_usd": -142_500,
        "exception_status": "RED",
        "fair_value_level": "L3",
        "pricing_source": "Intex",
        "desk": "Securitized Products",
        "notes": "CMBS B-piece subordinate exposure. Deep discount, illiquid — RED breach.",
    },
]

# ── Commodity Swap Positions (3) ─────────────────────────────────
#
# desk_mark / vc_fair_value are in $/unit for the swap.
# For WTI and NatGas the unit is per barrel and per MMBtu respectively.
# For Gold the unit is per troy oz.

COMMODITY_POSITIONS: list[dict[str, Any]] = [
    {
        # 13. WTI Crude Oil 1Y fixed-float swap $40M — GREEN, L2
        "trade_id": "T-20250214-313",
        "product_type": "Commodity Swap",
        "asset_class": "Commodity",
        "currency_pair": "USD/USD",
        "notional": 40_000_000,
        "notional_usd": 40_000_000,
        "currency": "USD",
        "trade_date": "2025-02-03",
        "maturity_date": "2026-02-03",
        "settlement_date": "2026-02-05",
        "counterparty": "Goldman Sachs",
        "desk_mark": 74.85,
        "vc_fair_value": 74.50,
        "book_value_usd": 39_920_000,
        "fva_usd": -15_800,
        "exception_status": "GREEN",
        "fair_value_level": "L2",
        "pricing_source": "ICE Settlement",
        "desk": "Commodity Derivatives",
        "notes": "WTI Crude Oil 1Y fixed-float swap. ICE Brent settlement pricing.",
    },
    {
        # 14. Natural Gas (Henry Hub) 6M swap $25M — AMBER, L2
        "trade_id": "T-20250214-314",
        "product_type": "Commodity Swap",
        "asset_class": "Commodity",
        "currency_pair": "USD/USD",
        "notional": 25_000_000,
        "notional_usd": 25_000_000,
        "currency": "USD",
        "trade_date": "2025-01-27",
        "maturity_date": "2025-07-28",
        "settlement_date": "2025-07-30",
        "counterparty": "Morgan Stanley",
        "desk_mark": 3.245,
        "vc_fair_value": 3.145,
        "book_value_usd": 24_962_500,
        "fva_usd": -9_350,
        "exception_status": "AMBER",
        "fair_value_level": "L2",
        "pricing_source": "ICE Settlement",
        "desk": "Commodity Derivatives",
        "notes": "Henry Hub Natural Gas 6M swap. Basis risk between delivery points — AMBER breach.",
    },
    {
        # 15. Gold swap 1Y 500 oz — GREEN, L1
        "trade_id": "T-20250214-315",
        "product_type": "Commodity Swap",
        "asset_class": "Commodity",
        "currency_pair": "XAU/USD",
        "notional": 500,
        "notional_usd": 1_467_500,
        "currency": "USD",
        "trade_date": "2025-02-05",
        "maturity_date": "2026-02-05",
        "settlement_date": "2026-02-09",
        "counterparty": "JPMorgan",
        "desk_mark": 2935.00,
        "vc_fair_value": 2928.50,
        "book_value_usd": 1_467_500,
        "fva_usd": -1_850,
        "exception_status": "GREEN",
        "fair_value_level": "L1",
        "pricing_source": "ICE Settlement",
        "desk": "Commodity Derivatives",
        "notes": "Gold 1Y fixed-float swap, 500 troy oz. LBMA PM Fix pricing.",
    },
]

# ── Combined list of all positions ───────────────────────────────

ALL_POSITIONS: list[dict[str, Any]] = (
    CDS_POSITIONS + CLO_POSITIONS + CDO_POSITIONS + MBS_POSITIONS + COMMODITY_POSITIONS
)


# ── CreditDetail reference data (CDS only) ──────────────────────

CREDIT_DETAILS: list[dict[str, Any]] = [
    {
        "trade_id": "T-20250214-301",
        "reference_entity": "Ford Motor Company",
        "seniority": "Senior",
        "cds_spread_bps": 185.00,
        "recovery_rate": 0.40,
        "restructuring_type": "XR",
    },
    {
        "trade_id": "T-20250214-302",
        "reference_entity": "Tesla Inc",
        "seniority": "Senior",
        "cds_spread_bps": 225.00,
        "recovery_rate": 0.40,
        "restructuring_type": "XR",
    },
    {
        "trade_id": "T-20250214-303",
        "reference_entity": "Federative Republic of Brazil",
        "seniority": "Senior",
        "cds_spread_bps": 165.00,
        "recovery_rate": 0.25,
        "restructuring_type": "CR",
    },
    {
        "trade_id": "T-20250214-304",
        "reference_entity": "Deutsche Bank AG",
        "seniority": "Senior",
        "cds_spread_bps": 95.00,
        "recovery_rate": 0.40,
        "restructuring_type": "MM",
    },
]

# ── StructuredProductDetail reference data (CLO/CDO/MBS) ────────

STRUCTURED_PRODUCT_DETAILS: list[dict[str, Any]] = [
    # CLO positions
    {
        "trade_id": "T-20250214-305",
        "tranche": "Senior",
        "attachment_pct": 30.0000,
        "detachment_pct": 100.0000,
        "pool_size": 150,
        "wac": 5.8500,
        "wam": 4.75,
        "credit_rating": "AAA",
        "collateral_type": "Senior Secured Loans",
    },
    {
        "trade_id": "T-20250214-306",
        "tranche": "Mezzanine",
        "attachment_pct": 10.0000,
        "detachment_pct": 15.0000,
        "pool_size": 150,
        "wac": 5.8500,
        "wam": 4.75,
        "credit_rating": "BBB",
        "collateral_type": "Senior Secured Loans",
    },
    {
        "trade_id": "T-20250214-307",
        "tranche": "Equity",
        "attachment_pct": 0.0000,
        "detachment_pct": 3.0000,
        "pool_size": 150,
        "wac": 5.8500,
        "wam": 4.75,
        "credit_rating": "NR",
        "collateral_type": "Senior Secured Loans",
    },
    # CDO positions
    {
        "trade_id": "T-20250214-308",
        "tranche": "Senior",
        "attachment_pct": 15.0000,
        "detachment_pct": 35.0000,
        "pool_size": 125,
        "wac": 4.9500,
        "wam": 5.20,
        "credit_rating": "AA",
        "collateral_type": "Synthetic CDS Portfolio",
    },
    {
        "trade_id": "T-20250214-309",
        "tranche": "Equity",
        "attachment_pct": 0.0000,
        "detachment_pct": 3.0000,
        "pool_size": 125,
        "wac": 4.9500,
        "wam": 5.20,
        "credit_rating": "NR",
        "collateral_type": "Synthetic CDS Portfolio",
    },
    # MBS positions
    {
        "trade_id": "T-20250214-310",
        "tranche": "Senior",
        "attachment_pct": 0.0000,
        "detachment_pct": 100.0000,
        "pool_size": 3200,
        "wac": 5.5000,
        "wam": 28.50,
        "credit_rating": "AAA",
        "collateral_type": "Agency Residential Mortgages",
    },
    {
        "trade_id": "T-20250214-311",
        "tranche": "Mezzanine",
        "attachment_pct": 5.0000,
        "detachment_pct": 15.0000,
        "pool_size": 2800,
        "wac": 6.1200,
        "wam": 26.30,
        "credit_rating": "BBB-",
        "collateral_type": "Non-Agency Residential Mortgages",
    },
    {
        "trade_id": "T-20250214-312",
        "tranche": "Equity",
        "attachment_pct": 0.0000,
        "detachment_pct": 5.0000,
        "pool_size": 45,
        "wac": 5.7500,
        "wam": 8.40,
        "credit_rating": "B",
        "collateral_type": "Commercial Mortgage Loans",
    },
]

# ── CommodityDetail reference data (Commodity Swaps) ────────────

COMMODITY_DETAILS: list[dict[str, Any]] = [
    {
        "trade_id": "T-20250214-313",
        "commodity": "WTI",
        "contract_unit": "bbl",
        "fixed_price": 74.50,
        "float_index": "ICE Brent",
        "settlement_type": "Cash",
        "delivery_point": "Cushing, Oklahoma",
    },
    {
        "trade_id": "T-20250214-314",
        "commodity": "NatGas",
        "contract_unit": "MMBtu",
        "fixed_price": 3.10,
        "float_index": "NYMEX Henry Hub",
        "settlement_type": "Cash",
        "delivery_point": "Henry Hub, Louisiana",
    },
    {
        "trade_id": "T-20250214-315",
        "commodity": "Gold",
        "contract_unit": "oz",
        "fixed_price": 2920.00,
        "float_index": "LBMA PM Fix",
        "settlement_type": "Cash",
        "delivery_point": "London",
    },
]

# ── Dealer quotes for Level 3 positions ──────────────────────────
#
# L3 positions: T-306 (CLO Mezz), T-307 (CLO Equity), T-308 (CDO Senior),
#               T-309 (CDO Equity), T-311 (Non-Agency RMBS), T-312 (CMBS B-piece)

L3_DEALER_QUOTES: list[dict[str, Any]] = [
    # CLO Mezzanine BBB (T-306) — quotes around vc_fair_value 91.80
    {
        "trade_id": "T-20250214-306",
        "dealer_name": "JPMorgan",
        "quote_value": 92.125,
        "quote_type": "Bid",
    },
    {
        "trade_id": "T-20250214-306",
        "dealer_name": "Barclays",
        "quote_value": 91.500,
        "quote_type": "Mid",
    },
    {
        "trade_id": "T-20250214-306",
        "dealer_name": "Morgan Stanley",
        "quote_value": 91.750,
        "quote_type": "Offer",
    },
    # CLO Equity (T-307) — quotes around vc_fair_value 63.20
    {
        "trade_id": "T-20250214-307",
        "dealer_name": "Goldman Sachs",
        "quote_value": 63.500,
        "quote_type": "Bid",
    },
    {
        "trade_id": "T-20250214-307",
        "dealer_name": "Citi",
        "quote_value": 62.750,
        "quote_type": "Mid",
    },
    {
        "trade_id": "T-20250214-307",
        "dealer_name": "JPMorgan",
        "quote_value": 63.375,
        "quote_type": "Offer",
    },
    # Synthetic CDO Senior AA (T-308) — quotes around vc_fair_value 93.45
    {
        "trade_id": "T-20250214-308",
        "dealer_name": "Morgan Stanley",
        "quote_value": 93.250,
        "quote_type": "Bid",
    },
    {
        "trade_id": "T-20250214-308",
        "dealer_name": "BNP Paribas",
        "quote_value": 93.750,
        "quote_type": "Mid",
    },
    {
        "trade_id": "T-20250214-308",
        "dealer_name": "Goldman Sachs",
        "quote_value": 93.375,
        "quote_type": "Offer",
    },
    # Synthetic CDO Equity (T-309) — quotes around vc_fair_value 48.20
    {
        "trade_id": "T-20250214-309",
        "dealer_name": "JPMorgan",
        "quote_value": 48.500,
        "quote_type": "Bid",
    },
    {
        "trade_id": "T-20250214-309",
        "dealer_name": "Citi",
        "quote_value": 47.750,
        "quote_type": "Mid",
    },
    {
        "trade_id": "T-20250214-309",
        "dealer_name": "Barclays",
        "quote_value": 48.375,
        "quote_type": "Offer",
    },
    # Non-Agency RMBS Mezzanine (T-311) — quotes around vc_fair_value 84.90
    {
        "trade_id": "T-20250214-311",
        "dealer_name": "Goldman Sachs",
        "quote_value": 85.125,
        "quote_type": "Bid",
    },
    {
        "trade_id": "T-20250214-311",
        "dealer_name": "Morgan Stanley",
        "quote_value": 84.625,
        "quote_type": "Mid",
    },
    {
        "trade_id": "T-20250214-311",
        "dealer_name": "BNP Paribas",
        "quote_value": 84.875,
        "quote_type": "Offer",
    },
    # CMBS B-piece (T-312) — quotes around vc_fair_value 59.40
    {
        "trade_id": "T-20250214-312",
        "dealer_name": "Citi",
        "quote_value": 59.750,
        "quote_type": "Bid",
    },
    {
        "trade_id": "T-20250214-312",
        "dealer_name": "Barclays",
        "quote_value": 59.000,
        "quote_type": "Mid",
    },
    {
        "trade_id": "T-20250214-312",
        "dealer_name": "JPMorgan",
        "quote_value": 59.500,
        "quote_type": "Offer",
    },
]


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


def _build_trade_id_map(positions: list[Position]) -> dict[str, Position]:
    """Build a lookup from trade_id to Position ORM object."""
    return {p.trade_id: p for p in positions}


# ══════════════════════════════════════════════════════════════════
# SEEDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════


async def seed_credit_commodity_positions(db: AsyncSession) -> list[Position]:
    """Seed all 15 Credit and Commodity positions.

    Returns the created ORM objects (with PK assigned).
    Handles idempotency: skips positions whose trade_id already exists.
    """
    created: list[Position] = []

    for pos_data in ALL_POSITIONS:
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
        logger.info("Seeded %d credit/commodity positions", len(created))

    return created


async def seed_credit_details(db: AsyncSession, positions: list[Position]) -> list[CreditDetail]:
    """Seed CreditDetail records for all CDS positions.

    Links each CreditDetail to its parent Position via position_id.
    Handles idempotency: skips details that already exist.
    """
    trade_id_map = _build_trade_id_map(positions)
    created: list[CreditDetail] = []

    for detail_data in CREDIT_DETAILS:
        trade_id = detail_data["trade_id"]

        # Find the parent position
        pos = trade_id_map.get(trade_id)
        if pos is None:
            # Try to look up from DB
            result = await db.execute(
                select(Position).where(Position.trade_id == trade_id)
            )
            pos = result.scalar_one_or_none()

        if pos is None:
            logger.warning("Position %s not found, skipping credit detail", trade_id)
            continue

        # Idempotency check
        existing = await db.get(CreditDetail, pos.position_id)
        if existing is not None:
            logger.info("CreditDetail already exists for position %d, skipping", pos.position_id)
            continue

        detail = CreditDetail(
            position_id=pos.position_id,
            reference_entity=detail_data["reference_entity"],
            seniority=detail_data["seniority"],
            cds_spread_bps=Decimal(str(detail_data["cds_spread_bps"])),
            recovery_rate=Decimal(str(detail_data["recovery_rate"])),
            restructuring_type=detail_data["restructuring_type"],
        )
        db.add(detail)
        created.append(detail)

    if created:
        await db.flush()
        logger.info("Seeded %d credit details", len(created))

    return created


async def seed_structured_product_details(
    db: AsyncSession, positions: list[Position]
) -> list[StructuredProductDetail]:
    """Seed StructuredProductDetail records for CLO, CDO, and MBS positions.

    Links each StructuredProductDetail to its parent Position via position_id.
    Handles idempotency: skips details that already exist.
    """
    trade_id_map = _build_trade_id_map(positions)
    created: list[StructuredProductDetail] = []

    for detail_data in STRUCTURED_PRODUCT_DETAILS:
        trade_id = detail_data["trade_id"]

        # Find the parent position
        pos = trade_id_map.get(trade_id)
        if pos is None:
            result = await db.execute(
                select(Position).where(Position.trade_id == trade_id)
            )
            pos = result.scalar_one_or_none()

        if pos is None:
            logger.warning("Position %s not found, skipping structured product detail", trade_id)
            continue

        # Idempotency check
        existing = await db.get(StructuredProductDetail, pos.position_id)
        if existing is not None:
            logger.info(
                "StructuredProductDetail already exists for position %d, skipping",
                pos.position_id,
            )
            continue

        detail = StructuredProductDetail(
            position_id=pos.position_id,
            tranche=detail_data["tranche"],
            attachment_pct=Decimal(str(detail_data["attachment_pct"])),
            detachment_pct=Decimal(str(detail_data["detachment_pct"])),
            pool_size=detail_data["pool_size"],
            wac=Decimal(str(detail_data["wac"])),
            wam=Decimal(str(detail_data["wam"])),
            credit_rating=detail_data["credit_rating"],
            collateral_type=detail_data["collateral_type"],
        )
        db.add(detail)
        created.append(detail)

    if created:
        await db.flush()
        logger.info("Seeded %d structured product details", len(created))

    return created


async def seed_commodity_details(
    db: AsyncSession, positions: list[Position]
) -> list[CommodityDetail]:
    """Seed CommodityDetail records for all Commodity Swap positions.

    Links each CommodityDetail to its parent Position via position_id.
    Handles idempotency: skips details that already exist.
    """
    trade_id_map = _build_trade_id_map(positions)
    created: list[CommodityDetail] = []

    for detail_data in COMMODITY_DETAILS:
        trade_id = detail_data["trade_id"]

        # Find the parent position
        pos = trade_id_map.get(trade_id)
        if pos is None:
            result = await db.execute(
                select(Position).where(Position.trade_id == trade_id)
            )
            pos = result.scalar_one_or_none()

        if pos is None:
            logger.warning("Position %s not found, skipping commodity detail", trade_id)
            continue

        # Idempotency check
        existing = await db.get(CommodityDetail, pos.position_id)
        if existing is not None:
            logger.info(
                "CommodityDetail already exists for position %d, skipping",
                pos.position_id,
            )
            continue

        detail = CommodityDetail(
            position_id=pos.position_id,
            commodity=detail_data["commodity"],
            contract_unit=detail_data["contract_unit"],
            fixed_price=Decimal(str(detail_data["fixed_price"])),
            float_index=detail_data["float_index"],
            settlement_type=detail_data["settlement_type"],
            delivery_point=detail_data["delivery_point"],
        )
        db.add(detail)
        created.append(detail)

    if created:
        await db.flush()
        logger.info("Seeded %d commodity details", len(created))

    return created


async def seed_credit_commodity_dealer_quotes(
    db: AsyncSession, positions: list[Position]
) -> list[DealerQuote]:
    """Seed dealer quotes for all Level 3 positions.

    Level 3 positions require dealer quote evidence to support fair value.
    Quotes are sourced from major sell-side counterparties.
    Handles idempotency: skips quotes that already exist.
    """
    trade_id_map = _build_trade_id_map(positions)
    created: list[DealerQuote] = []

    for quote_data in L3_DEALER_QUOTES:
        trade_id = quote_data["trade_id"]

        # Find the parent position
        pos = trade_id_map.get(trade_id)
        if pos is None:
            result = await db.execute(
                select(Position).where(Position.trade_id == trade_id)
            )
            pos = result.scalar_one_or_none()

        if pos is None:
            logger.warning("Position %s not found, skipping dealer quote", trade_id)
            continue

        # Idempotency check
        existing = await db.execute(
            select(DealerQuote).where(
                DealerQuote.position_id == pos.position_id,
                DealerQuote.dealer_name == quote_data["dealer_name"],
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        quote = DealerQuote(
            position_id=pos.position_id,
            dealer_name=quote_data["dealer_name"],
            quote_value=Decimal(str(quote_data["quote_value"])),
            quote_date=VALUATION_DATE,
            quote_type=quote_data["quote_type"],
        )
        db.add(quote)
        created.append(quote)

    if created:
        await db.flush()
        logger.info("Seeded %d credit/commodity dealer quotes", len(created))

    return created


# ══════════════════════════════════════════════════════════════════
# MASTER SEED FUNCTION
# ══════════════════════════════════════════════════════════════════


async def seed_all_credit_commodity(db: AsyncSession) -> dict[str, Any]:
    """Seed all credit and commodity data in the correct order.

    Returns a summary of what was seeded.

    Order:
    1. Positions (15 credit + commodity positions)
    2. Credit details (CDS)
    3. Structured product details (CLO/CDO/MBS)
    4. Commodity details (Commodity Swaps)
    5. Dealer quotes (Level 3 positions)
    """
    results: dict[str, Any] = {}

    # 1. Positions
    positions = await seed_credit_commodity_positions(db)
    results["positions_created"] = len(positions)

    # If no new positions were created, load existing ones for downstream seeding
    if not positions:
        trade_ids = [p["trade_id"] for p in ALL_POSITIONS]
        pos_result = await db.execute(
            select(Position).where(Position.trade_id.in_(trade_ids))
        )
        positions = list(pos_result.scalars().all())
        results["positions_created"] = 0
        results["positions_existing"] = len(positions)

    # 2. Credit details
    credit_details = await seed_credit_details(db, positions)
    results["credit_details_created"] = len(credit_details)

    # 3. Structured product details
    structured_details = await seed_structured_product_details(db, positions)
    results["structured_product_details_created"] = len(structured_details)

    # 4. Commodity details
    commodity_details = await seed_commodity_details(db, positions)
    results["commodity_details_created"] = len(commodity_details)

    # 5. Dealer quotes
    dealer_quotes = await seed_credit_commodity_dealer_quotes(db, positions)
    results["dealer_quotes_created"] = len(dealer_quotes)

    # Commit all changes
    await db.commit()

    logger.info("Credit/commodity seed complete: %s", results)
    return results


# ══════════════════════════════════════════════════════════════════
# STANDALONE ENTRY POINT
# ══════════════════════════════════════════════════════════════════


async def _main() -> None:
    """Run the seeder as a standalone script."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
    async with async_session_factory() as session:
        summary = await seed_all_credit_commodity(session)
        logger.info("Seed summary: %s", summary)


if __name__ == "__main__":
    asyncio.run(_main())

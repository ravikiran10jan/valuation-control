"""XVA adjustments, expanded market data, exceptions, and valuation comparisons
for all new product types (Rates, FX Products, Credit/Commodity).

Seeds:
- Net XVA (CVA + FVA - DVA) stored as ``fva_usd`` on every OTC derivative position
- Market data snapshots: yield curves, CDS spreads, commodity prices, treasury
  yields, and muni yields
- Exception records for all AMBER / RED positions across the expanded universe
- Exception comments with realistic VC-vs-desk dispute dialogue for RED items
- Valuation comparison records for all 41 new positions

Can be run as a standalone script or imported by API seed routes.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.postgres import (
    Position,
    MarketDataSnapshot,
    VCException,
    ExceptionComment,
    ValuationComparison,
    CommitteeAgendaItem,
)

logger = logging.getLogger(__name__)

# ── Valuation date used across all seed data ─────────────────────
VALUATION_DATE = date(2025, 2, 14)


# ══════════════════════════════════════════════════════════════════
# TRADE-ID RANGES BY ASSET CLASS
# ══════════════════════════════════════════════════════════════════

# Rates: T-20250214-101 .. T-20250214-114  (position_ids 8-21)
RATES_TRADE_IDS = [f"T-20250214-{i}" for i in range(101, 115)]

# FX Products: T-20250214-201 .. T-20250214-212  (position_ids 22-33)
FX_TRADE_IDS = [f"T-20250214-{i}" for i in range(201, 213)]

# Credit / Commodity: T-20250214-301 .. T-20250214-315  (position_ids 34-48)
CREDIT_COMMODITY_TRADE_IDS = [f"T-20250214-{i}" for i in range(301, 316)]

ALL_NEW_TRADE_IDS = RATES_TRADE_IDS + FX_TRADE_IDS + CREDIT_COMMODITY_TRADE_IDS

# Original 7 FX positions (position_ids 1-7)
ORIGINAL_FX_TRADE_IDS = [
    "T-20250214-001",
    "T-20250213-002",
    "T-20250212-003",
    "T-20250210-004",
    "T-20250211-005",
    "T-20250120-006",
    "T-20250105-007",
]


# ══════════════════════════════════════════════════════════════════
# XVA ADJUSTMENT PARAMETERS
# ══════════════════════════════════════════════════════════════════

# XVA parameters by trade_id.  Net XVA = CVA + FVA - DVA  (stored as fva_usd).
# For OTC derivatives the net is always a cost (negative), except where DVA
# dominates on short-risk positions.
#
# CVA: 2-15 bps IG, 15-50 bps HY of notional
# FVA: 5-20 bps of exposure (approximated as fraction of notional)
# DVA: 1-5 bps offset

XVA_ADJUSTMENTS: dict[str, dict[str, Any]] = {
    # ── Original FX positions (1-7) ──────────────────────────────
    # Position 1: EUR/USD Spot 150M — very short tenor, minimal XVA
    "T-20250214-001": {
        "cva_bps": 2, "fva_bps": 5, "dva_bps": 1,
        "notional": 150_000_000, "exposure_pct": 0.01,
    },
    # Position 2: GBP/USD Spot 85M
    "T-20250213-002": {
        "cva_bps": 2, "fva_bps": 5, "dva_bps": 1,
        "notional": 85_000_000, "exposure_pct": 0.01,
    },
    # Position 3: USD/JPY Spot 50M
    "T-20250212-003": {
        "cva_bps": 2, "fva_bps": 5, "dva_bps": 1,
        "notional": 50_000_000, "exposure_pct": 0.01,
    },
    # Position 4: USD/TRY Spot 25M — EM, higher CVA
    "T-20250210-004": {
        "cva_bps": 8, "fva_bps": 12, "dva_bps": 2,
        "notional": 25_000_000, "exposure_pct": 0.05,
    },
    # Position 5: USD/BRL Spot 10M — EM
    "T-20250211-005": {
        "cva_bps": 6, "fva_bps": 10, "dva_bps": 2,
        "notional": 10_000_000, "exposure_pct": 0.03,
    },
    # Position 6: EUR/USD 1Y Forward 120M — longer tenor
    "T-20250120-006": {
        "cva_bps": 5, "fva_bps": 8, "dva_bps": 2,
        "notional": 120_000_000, "exposure_pct": 0.03,
    },
    # Position 7: EUR/USD DNT Barrier 50M — L3 exotic
    "T-20250105-007": {
        "cva_bps": 12, "fva_bps": 18, "dva_bps": 3,
        "notional": 50_000_000, "exposure_pct": 0.08,
    },

    # ── Rates positions (8-21): IRS, Futures, Options, Munis, Bonds ──
    # 101: 10Y USD IRS 500M — IG, moderate tenor
    "T-20250214-101": {
        "cva_bps": 5, "fva_bps": 10, "dva_bps": 2,
        "notional": 500_000_000, "exposure_pct": 0.04,
    },
    # 102: 5Y EUR IRS 250M — IG
    "T-20250214-102": {
        "cva_bps": 4, "fva_bps": 8, "dva_bps": 2,
        "notional": 250_000_000, "exposure_pct": 0.03,
    },
    # 103: 2Y USD IRS 100M — short tenor IG  (AMBER)
    "T-20250214-103": {
        "cva_bps": 3, "fva_bps": 7, "dva_bps": 1,
        "notional": 100_000_000, "exposure_pct": 0.02,
    },
    # 104: 30Y GBP IRS 150M — long tenor, higher CVA  (RED)
    "T-20250214-104": {
        "cva_bps": 12, "fva_bps": 18, "dva_bps": 3,
        "notional": 150_000_000, "exposure_pct": 0.08,
    },
    # 105: 7Y USD IRS 300M
    "T-20250214-105": {
        "cva_bps": 5, "fva_bps": 9, "dva_bps": 2,
        "notional": 300_000_000, "exposure_pct": 0.035,
    },
    # 106: 3Y EUR IRS 200M
    "T-20250214-106": {
        "cva_bps": 3, "fva_bps": 7, "dva_bps": 1,
        "notional": 200_000_000, "exposure_pct": 0.025,
    },
    # 107: UST 10Y Futures — exchange-traded, minimal XVA
    "T-20250214-107": {
        "cva_bps": 0, "fva_bps": 1, "dva_bps": 0,
        "notional": 100_000_000, "exposure_pct": 0.005,
    },
    # 108: Eurodollar Futures  (AMBER)
    "T-20250214-108": {
        "cva_bps": 0, "fva_bps": 1, "dva_bps": 0,
        "notional": 75_000_000, "exposure_pct": 0.005,
    },
    # 109: UST 5Y Futures
    "T-20250214-109": {
        "cva_bps": 0, "fva_bps": 1, "dva_bps": 0,
        "notional": 50_000_000, "exposure_pct": 0.005,
    },
    # 110: USD Swaption 3Mx10Y  (AMBER)
    "T-20250214-110": {
        "cva_bps": 7, "fva_bps": 14, "dva_bps": 2,
        "notional": 200_000_000, "exposure_pct": 0.05,
    },
    # 111: EUR Swaption 6Mx5Y  (RED)
    "T-20250214-111": {
        "cva_bps": 8, "fva_bps": 15, "dva_bps": 2,
        "notional": 150_000_000, "exposure_pct": 0.06,
    },
    # 112: Cap/Floor 2Y USD
    "T-20250214-112": {
        "cva_bps": 4, "fva_bps": 8, "dva_bps": 1,
        "notional": 100_000_000, "exposure_pct": 0.03,
    },
    # 113: NY Muni Bond 10Y  (AMBER)
    "T-20250214-113": {
        "cva_bps": 3, "fva_bps": 6, "dva_bps": 1,
        "notional": 50_000_000, "exposure_pct": 0.02,
    },
    # 114: IL Muni Bond 7Y  (RED)
    "T-20250214-114": {
        "cva_bps": 8, "fva_bps": 12, "dva_bps": 2,
        "notional": 30_000_000, "exposure_pct": 0.04,
    },

    # ── FX Products (22-33): Forwards, Vanilla Options, Exotics ──
    # 201: EUR/USD 6M FWD 200M
    "T-20250214-201": {
        "cva_bps": 4, "fva_bps": 7, "dva_bps": 2,
        "notional": 200_000_000, "exposure_pct": 0.02,
    },
    # 202: GBP/USD 3M FWD 100M
    "T-20250214-202": {
        "cva_bps": 3, "fva_bps": 6, "dva_bps": 1,
        "notional": 100_000_000, "exposure_pct": 0.015,
    },
    # 203: USD/JPY 1Y FWD 75M  (AMBER — position 3 of FX Forwards)
    "T-20250214-203": {
        "cva_bps": 5, "fva_bps": 9, "dva_bps": 2,
        "notional": 75_000_000, "exposure_pct": 0.03,
    },
    # 204: USD/MXN 6M FWD 50M
    "T-20250214-204": {
        "cva_bps": 7, "fva_bps": 11, "dva_bps": 2,
        "notional": 50_000_000, "exposure_pct": 0.04,
    },
    # 205: EUR/USD Vanilla Call 150M
    "T-20250214-205": {
        "cva_bps": 6, "fva_bps": 10, "dva_bps": 2,
        "notional": 150_000_000, "exposure_pct": 0.04,
    },
    # 206: GBP/USD Vanilla Put 80M
    "T-20250214-206": {
        "cva_bps": 5, "fva_bps": 9, "dva_bps": 2,
        "notional": 80_000_000, "exposure_pct": 0.035,
    },
    # 207: USD/JPY Vanilla Call 60M  (AMBER — position 7 of FX Options)
    "T-20250214-207": {
        "cva_bps": 5, "fva_bps": 10, "dva_bps": 2,
        "notional": 60_000_000, "exposure_pct": 0.04,
    },
    # 208: EUR/USD KO Barrier 100M
    "T-20250214-208": {
        "cva_bps": 10, "fva_bps": 16, "dva_bps": 3,
        "notional": 100_000_000, "exposure_pct": 0.07,
    },
    # 209: GBP/USD KI Barrier 70M  (RED — position 9 of FX Exotics)
    "T-20250214-209": {
        "cva_bps": 12, "fva_bps": 18, "dva_bps": 3,
        "notional": 70_000_000, "exposure_pct": 0.08,
    },
    # 210: USD/JPY DNT 50M  (RED — position 10 of FX Exotics)
    "T-20250214-210": {
        "cva_bps": 14, "fva_bps": 20, "dva_bps": 4,
        "notional": 50_000_000, "exposure_pct": 0.09,
    },
    # 211: EUR/GBP Range Accrual 40M  (AMBER — position 11 of FX Exotics)
    "T-20250214-211": {
        "cva_bps": 10, "fva_bps": 15, "dva_bps": 3,
        "notional": 40_000_000, "exposure_pct": 0.06,
    },
    # 212: USD/BRL Barrier 30M  (RED — position 12 of FX Exotics)
    "T-20250214-212": {
        "cva_bps": 15, "fva_bps": 20, "dva_bps": 4,
        "notional": 30_000_000, "exposure_pct": 0.10,
    },

    # ── Credit / Commodity (34-48): CDS, CLO, CDO, MBS, Commodity ──
    # 301: CDS Ford 5Y 25M
    "T-20250214-301": {
        "cva_bps": 15, "fva_bps": 10, "dva_bps": 3,
        "notional": 25_000_000, "exposure_pct": 0.06,
    },
    # 302: CDS Tesla 3Y 15M  (AMBER — position 2 of CDS)
    "T-20250214-302": {
        "cva_bps": 25, "fva_bps": 15, "dva_bps": 4,
        "notional": 15_000_000, "exposure_pct": 0.08,
    },
    # 303: CDS Brazil 5Y 20M
    "T-20250214-303": {
        "cva_bps": 18, "fva_bps": 12, "dva_bps": 3,
        "notional": 20_000_000, "exposure_pct": 0.07,
    },
    # 304: CDS DeutscheBank 5Y 10M
    "T-20250214-304": {
        "cva_bps": 10, "fva_bps": 8, "dva_bps": 2,
        "notional": 10_000_000, "exposure_pct": 0.05,
    },
    # 305: CDS IG Index 5Y 50M
    "T-20250214-305": {
        "cva_bps": 4, "fva_bps": 6, "dva_bps": 1,
        "notional": 50_000_000, "exposure_pct": 0.03,
    },
    # 306: CLO Senior AAA 30M  (AMBER — position 6 of CLO)
    "T-20250214-306": {
        "cva_bps": 3, "fva_bps": 7, "dva_bps": 1,
        "notional": 30_000_000, "exposure_pct": 0.025,
    },
    # 307: CLO Mezzanine BB 20M  (RED — position 7 of CLO)
    "T-20250214-307": {
        "cva_bps": 35, "fva_bps": 18, "dva_bps": 5,
        "notional": 20_000_000, "exposure_pct": 0.12,
    },
    # 308: CDO Tranche AA 25M  (AMBER — position 8 of CDO)
    "T-20250214-308": {
        "cva_bps": 8, "fva_bps": 10, "dva_bps": 2,
        "notional": 25_000_000, "exposure_pct": 0.04,
    },
    # 309: CDO Equity Tranche 10M  (RED — position 9 of CDO)
    "T-20250214-309": {
        "cva_bps": 50, "fva_bps": 20, "dva_bps": 5,
        "notional": 10_000_000, "exposure_pct": 0.20,
    },
    # 310: Agency MBS Pool 40M
    "T-20250214-310": {
        "cva_bps": 3, "fva_bps": 6, "dva_bps": 1,
        "notional": 40_000_000, "exposure_pct": 0.02,
    },
    # 311: Non-Agency MBS 20M  (AMBER — position 11 of MBS)
    "T-20250214-311": {
        "cva_bps": 12, "fva_bps": 14, "dva_bps": 3,
        "notional": 20_000_000, "exposure_pct": 0.06,
    },
    # 312: CMBS B-piece 15M  (RED — position 12 of MBS)
    "T-20250214-312": {
        "cva_bps": 40, "fva_bps": 18, "dva_bps": 5,
        "notional": 15_000_000, "exposure_pct": 0.15,
    },
    # 313: WTI Crude Swap 35M
    "T-20250214-313": {
        "cva_bps": 6, "fva_bps": 10, "dva_bps": 2,
        "notional": 35_000_000, "exposure_pct": 0.04,
    },
    # 314: NatGas Swap 20M  (AMBER — position 14 of Commodity)
    "T-20250214-314": {
        "cva_bps": 8, "fva_bps": 12, "dva_bps": 2,
        "notional": 20_000_000, "exposure_pct": 0.05,
    },
    # 315: Gold Forward 25M
    "T-20250214-315": {
        "cva_bps": 4, "fva_bps": 7, "dva_bps": 1,
        "notional": 25_000_000, "exposure_pct": 0.03,
    },
}


def _compute_net_xva(params: dict[str, Any]) -> Decimal:
    """Compute net XVA = CVA + FVA - DVA in USD.

    CVA and FVA are costs (positive inputs that produce a negative P&L impact).
    DVA is an offset (reduces the cost).  The stored ``fva_usd`` is the net
    impact, typically negative for the bank.

    CVA = notional * exposure_pct * cva_bps / 10_000
    FVA = notional * exposure_pct * fva_bps / 10_000
    DVA = notional * exposure_pct * dva_bps / 10_000
    net = -(CVA + FVA) + DVA   (negative = cost to the bank)
    """
    notional = Decimal(str(params["notional"]))
    exposure_pct = Decimal(str(params["exposure_pct"]))
    exposure = notional * exposure_pct

    cva = exposure * Decimal(str(params["cva_bps"])) / Decimal("10000")
    fva = exposure * Decimal(str(params["fva_bps"])) / Decimal("10000")
    dva = exposure * Decimal(str(params["dva_bps"])) / Decimal("10000")

    net_xva = -(cva + fva) + dva
    return net_xva.quantize(Decimal("0.01"))


# ══════════════════════════════════════════════════════════════════
# MARKET DATA DEFINITIONS
# ══════════════════════════════════════════════════════════════════

YIELD_CURVE_DATA: list[tuple[str, str, str]] = [
    # (source, field_name, value)
    # USD SOFR curve
    ("ICE Benchmark", "USD_SOFR_1M", "5.32"),
    ("ICE Benchmark", "USD_SOFR_3M", "5.30"),
    ("ICE Benchmark", "USD_SOFR_6M", "5.15"),
    ("ICE Benchmark", "USD_SOFR_1Y", "4.85"),
    ("ICE Benchmark", "USD_SOFR_2Y", "4.52"),
    ("ICE Benchmark", "USD_SOFR_5Y", "4.25"),
    ("ICE Benchmark", "USD_SOFR_10Y", "4.35"),
    ("ICE Benchmark", "USD_SOFR_30Y", "4.55"),
    # EUR EURIBOR curve
    ("ICE Benchmark", "EUR_EURIBOR_1M", "3.85"),
    ("ICE Benchmark", "EUR_EURIBOR_3M", "3.82"),
    ("ICE Benchmark", "EUR_EURIBOR_6M", "3.65"),
    ("ICE Benchmark", "EUR_EURIBOR_1Y", "3.35"),
    ("ICE Benchmark", "EUR_EURIBOR_2Y", "3.02"),
    ("ICE Benchmark", "EUR_EURIBOR_5Y", "2.85"),
    ("ICE Benchmark", "EUR_EURIBOR_10Y", "2.95"),
    ("ICE Benchmark", "EUR_EURIBOR_30Y", "3.10"),
    # GBP SONIA curve
    ("ICE Benchmark", "GBP_SONIA_1M", "5.15"),
    ("ICE Benchmark", "GBP_SONIA_3M", "5.10"),
    ("ICE Benchmark", "GBP_SONIA_6M", "4.95"),
    ("ICE Benchmark", "GBP_SONIA_1Y", "4.65"),
    ("ICE Benchmark", "GBP_SONIA_2Y", "4.35"),
    ("ICE Benchmark", "GBP_SONIA_5Y", "4.15"),
    ("ICE Benchmark", "GBP_SONIA_10Y", "4.25"),
    ("ICE Benchmark", "GBP_SONIA_30Y", "4.40"),
]

CDS_SPREAD_DATA: list[tuple[str, str, str]] = [
    ("Markit", "CDS_Ford_5Y_bps", "185"),
    ("Markit", "CDS_Tesla_3Y_bps", "225"),
    ("Markit", "CDS_Brazil_5Y_bps", "165"),
    ("Markit", "CDS_DeutscheBank_5Y_bps", "95"),
]

COMMODITY_DATA: list[tuple[str, str, str]] = [
    ("ICE Settlement", "COMMODITY_WTI_spot", "76.85"),
    ("ICE Settlement", "COMMODITY_BRENT_spot", "81.20"),
    ("ICE Settlement", "COMMODITY_NATGAS_spot", "2.45"),
    ("ICE Settlement", "COMMODITY_GOLD_spot", "2025.50"),
]

TREASURY_DATA: list[tuple[str, str, str]] = [
    ("Bloomberg VCUB", "UST_2Y", "4.48"),
    ("Bloomberg VCUB", "UST_5Y", "4.22"),
    ("Bloomberg VCUB", "UST_10Y", "4.32"),
    ("Bloomberg VCUB", "UST_30Y", "4.52"),
]

MUNI_DATA: list[tuple[str, str, str]] = [
    ("Bloomberg MUNI", "MUNI_NY_10Y", "3.15"),
    ("Bloomberg MUNI", "MUNI_CA_15Y", "3.45"),
    ("Bloomberg MUNI", "MUNI_IL_7Y", "4.05"),
]


# ══════════════════════════════════════════════════════════════════
# EXCEPTION DEFINITIONS
# ══════════════════════════════════════════════════════════════════

# Each entry: (trade_id, severity, status, days_open, escalation_level,
#              assigned_to, difference, difference_pct, description)
EXCEPTION_DEFINITIONS: list[dict[str, Any]] = [
    # ── Rates ────────────────────────────────────────────────────
    # Position 3 of IRS group = T-20250214-103 (AMBER)
    {
        "trade_id": "T-20250214-103",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 3,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-45200.00"),
        "difference_pct": Decimal("-1.85"),
        "description": "2Y USD IRS desk mark diverges from SOFR curve rebuild",
    },
    # Position 4 of IRS group = T-20250214-104 (RED)
    {
        "trade_id": "T-20250214-104",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 8,
        "escalation_level": 2,
        "assigned_to": "VC Senior Analyst",
        "difference": Decimal("-385000.00"),
        "difference_pct": Decimal("-5.42"),
        "description": "30Y GBP IRS significant mark deviation; SONIA curve shift",
    },
    # IR Futures position 8 = T-20250214-108 (AMBER)
    {
        "trade_id": "T-20250214-108",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 2,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-18750.00"),
        "difference_pct": Decimal("-1.25"),
        "description": "Eurodollar futures settlement vs exchange close timing difference",
    },
    # IR Options position 10 = T-20250214-110 (AMBER)
    {
        "trade_id": "T-20250214-110",
        "severity": "AMBER",
        "status": "INVESTIGATING",
        "days_open": 5,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-152000.00"),
        "difference_pct": Decimal("-2.15"),
        "description": "USD swaption 3Mx10Y vol surface calibration difference",
    },
    # IR Options position 11 = T-20250214-111 (RED)
    {
        "trade_id": "T-20250214-111",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 12,
        "escalation_level": 2,
        "assigned_to": "VC Senior Analyst",
        "difference": Decimal("-478500.00"),
        "difference_pct": Decimal("-6.38"),
        "description": "EUR swaption 6Mx5Y desk model uses outdated SABR params",
    },
    # Munis position 13 = T-20250214-113 (AMBER)
    {
        "trade_id": "T-20250214-113",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 4,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-62500.00"),
        "difference_pct": Decimal("-1.78"),
        "description": "NY 10Y Muni OAS spread wider than Bloomberg MUNI benchmark",
    },
    # Munis position 14 = T-20250214-114 (RED)
    {
        "trade_id": "T-20250214-114",
        "severity": "RED",
        "status": "OPEN",
        "days_open": 15,
        "escalation_level": 2,
        "assigned_to": "VC Manager",
        "difference": Decimal("-195000.00"),
        "difference_pct": Decimal("-7.85"),
        "description": "IL 7Y Muni severe mispricing; IL fiscal concerns not reflected",
    },

    # ── FX Products ──────────────────────────────────────────────
    # FX Forward position 3 = T-20250214-203 (AMBER)
    {
        "trade_id": "T-20250214-203",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 2,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-87500.00"),
        "difference_pct": Decimal("-1.55"),
        "description": "USD/JPY 1Y forward points differ from JPY OIS implied curve",
    },
    # FX Options position 7 = T-20250214-207 (AMBER)
    {
        "trade_id": "T-20250214-207",
        "severity": "AMBER",
        "status": "INVESTIGATING",
        "days_open": 6,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-72000.00"),
        "difference_pct": Decimal("-2.40"),
        "description": "USD/JPY vanilla call smile interpolation difference at 25d",
    },
    # FX Exotics position 9 = T-20250214-209 (RED)
    {
        "trade_id": "T-20250214-209",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 10,
        "escalation_level": 2,
        "assigned_to": "VC Senior Analyst",
        "difference": Decimal("-315000.00"),
        "difference_pct": Decimal("-7.50"),
        "description": "GBP/USD KI barrier desk model uses wrong barrier shift",
    },
    # FX Exotics position 10 = T-20250214-210 (RED)
    {
        "trade_id": "T-20250214-210",
        "severity": "RED",
        "status": "OPEN",
        "days_open": 14,
        "escalation_level": 2,
        "assigned_to": "VC Senior Analyst",
        "difference": Decimal("-248000.00"),
        "difference_pct": Decimal("-8.27"),
        "description": "USD/JPY DNT survival probability disputed; daily vs weekly obs",
    },
    # FX Exotics position 11 = T-20250214-211 (AMBER)
    {
        "trade_id": "T-20250214-211",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 4,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-56000.00"),
        "difference_pct": Decimal("-2.80"),
        "description": "EUR/GBP range accrual correlation assumption difference",
    },
    # FX Exotics position 12 = T-20250214-212 (RED)
    {
        "trade_id": "T-20250214-212",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 18,
        "escalation_level": 2,
        "assigned_to": "VC Manager",
        "difference": Decimal("-186000.00"),
        "difference_pct": Decimal("-9.30"),
        "description": "USD/BRL barrier desk mark uses stale EM vol; 3-week escalation",
    },

    # ── Credit / Commodity ───────────────────────────────────────
    # CDS position 2 = T-20250214-302 (AMBER)
    {
        "trade_id": "T-20250214-302",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 3,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-42000.00"),
        "difference_pct": Decimal("-2.10"),
        "description": "Tesla CDS 3Y spread wider than Markit composite by 15 bps",
    },
    # CLO position 6 = T-20250214-306 (AMBER)
    {
        "trade_id": "T-20250214-306",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 5,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-37500.00"),
        "difference_pct": Decimal("-1.50"),
        "description": "CLO AAA tranche pricing below comparable secondary trades",
    },
    # CLO position 7 = T-20250214-307 (RED)
    {
        "trade_id": "T-20250214-307",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 20,
        "escalation_level": 2,
        "assigned_to": "VC Manager",
        "difference": Decimal("-285000.00"),
        "difference_pct": Decimal("-11.40"),
        "description": "CLO BB mezz tranche model diverges from dealer consensus",
    },
    # CDO position 8 = T-20250214-308 (AMBER)
    {
        "trade_id": "T-20250214-308",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 7,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-55000.00"),
        "difference_pct": Decimal("-2.75"),
        "description": "CDO AA tranche correlation skew assumption questioned",
    },
    # CDO position 9 = T-20250214-309 (RED)
    {
        "trade_id": "T-20250214-309",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 25,
        "escalation_level": 2,
        "assigned_to": "VC Manager",
        "difference": Decimal("-420000.00"),
        "difference_pct": Decimal("-16.80"),
        "description": "CDO equity tranche severe mark dispute; L3 model divergence",
    },
    # MBS position 11 = T-20250214-311 (AMBER)
    {
        "trade_id": "T-20250214-311",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 6,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-48000.00"),
        "difference_pct": Decimal("-2.40"),
        "description": "Non-Agency MBS prepayment speed assumption differs from model",
    },
    # MBS position 12 = T-20250214-312 (RED)
    {
        "trade_id": "T-20250214-312",
        "severity": "RED",
        "status": "INVESTIGATING",
        "days_open": 22,
        "escalation_level": 2,
        "assigned_to": "VC Senior Analyst",
        "difference": Decimal("-352500.00"),
        "difference_pct": Decimal("-14.10"),
        "description": "CMBS B-piece default assumption gap; delinquency data stale",
    },
    # Commodity position 14 = T-20250214-314 (AMBER)
    {
        "trade_id": "T-20250214-314",
        "severity": "AMBER",
        "status": "OPEN",
        "days_open": 1,
        "escalation_level": 1,
        "assigned_to": "VC Analyst",
        "difference": Decimal("-22500.00"),
        "difference_pct": Decimal("-1.80"),
        "description": "NatGas swap desk uses prior-day ICE settlement; basis gap",
    },
]


# ══════════════════════════════════════════════════════════════════
# EXCEPTION COMMENT TEMPLATES (RED exceptions only)
# ══════════════════════════════════════════════════════════════════

RED_EXCEPTION_COMMENTS: dict[str, list[dict[str, Any]]] = {
    # 30Y GBP IRS
    "T-20250214-104": [
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "30Y GBP IRS desk mark deviates by -5.42% from VC rebuild using "
                "SONIA curve. The GBP 30Y point moved 12 bps on 13-Feb following "
                "BoE commentary. Desk appears to be marking off stale curve from "
                "11-Feb. Requesting trader update."
            ),
        },
        {
            "user_name": "Rates Desk Trader",
            "comment_text": (
                "Disagree with VC SONIA curve construction at 30Y. Our curve uses "
                "gilt-implied SONIA which shows less movement. The Bloomberg VCUB "
                "30Y SONIA point is unreliable for long-end. Requesting committee "
                "review of curve methodology."
            ),
        },
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "VC position: ICE Benchmark SONIA fixings are the standard reference. "
                "Gilt-implied curve introduces basis risk that should be a separate "
                "adjustment, not baked into the mark. Maintaining VC fair value. "
                "Escalated to Manager level."
            ),
        },
    ],
    # EUR Swaption 6Mx5Y
    "T-20250214-111": [
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "EUR swaption 6Mx5Y desk model uses SABR parameters calibrated "
                "on 31-Jan. VC recalibrated SABR alpha/rho to 14-Feb market. "
                "Difference of -6.38% exceeds RED threshold. The EUR normal vol "
                "surface shifted materially post-ECB meeting on 6-Feb."
            ),
        },
        {
            "user_name": "Options Desk Trader",
            "comment_text": (
                "SABR recalibration frequency is monthly per desk policy. Our "
                "parameters were approved by risk at month-end. Intra-month "
                "recalibration creates instability. We have broker quotes from "
                "BGC supporting our level."
            ),
        },
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "VC policy requires recalibration within 5 business days of a "
                "material market event. ECB meeting qualifies. BGC quote is from "
                "7-Feb (pre-data release). Current Tradeweb mid supports VC level. "
                "Exception stands, escalating to Manager."
            ),
        },
    ],
    # IL Muni 7Y
    "T-20250214-114": [
        {
            "user_name": "VC Manager",
            "comment_text": (
                "IL 7Y Muni bond shows -7.85% deviation. Illinois fiscal data "
                "released 3-Feb shows wider deficit than expected. OAS should "
                "reflect updated credit view. Desk mark appears to use pre-release "
                "spread levels. This has been open 15 days with no desk response."
            ),
        },
        {
            "user_name": "Muni Desk Trader",
            "comment_text": (
                "IL muni market is illiquid at the 7Y point. Last traded "
                "comparable was 28-Jan at a tighter spread. We are marking to "
                "the last observable trade per L2 policy."
            ),
        },
        {
            "user_name": "VC Manager",
            "comment_text": (
                "Marking to stale trades in illiquid markets does not satisfy "
                "fair value requirements. Bloomberg MUNI index for IL shows "
                "wider spreads consistent with VC level. Will present at next "
                "Valuation Committee for binding resolution."
            ),
        },
    ],
    # GBP/USD KI Barrier
    "T-20250214-209": [
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "GBP/USD KI barrier option desk model applies a 0.5% barrier "
                "shift for daily monitoring. VC model uses continuous barrier "
                "monitoring per ISDA definitions in the term sheet. This creates "
                "a 7.50% mark difference. Two dealer quotes (GS, Barclays) "
                "support the VC level."
            ),
        },
        {
            "user_name": "FX Exotics Trader",
            "comment_text": (
                "Market convention for GBP/USD barriers is discrete daily "
                "monitoring with a 50-pip shift. The term sheet language is "
                "ambiguous. Our mark is consistent with how we risk-manage "
                "the position."
            ),
        },
    ],
    # USD/JPY DNT
    "T-20250214-210": [
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "USD/JPY DNT barrier desk mark 8.27% above VC fair value. "
                "Survival probability calculation differs: desk uses weekly "
                "observation (higher survival) while VC uses daily observation "
                "per term sheet. Three dealer quotes average within 2% of VC level."
            ),
        },
        {
            "user_name": "FX Exotics Trader",
            "comment_text": (
                "We have been booking DNT barriers with weekly observation "
                "since Q3 2024. Risk management and margin calculations all "
                "use weekly. Changing to daily mid-lifecycle creates P&L noise. "
                "Requesting grandfathering."
            ),
        },
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "The term sheet signed by the counterparty specifies daily "
                "observation. Internal risk management conventions do not "
                "override contractual terms for fair value purposes. "
                "Exception maintained. Escalated to Manager."
            ),
        },
    ],
    # USD/BRL Barrier
    "T-20250214-212": [
        {
            "user_name": "VC Manager",
            "comment_text": (
                "USD/BRL barrier option has been in dispute for 18 days. "
                "Desk mark uses BRL implied vol from 27-Jan. VC model uses "
                "14-Feb vol surface which reflects significant BRL weakening. "
                "Difference of -9.30% is well into RED territory. This is the "
                "longest outstanding RED exception in the FX book."
            ),
        },
        {
            "user_name": "EM FX Trader",
            "comment_text": (
                "BRL vol surface is extremely illiquid beyond 3M. Our "
                "vol surface is constructed from NDF implied vols which are "
                "more reliable than the exchange-listed options VC uses. "
                "Client valuation also supports our level."
            ),
        },
        {
            "user_name": "VC Manager",
            "comment_text": (
                "NDF-implied vols have known funding premium that should be "
                "stripped out. VC methodology uses BGC broker composite for "
                "EM barrier vols, consistent with audit guidance. Presenting "
                "to Valuation Committee on 19-Feb with recommendation to "
                "adjust desk mark by $186k."
            ),
        },
    ],
    # CLO BB Mezz
    "T-20250214-307": [
        {
            "user_name": "VC Manager",
            "comment_text": (
                "CLO BB mezzanine tranche desk mark deviates by -11.40% "
                "from VC model. VC uses Intex cashflow model with updated "
                "CPR/CDR vectors from January trustee reports. Desk is using "
                "dealer run from 22-Jan which predates the collateral "
                "performance update."
            ),
        },
        {
            "user_name": "Credit Desk Trader",
            "comment_text": (
                "BB CLO tranches trade by appointment. Last BWIC result on "
                "24-Jan cleared at our level. Intex model assumptions are "
                "too aggressive on CDR ramp. Our CDR of 2.5% is more "
                "realistic than VC's 3.8%."
            ),
        },
        {
            "user_name": "VC Manager",
            "comment_text": (
                "The 24-Jan BWIC was for a different vintage with better "
                "collateral quality. VC CDR of 3.8% is derived from actual "
                "60+ day delinquency trends in the pool. This position has "
                "been in RED for 20 days. Committee agenda item created."
            ),
        },
    ],
    # CDO Equity Tranche
    "T-20250214-309": [
        {
            "user_name": "VC Manager",
            "comment_text": (
                "CDO equity tranche shows -16.80% mark deviation, the largest "
                "in the credit book. This is a Level 3 position with limited "
                "observable inputs. VC model uses base correlation framework "
                "with Markit tranched index data. Desk model appears to use "
                "a flat correlation assumption which overstates the tranche "
                "value."
            ),
        },
        {
            "user_name": "Structured Credit Trader",
            "comment_text": (
                "Equity tranche valuation is inherently model-dependent. "
                "Our flat correlation of 22% is the consensus from the "
                "monthly dealer survey (3 banks). VC base correlation "
                "approach gives different results but is not necessarily "
                "more accurate for bespoke tranches."
            ),
        },
        {
            "user_name": "VC Manager",
            "comment_text": (
                "Requested the 3-bank survey referenced by desk. Survey was "
                "conducted on 15-Jan using stale inputs. Current Markit index "
                "tranches imply a steeper correlation skew. This has been "
                "open 25 days. Escalating to Committee with recommendation "
                "to adopt VC methodology."
            ),
        },
    ],
    # CMBS B-piece
    "T-20250214-312": [
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "CMBS B-piece desk mark is 14.10% above VC fair value. "
                "December remittance data shows 30+ day delinquencies up "
                "180 bps in the underlying pool. Desk has not updated default "
                "assumptions since October. VC model incorporates latest "
                "servicer data."
            ),
        },
        {
            "user_name": "CMBS Desk Trader",
            "comment_text": (
                "Delinquency spike is seasonal (holiday forbearance). "
                "Historical data shows Q1 cure rates of 60-70% for this "
                "vintage. Adjusting for expected cures, our mark is "
                "justified. Servicer modification pipeline supports recovery."
            ),
        },
        {
            "user_name": "VC Senior Analyst",
            "comment_text": (
                "Even applying a 65% cure rate assumption, VC model shows "
                "the desk mark is still 9.2% rich. Cure rate data cited by "
                "desk is from 2019 vintage, not applicable to 2023 origination. "
                "Exception maintained at RED. Escalated to Manager."
            ),
        },
    ],
}


# ══════════════════════════════════════════════════════════════════
# VALUATION COMPARISON DATA FOR ALL 41 NEW POSITIONS
# ══════════════════════════════════════════════════════════════════

# Each entry: (trade_id, desk_mark, vc_fair_value, status)
# The difference and difference_pct are computed from these values.
COMPARISON_DATA: list[dict[str, Any]] = [
    # ── Rates: T-20250214-101 through T-20250214-114 ─────────────
    # 101: 10Y USD IRS 500M — GREEN
    {"trade_id": "T-20250214-101", "desk_mark": Decimal("3250000.00"), "vc_fair_value": Decimal("3235000.00"), "status": "GREEN"},
    # 102: 5Y EUR IRS 250M — GREEN
    {"trade_id": "T-20250214-102", "desk_mark": Decimal("1875000.00"), "vc_fair_value": Decimal("1868500.00"), "status": "GREEN"},
    # 103: 2Y USD IRS 100M — AMBER
    {"trade_id": "T-20250214-103", "desk_mark": Decimal("2400000.00"), "vc_fair_value": Decimal("2445200.00"), "status": "AMBER"},
    # 104: 30Y GBP IRS 150M — RED
    {"trade_id": "T-20250214-104", "desk_mark": Decimal("6720000.00"), "vc_fair_value": Decimal("7105000.00"), "status": "RED"},
    # 105: 7Y USD IRS 300M — GREEN
    {"trade_id": "T-20250214-105", "desk_mark": Decimal("2850000.00"), "vc_fair_value": Decimal("2842000.00"), "status": "GREEN"},
    # 106: 3Y EUR IRS 200M — GREEN
    {"trade_id": "T-20250214-106", "desk_mark": Decimal("1425000.00"), "vc_fair_value": Decimal("1418000.00"), "status": "GREEN"},
    # 107: UST 10Y Futures — GREEN
    {"trade_id": "T-20250214-107", "desk_mark": Decimal("110156250.00"), "vc_fair_value": Decimal("110125000.00"), "status": "GREEN"},
    # 108: Eurodollar Futures — AMBER
    {"trade_id": "T-20250214-108", "desk_mark": Decimal("1481250.00"), "vc_fair_value": Decimal("1500000.00"), "status": "AMBER"},
    # 109: UST 5Y Futures — GREEN
    {"trade_id": "T-20250214-109", "desk_mark": Decimal("54687500.00"), "vc_fair_value": Decimal("54671875.00"), "status": "GREEN"},
    # 110: USD Swaption 3Mx10Y — AMBER
    {"trade_id": "T-20250214-110", "desk_mark": Decimal("6920000.00"), "vc_fair_value": Decimal("7072000.00"), "status": "AMBER"},
    # 111: EUR Swaption 6Mx5Y — RED
    {"trade_id": "T-20250214-111", "desk_mark": Decimal("7020000.00"), "vc_fair_value": Decimal("7498500.00"), "status": "RED"},
    # 112: Cap/Floor 2Y USD — GREEN
    {"trade_id": "T-20250214-112", "desk_mark": Decimal("385000.00"), "vc_fair_value": Decimal("382500.00"), "status": "GREEN"},
    # 113: NY Muni 10Y — AMBER
    {"trade_id": "T-20250214-113", "desk_mark": Decimal("3450000.00"), "vc_fair_value": Decimal("3512500.00"), "status": "AMBER"},
    # 114: IL Muni 7Y — RED
    {"trade_id": "T-20250214-114", "desk_mark": Decimal("2290000.00"), "vc_fair_value": Decimal("2485000.00"), "status": "RED"},

    # ── FX Products: T-20250214-201 through T-20250214-212 ───────
    # 201: EUR/USD 6M FWD 200M — GREEN
    {"trade_id": "T-20250214-201", "desk_mark": Decimal("216400000.00"), "vc_fair_value": Decimal("216320000.00"), "status": "GREEN"},
    # 202: GBP/USD 3M FWD 100M — GREEN
    {"trade_id": "T-20250214-202", "desk_mark": Decimal("126580000.00"), "vc_fair_value": Decimal("126545000.00"), "status": "GREEN"},
    # 203: USD/JPY 1Y FWD 75M — AMBER
    {"trade_id": "T-20250214-203", "desk_mark": Decimal("5550000.00"), "vc_fair_value": Decimal("5637500.00"), "status": "AMBER"},
    # 204: USD/MXN 6M FWD 50M — GREEN
    {"trade_id": "T-20250214-204", "desk_mark": Decimal("865000.00"), "vc_fair_value": Decimal("858500.00"), "status": "GREEN"},
    # 205: EUR/USD Vanilla Call 150M — GREEN
    {"trade_id": "T-20250214-205", "desk_mark": Decimal("2850000.00"), "vc_fair_value": Decimal("2835000.00"), "status": "GREEN"},
    # 206: GBP/USD Vanilla Put 80M — GREEN
    {"trade_id": "T-20250214-206", "desk_mark": Decimal("1520000.00"), "vc_fair_value": Decimal("1512000.00"), "status": "GREEN"},
    # 207: USD/JPY Vanilla Call 60M — AMBER
    {"trade_id": "T-20250214-207", "desk_mark": Decimal("2928000.00"), "vc_fair_value": Decimal("3000000.00"), "status": "AMBER"},
    # 208: EUR/USD KO Barrier 100M — GREEN
    {"trade_id": "T-20250214-208", "desk_mark": Decimal("1850000.00"), "vc_fair_value": Decimal("1838000.00"), "status": "GREEN"},
    # 209: GBP/USD KI Barrier 70M — RED
    {"trade_id": "T-20250214-209", "desk_mark": Decimal("3885000.00"), "vc_fair_value": Decimal("4200000.00"), "status": "RED"},
    # 210: USD/JPY DNT 50M — RED
    {"trade_id": "T-20250214-210", "desk_mark": Decimal("2752000.00"), "vc_fair_value": Decimal("3000000.00"), "status": "RED"},
    # 211: EUR/GBP Range Accrual 40M — AMBER
    {"trade_id": "T-20250214-211", "desk_mark": Decimal("1944000.00"), "vc_fair_value": Decimal("2000000.00"), "status": "AMBER"},
    # 212: USD/BRL Barrier 30M — RED
    {"trade_id": "T-20250214-212", "desk_mark": Decimal("1814000.00"), "vc_fair_value": Decimal("2000000.00"), "status": "RED"},

    # ── Credit / Commodity: T-20250214-301 through T-20250214-315 ─
    # 301: CDS Ford 5Y 25M — GREEN
    {"trade_id": "T-20250214-301", "desk_mark": Decimal("462500.00"), "vc_fair_value": Decimal("458000.00"), "status": "GREEN"},
    # 302: CDS Tesla 3Y 15M — AMBER
    {"trade_id": "T-20250214-302", "desk_mark": Decimal("1958000.00"), "vc_fair_value": Decimal("2000000.00"), "status": "AMBER"},
    # 303: CDS Brazil 5Y 20M — GREEN
    {"trade_id": "T-20250214-303", "desk_mark": Decimal("330000.00"), "vc_fair_value": Decimal("326500.00"), "status": "GREEN"},
    # 304: CDS DeutscheBank 5Y 10M — GREEN
    {"trade_id": "T-20250214-304", "desk_mark": Decimal("95000.00"), "vc_fair_value": Decimal("93500.00"), "status": "GREEN"},
    # 305: CDS IG Index 5Y 50M — GREEN
    {"trade_id": "T-20250214-305", "desk_mark": Decimal("375000.00"), "vc_fair_value": Decimal("372500.00"), "status": "GREEN"},
    # 306: CLO AAA 30M — AMBER
    {"trade_id": "T-20250214-306", "desk_mark": Decimal("2462500.00"), "vc_fair_value": Decimal("2500000.00"), "status": "AMBER"},
    # 307: CLO BB Mezz 20M — RED
    {"trade_id": "T-20250214-307", "desk_mark": Decimal("2215000.00"), "vc_fair_value": Decimal("2500000.00"), "status": "RED"},
    # 308: CDO AA 25M — AMBER
    {"trade_id": "T-20250214-308", "desk_mark": Decimal("1945000.00"), "vc_fair_value": Decimal("2000000.00"), "status": "AMBER"},
    # 309: CDO Equity 10M — RED
    {"trade_id": "T-20250214-309", "desk_mark": Decimal("2080000.00"), "vc_fair_value": Decimal("2500000.00"), "status": "RED"},
    # 310: Agency MBS 40M — GREEN
    {"trade_id": "T-20250214-310", "desk_mark": Decimal("38500000.00"), "vc_fair_value": Decimal("38420000.00"), "status": "GREEN"},
    # 311: Non-Agency MBS 20M — AMBER
    {"trade_id": "T-20250214-311", "desk_mark": Decimal("1952000.00"), "vc_fair_value": Decimal("2000000.00"), "status": "AMBER"},
    # 312: CMBS B-piece 15M — RED
    {"trade_id": "T-20250214-312", "desk_mark": Decimal("2147500.00"), "vc_fair_value": Decimal("2500000.00"), "status": "RED"},
    # 313: WTI Crude Swap 35M — GREEN
    {"trade_id": "T-20250214-313", "desk_mark": Decimal("2695000.00"), "vc_fair_value": Decimal("2688000.00"), "status": "GREEN"},
    # 314: NatGas Swap 20M — AMBER
    {"trade_id": "T-20250214-314", "desk_mark": Decimal("1227500.00"), "vc_fair_value": Decimal("1250000.00"), "status": "AMBER"},
    # 315: Gold Forward 25M — GREEN
    {"trade_id": "T-20250214-315", "desk_mark": Decimal("25062500.00"), "vc_fair_value": Decimal("25037500.00"), "status": "GREEN"},
]


# ══════════════════════════════════════════════════════════════════
# HELPER: Look up positions by trade_id
# ══════════════════════════════════════════════════════════════════


async def _get_position_map(db: AsyncSession, trade_ids: list[str]) -> dict[str, Position]:
    """Return a {trade_id: Position} mapping for the requested trade_ids."""
    result = await db.execute(
        select(Position).where(Position.trade_id.in_(trade_ids))
    )
    positions = list(result.scalars().all())
    return {p.trade_id: p for p in positions}


# ══════════════════════════════════════════════════════════════════
# SEEDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════


async def seed_xva_adjustments(db: AsyncSession) -> dict:
    """Update ``fva_usd`` on all OTC derivative positions with net XVA.

    Net XVA = CVA + FVA - DVA, stored as the ``fva_usd`` column on each
    Position row.  The function queries positions by trade_id to get the
    actual position_ids, then issues UPDATE statements.

    Returns a summary dict with counts and total XVA impact.
    """
    all_trade_ids = list(XVA_ADJUSTMENTS.keys())
    pos_map = await _get_position_map(db, all_trade_ids)

    updated_count = 0
    total_xva = Decimal("0.00")
    details: list[dict[str, Any]] = []

    for trade_id, params in XVA_ADJUSTMENTS.items():
        pos = pos_map.get(trade_id)
        if pos is None:
            logger.warning("Position %s not found for XVA update, skipping", trade_id)
            continue

        net_xva = _compute_net_xva(params)

        await db.execute(
            update(Position)
            .where(Position.position_id == pos.position_id)
            .values(fva_usd=net_xva)
        )
        updated_count += 1
        total_xva += net_xva

        details.append({
            "trade_id": trade_id,
            "position_id": pos.position_id,
            "cva_bps": params["cva_bps"],
            "fva_bps": params["fva_bps"],
            "dva_bps": params["dva_bps"],
            "net_xva_usd": float(net_xva),
        })

    if updated_count:
        await db.flush()
        logger.info(
            "Updated fva_usd on %d positions; total net XVA = $%s",
            updated_count, total_xva,
        )

    return {
        "positions_updated": updated_count,
        "total_net_xva_usd": float(total_xva),
        "details": details,
    }


async def seed_new_market_data(db: AsyncSession) -> list:
    """Create market data snapshots for yield curves, CDS spreads, commodity
    prices, treasury yields, and muni yields.

    Returns the list of created ``MarketDataSnapshot`` objects.
    """
    all_data = (
        YIELD_CURVE_DATA
        + CDS_SPREAD_DATA
        + COMMODITY_DATA
        + TREASURY_DATA
        + MUNI_DATA
    )

    created: list[MarketDataSnapshot] = []

    for source, field_name, value in all_data:
        # Idempotency check
        existing = await db.execute(
            select(MarketDataSnapshot).where(
                MarketDataSnapshot.valuation_date == VALUATION_DATE,
                MarketDataSnapshot.field_name == field_name,
                MarketDataSnapshot.data_source == source,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        snapshot = MarketDataSnapshot(
            valuation_date=VALUATION_DATE,
            data_source=source,
            field_name=field_name,
            field_value=Decimal(value),
        )
        db.add(snapshot)
        created.append(snapshot)

    if created:
        await db.flush()
        logger.info("Seeded %d new market data snapshots", len(created))

    return created


async def seed_new_exceptions(db: AsyncSession) -> tuple[list, list]:
    """Create exception records for all AMBER/RED positions and dispute
    comments for RED exceptions.

    Returns a tuple of (exceptions_list, comments_list).
    """
    # Gather all trade_ids referenced in exception definitions
    exc_trade_ids = [exc_def["trade_id"] for exc_def in EXCEPTION_DEFINITIONS]
    pos_map = await _get_position_map(db, exc_trade_ids)

    created_exceptions: list[VCException] = []
    created_comments: list[ExceptionComment] = []

    for exc_def in EXCEPTION_DEFINITIONS:
        trade_id = exc_def["trade_id"]
        pos = pos_map.get(trade_id)
        if pos is None:
            logger.warning(
                "Position %s not found for exception creation, skipping", trade_id
            )
            continue

        # Idempotency: skip if an open/investigating exception already exists
        existing = await db.execute(
            select(VCException).where(
                VCException.position_id == pos.position_id,
                VCException.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"]),
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info(
                "Exception for position %s (%s) already exists, skipping",
                pos.position_id, trade_id,
            )
            continue

        exc = VCException(
            position_id=pos.position_id,
            difference=exc_def["difference"],
            difference_pct=exc_def["difference_pct"],
            status=exc_def["status"],
            severity=exc_def["severity"],
            created_date=VALUATION_DATE - timedelta(days=exc_def["days_open"]),
            assigned_to=exc_def["assigned_to"],
            days_open=exc_def["days_open"],
            escalation_level=exc_def["escalation_level"],
        )
        db.add(exc)
        await db.flush()  # assign PK
        created_exceptions.append(exc)

        # Add comments for RED exceptions
        if exc_def["severity"] == "RED" and trade_id in RED_EXCEPTION_COMMENTS:
            comment_defs = RED_EXCEPTION_COMMENTS[trade_id]
            for c_def in comment_defs:
                comment = ExceptionComment(
                    exception_id=exc.exception_id,
                    user_name=c_def["user_name"],
                    comment_text=c_def["comment_text"],
                    attachments=c_def.get("attachments"),
                )
                db.add(comment)
                created_comments.append(comment)

    if created_exceptions or created_comments:
        await db.flush()
        logger.info(
            "Seeded %d exceptions and %d comments",
            len(created_exceptions), len(created_comments),
        )

    return created_exceptions, created_comments


async def seed_new_comparisons(db: AsyncSession) -> list:
    """Create valuation comparison records for all 41 new positions.

    Computes difference and difference_pct from desk_mark and vc_fair_value.

    Returns the list of created ``ValuationComparison`` objects.
    """
    comp_trade_ids = [c["trade_id"] for c in COMPARISON_DATA]
    pos_map = await _get_position_map(db, comp_trade_ids)

    created: list[ValuationComparison] = []

    for comp_def in COMPARISON_DATA:
        trade_id = comp_def["trade_id"]
        pos = pos_map.get(trade_id)
        if pos is None:
            logger.warning(
                "Position %s not found for comparison creation, skipping", trade_id
            )
            continue

        # Idempotency
        existing = await db.execute(
            select(ValuationComparison).where(
                ValuationComparison.position_id == pos.position_id,
                ValuationComparison.comparison_date == VALUATION_DATE,
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue

        desk_mark = comp_def["desk_mark"]
        vc_fair_value = comp_def["vc_fair_value"]
        diff = desk_mark - vc_fair_value

        if vc_fair_value != Decimal("0"):
            diff_pct = (diff / abs(vc_fair_value) * 100).quantize(Decimal("0.01"))
        else:
            diff_pct = Decimal("0.00")

        comp = ValuationComparison(
            position_id=pos.position_id,
            desk_mark=desk_mark,
            vc_fair_value=vc_fair_value,
            difference=diff,
            difference_pct=diff_pct,
            status=comp_def["status"],
            comparison_date=VALUATION_DATE,
        )
        db.add(comp)
        created.append(comp)

    if created:
        await db.flush()
        logger.info("Seeded %d valuation comparisons for new positions", len(created))

    return created

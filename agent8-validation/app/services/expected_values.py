"""
Expected values extracted from the FX IPV Model Excel.
These are the ground truth for validation.

Every constant in this module corresponds to a cell, range, or computed
value in the master workbook.  Validators compare agent outputs against
these values to ensure the multi-agent system reproduces the Excel model
faithfully.
"""

from typing import Any

# ==========================================
# POSITIONS (from Positions sheet)
# ==========================================
EXPECTED_POSITIONS: list[dict[str, Any]] = [
    {
        "position_id": "FX-SPOT-001",
        "currency_pair": "EUR/USD",
        "product_type": "Spot",
        "notional_usd": 150_000_000,
        "desk_mark": 1.0825,
        "ipv_price": 1.0823,
        "pct_diff": 0.018,
        "rag_status": "GREEN",
        "fv_level": "L1",
        "fva_usd": -300,
        "book_value_usd": 162_375_000,
    },
    {
        "position_id": "FX-SPOT-002",
        "currency_pair": "GBP/USD",
        "product_type": "Spot",
        "notional_usd": 85_000_000,
        "desk_mark": 1.2648,
        "ipv_price": 1.2645,
        "pct_diff": 0.024,
        "rag_status": "GREEN",
        "fv_level": "L1",
        "fva_usd": -255,
        "book_value_usd": 107_508_000,
    },
    {
        "position_id": "FX-SPOT-003",
        "currency_pair": "USD/JPY",
        "product_type": "Spot",
        "notional_usd": 50_000_000,
        "desk_mark": 149.85,
        "ipv_price": 149.88,
        "pct_diff": -0.02,
        "rag_status": "GREEN",
        "fv_level": "L1",
        "fva_usd": 100,
        "book_value_usd": 50_000_000,
    },
    {
        "position_id": "FX-SPOT-004",
        "currency_pair": "USD/TRY",
        "product_type": "Spot",
        "notional_usd": 25_000_000,
        "desk_mark": 32.45,
        "ipv_price": 35.12,
        "pct_diff": -8.22,
        "rag_status": "RED",
        "fv_level": "L2",
        "fva_usd": -18_500,
        "book_value_usd": 25_000_000,
    },
    {
        "position_id": "FX-SPOT-005",
        "currency_pair": "USD/BRL",
        "product_type": "Spot",
        "notional_usd": 10_000_000,
        "desk_mark": 5.12,
        "ipv_price": 5.18,
        "pct_diff": -1.17,
        "rag_status": "AMBER",
        "fv_level": "L2",
        "fva_usd": -1_160,
        "book_value_usd": 10_000_000,
    },
    {
        "position_id": "FX-FWD-001",
        "currency_pair": "EUR/USD",
        "product_type": "Forward",
        "notional_usd": 120_000_000,
        "desk_mark": 1.095,
        "ipv_price": 1.0948,
        "pct_diff": 0.018,
        "rag_status": "GREEN",
        "fv_level": "L2",
        "fva_usd": -240,
        "book_value_usd": 131_400_000,
    },
    {
        "position_id": "FX-OPT-001",
        "currency_pair": "EUR/USD",
        "product_type": "Barrier",
        "notional_usd": 50_000_000,
        "desk_mark": 425_000,
        "ipv_price": 425_000,
        "pct_diff": 0.0,
        "rag_status": "RED",
        "fv_level": "L3",
        "fva_usd": 0,
        "book_value_usd": 850_000,
    },
]

# ==========================================
# TOLERANCE THRESHOLDS (from Assumptions sheet)
# ==========================================
EXPECTED_THRESHOLDS: dict[str, dict[str, float]] = {
    "G10_SPOT": {"green_max_bps": 5, "amber_max_bps": 10},
    "EM_SPOT": {"green_max_pct": 2.0, "amber_max_pct": 5.0},
    "FX_FORWARDS": {"green_max_bps": 10, "amber_max_bps": 20},
    "FX_OPTIONS": {"green_max_pct": 5.0, "amber_max_pct": 10.0},
}

# ==========================================
# SUMMARY METRICS (from Summary_Dashboard)
# ==========================================
EXPECTED_SUMMARY: dict[str, Any] = {
    "total_notional_usd": 485_750_000,
    "total_book_value_usd": 2_847_250,
    "total_ipv_breaches": {"red": 2, "amber": 1, "green": 4},
    "total_fva": -47_820,
    "total_ava": 89_450,
    "largest_position": "EUR/USD Spot ($150m notional)",
    "largest_breach": "USD/TRY Spot (-8.2%)",
    "level_3_exposure": 850_000,
}

# ==========================================
# FV HIERARCHY (from FV_Hierarchy sheet)
# ==========================================
EXPECTED_FV_HIERARCHY: dict[str, dict[str, Any]] = {
    "L1": {"count": 3, "book_value": 319_762_250},
    "L2": {"count": 3, "book_value": 166_376_000},
    "L3": {"count": 1, "book_value": 850_000},
}

# ==========================================
# MODEL RESERVE (from Model_Reserve sheet)
# ==========================================
EXPECTED_MODEL_RESERVES: dict[str, Any] = {
    "FX-SPOT-001": {"reserve": 0, "materiality": "ZERO"},
    "FX-SPOT-002": {"reserve": 0, "materiality": "ZERO"},
    "FX-SPOT-003": {"reserve": 0, "materiality": "ZERO"},
    "FX-SPOT-004": {"reserve": 3_000, "materiality": "IMMATERIAL"},
    "FX-SPOT-005": {"reserve": 200, "materiality": "IMMATERIAL"},
    "FX-FWD-001": {"reserve": 1_200, "materiality": "IMMATERIAL"},
    "FX-OPT-001": {"reserve": 42_500, "materiality": "MATERIAL"},
    "total": 46_900,
}

# ==========================================
# AVA CALCULATION (from AVA_Calculation sheet)
# ==========================================
EXPECTED_AVA_BARRIER: dict[str, Any] = {
    "position_id": "FX-OPT-001",
    "components": {
        "mpu": 8_500,
        "close_out": 4_250,
        "model_risk": 21_250,
        "credit_spreads": 0,
        "funding": 0,
        "concentration": 0,
        "admin": 425,
    },
    "total_ava": 34_425,
    "dealer_quotes": {
        "JPM": 305_000,
        "GS": 308_000,
        "Citi": 302_000,
    },
}

# ==========================================
# DAY 1 PnL (from Day1_PnL sheet)
# ==========================================
EXPECTED_DAY1_PNL: dict[str, Any] = {
    "position_id": "FX-OPT-001",
    "transaction_price": 425_000,
    "fair_value": 306_000,
    "day1_pnl": 119_000,
    "recognition": "DEFERRED",
    "amortization_monthly": 10_455,
    "amortization_months": 11,
    "amortization_daily": 371.88,
}

# ==========================================
# FVA (from FVA sheet)
# ==========================================
EXPECTED_FVA_BARRIER: dict[str, Any] = {
    "position_id": "FX-OPT-001",
    "premium": 425_000,
    "fair_value": 310_000,
    "fva_amount": 115_000,
    "monthly_release": 10_455,
    "total_months": 11,
}

EXPECTED_TOTAL_FVA: float = -20_355  # from IPV_Tolerance_Check sheet total

# ==========================================
# BARRIER OPTION PRICING (from Barrier_Pricing_Methods)
# ==========================================
EXPECTED_BARRIER_PRICING: dict[str, Any] = {
    "analytical_survival": 0.7208,
    "monte_carlo_survival": 0.7198,
    "pde_survival": 0.7215,
    "bloomberg_ovml": 0.7205,
    "consensus_survival": 0.7207,
    "fair_value": 306_298,
    "tolerance_pct": 0.5,  # Methods within 0.5% of each other
}

# ==========================================
# GREEKS (from Greeks_PnL_Attribution sheet)
# ==========================================
EXPECTED_GREEKS_BARRIER: dict[str, Any] = {
    "delta_per_pip": 1_500_000,
    "gamma_near_barrier": "HIGH",
    "vega_per_1pct": 500_000,
    "theta_daily": -900,
}

# ==========================================
# CAPITAL ADEQUACY (from Capital_Adequacy sheet)
# ==========================================
EXPECTED_CAPITAL: dict[str, Any] = {
    "shareholders_equity": 50_000_000,
    "retained_earnings": 25_000_000,
    "aoci": 2_000_000,
    "goodwill_deduction": -5_000_000,
    "dta_deduction": -1_000_000,
    "ava_deduction": -34_425,  # from AVA calc
    "other_deductions": -500_000,
    "cet1_capital": 70_465_575,
    "credit_risk_rwa": 225_000_000,
    "market_risk_rwa": 42_360_000,
    "operational_risk_rwa": 30_000_000,
    "total_rwa": 297_360_000,
    "cet1_ratio_min": 0.045,
    "ccb_min": 0.070,
}


# ── Helper look-ups ─────────────────────────────────────────────────

def get_expected_position(position_id: str) -> dict[str, Any] | None:
    """Return the expected position dict for a given position_id, or None."""
    for pos in EXPECTED_POSITIONS:
        if pos["position_id"] == position_id:
            return pos
    return None


def get_expected_reserve(position_id: str) -> dict[str, Any] | None:
    """Return the expected model reserve for a given position_id, or None."""
    entry = EXPECTED_MODEL_RESERVES.get(position_id)
    if isinstance(entry, dict):
        return entry
    return None


def total_expected_notional() -> int:
    """Sum all expected position notionals."""
    return sum(p["notional_usd"] for p in EXPECTED_POSITIONS)


def total_expected_book_value() -> int:
    """Sum all expected position book values."""
    return sum(p["book_value_usd"] for p in EXPECTED_POSITIONS)


def count_by_rag(status: str) -> int:
    """Count expected positions with a given RAG status."""
    return sum(1 for p in EXPECTED_POSITIONS if p["rag_status"] == status)


def count_by_fv_level(level: str) -> int:
    """Count expected positions with a given FV level."""
    return sum(1 for p in EXPECTED_POSITIONS if p["fv_level"] == level)

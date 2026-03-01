"""Data quality monitoring service.

Computes freshness, validation failure counts, cross-validation alerts,
and data gap metrics for the VC dashboard.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import List, Optional

import structlog

from app.core.config import settings
from app.core.database import get_mongo
from app.models.schemas import DataQualityMetric, DataQualitySummary

log = structlog.get_logger()

# The field names we expect to see daily (FX book)
EXPECTED_FIELDS: List[str] = [
    # Spot rates (WM/Reuters 4pm Fix)
    "EUR/USD_Spot", "GBP/USD_Spot", "USD/JPY_Spot", "USD/TRY_Spot", "USD/BRL_Spot",
    # Bid/Ask for spread monitoring
    "EUR/USD_Bid", "EUR/USD_Ask",
    "GBP/USD_Bid", "GBP/USD_Ask",
    "USD/JPY_Bid", "USD/JPY_Ask",
    "USD/TRY_Bid", "USD/TRY_Ask",
    "USD/BRL_Bid", "USD/BRL_Ask",
    # Forward points (Bloomberg FXFA)
    "EUR/USD_1M_FWD", "EUR/USD_3M_FWD", "EUR/USD_6M_FWD", "EUR/USD_1Y_FWD",
    # Interest rates
    "EUR_Rate_1Y", "USD_Rate_1Y",
    # Vol surface (Bloomberg OVML)
    "EUR/USD_1Y_ATM_Vol", "EUR/USD_1Y_25D_RR", "EUR/USD_1Y_25D_BF",
]

EXPECTED_VOL_PAIRS = ["EUR/USD"]
EXPECTED_VOL_TENORS = ["1M", "3M", "6M", "1Y"]


async def compute_quality_summary(
    valuation_date: Optional[date] = None,
) -> DataQualitySummary:
    as_of = valuation_date or date.today()
    db = get_mongo()
    metrics: List[DataQualityMetric] = []

    # ── 1. Data freshness ─────────────────────────────────────────
    cutoff = datetime.utcnow() - timedelta(hours=settings.data_stale_threshold_hours)
    fresh_count = await db["market_data_history"].count_documents(
        {"timestamp": {"$gte": cutoff}}
    )
    total_expected = len(EXPECTED_FIELDS)
    freshness_pct = (fresh_count / total_expected * 100) if total_expected else 100.0

    freshness_status = "OK"
    if freshness_pct < 90:
        freshness_status = "CRITICAL"
    elif freshness_pct < 95:
        freshness_status = "WARNING"

    metrics.append(
        DataQualityMetric(
            metric="data_freshness",
            value=round(freshness_pct, 1),
            status=freshness_status,
            detail=f"{fresh_count}/{total_expected} fields updated in last {settings.data_stale_threshold_hours}h",
        )
    )

    # ── 2. Data gaps (missing expected fields for today) ──────────
    start_of_day = datetime.combine(as_of, datetime.min.time())
    end_of_day = start_of_day + timedelta(days=1)

    present_fields_list = await db["market_data_history"].distinct(
        "field", {"date": {"$gte": start_of_day, "$lt": end_of_day}}
    )
    present_fields = set(present_fields_list)
    missing_fields = set(EXPECTED_FIELDS) - present_fields
    data_gaps = len(missing_fields)

    gap_status = "OK"
    if data_gaps > 5:
        gap_status = "CRITICAL"
    elif data_gaps > 0:
        gap_status = "WARNING"

    metrics.append(
        DataQualityMetric(
            metric="data_gaps",
            value=float(data_gaps),
            status=gap_status,
            detail=f"Missing: {', '.join(sorted(missing_fields)[:5])}" if missing_fields else "All fields present",
        )
    )

    # ── 3. Vol surface coverage ───────────────────────────────────
    vol_present = await db["vol_surface_history"].count_documents(
        {"date": {"$gte": start_of_day, "$lt": end_of_day}}
    )
    expected_vol_points = len(EXPECTED_VOL_PAIRS) * len(EXPECTED_VOL_TENORS) * 3  # 3 deltas
    vol_coverage = (vol_present / expected_vol_points * 100) if expected_vol_points else 100.0

    vol_status = "OK" if vol_coverage >= 90 else ("CRITICAL" if vol_coverage < 50 else "WARNING")
    metrics.append(
        DataQualityMetric(
            metric="vol_surface_coverage",
            value=round(vol_coverage, 1),
            status=vol_status,
            detail=f"{vol_present}/{expected_vol_points} vol surface points",
        )
    )

    # ── 4. Source availability ────────────────────────────────────
    for source in ("Bloomberg", "Reuters", "Mock"):
        src_count = await db["market_data_history"].count_documents(
            {"source": source, "timestamp": {"$gte": cutoff}}
        )
        src_status = "OK" if src_count > 0 else "WARNING"
        metrics.append(
            DataQualityMetric(
                metric=f"source_availability_{source.lower()}",
                value=float(src_count),
                status=src_status,
                detail=f"{src_count} records from {source} in last {settings.data_stale_threshold_hours}h",
            )
        )

    # ── Aggregate ─────────────────────────────────────────────────
    validation_failures = sum(1 for m in metrics if m.status == "CRITICAL")
    cross_validation_alerts = sum(
        1 for m in metrics if m.status == "WARNING" and "cross" in m.metric
    )

    return DataQualitySummary(
        valuation_date=as_of,
        freshness_pct=round(freshness_pct, 1),
        validation_failures=validation_failures,
        cross_validation_alerts=cross_validation_alerts,
        data_gaps=data_gaps,
        metrics=metrics,
    )

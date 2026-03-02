"""API endpoints for Day 1 P&L Red Flag detection."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.red_flag_detector import Day1RedFlagDetector

router = APIRouter(prefix="/red-flags", tags=["red-flags"])


class RedFlagAssessmentRequest(BaseModel):
    """Request body for red flag assessment."""
    position_id: str
    transaction_price: float
    fair_value: float
    fair_value_level: str = "L2"
    product_type: str = "Spot"
    num_dealer_quotes: int = 0
    has_bloomberg_pricing: bool = True
    desk_has_proprietary_data: bool = False
    client_type: str = "institutional"
    trade_date: Optional[date] = None
    remark_count: int = 0
    period_end_trade_count: int = 0
    model_comparison_values: Optional[list[float]] = None


@router.post("/assess")
async def assess_red_flags(request: RedFlagAssessmentRequest) -> dict:
    """Run all 6 red flag checks against a position.

    Implements the Day1_PnL_RedFlags sheet from the FX IPV Model:
    1. Client Overpaid for Derivative
    2. No Observable Market for Product
    3. Bank Has Information Advantage
    4. Earnings Manipulation Risk
    5. Volume Spike at Period End
    6. Frequent Re-marks
    """
    detector = Day1RedFlagDetector()
    report = detector.assess_position(
        position_id=request.position_id,
        transaction_price=request.transaction_price,
        fair_value=request.fair_value,
        fair_value_level=request.fair_value_level,
        product_type=request.product_type,
        num_dealer_quotes=request.num_dealer_quotes,
        has_bloomberg_pricing=request.has_bloomberg_pricing,
        desk_has_proprietary_data=request.desk_has_proprietary_data,
        client_type=request.client_type,
        trade_date=request.trade_date,
        remark_count=request.remark_count,
        period_end_trade_count=request.period_end_trade_count,
        model_comparison_values=request.model_comparison_values,
    )
    return report.to_dict()


@router.post("/assess/barrier-example")
async def assess_barrier_option_example() -> dict:
    """Run red flag assessment for the EUR/USD barrier option from the Excel model.

    Pre-configured with:
    - Transaction Price: $425,000
    - Fair Value: $306,000
    - Day 1 P&L: +$119,000 (38.9% overpayment)
    - Level 3
    - 3 dealer quotes
    """
    detector = Day1RedFlagDetector()
    report = detector.assess_barrier_option_example()
    return report.to_dict()


@router.get("/thresholds")
async def get_red_flag_thresholds() -> dict:
    """Get the current red flag detection thresholds."""
    return {
        "overpayment_severe_pct": Day1RedFlagDetector.OVERPAYMENT_SEVERE_PCT,
        "overpayment_high_pct": Day1RedFlagDetector.OVERPAYMENT_HIGH_PCT,
        "overpayment_medium_pct": Day1RedFlagDetector.OVERPAYMENT_MEDIUM_PCT,
        "min_dealer_quotes": Day1RedFlagDetector.MIN_DEALER_QUOTES,
        "period_end_window_days": Day1RedFlagDetector.PERIOD_END_WINDOW_DAYS,
        "remark_threshold": Day1RedFlagDetector.REMARK_THRESHOLD,
        "red_flag_categories": [
            {"number": 1, "name": "Client Overpaid", "severity_levels": ["SEVERE >20%", "HIGH >10%", "MEDIUM >5%"]},
            {"number": 2, "name": "No Observable Market", "severity_levels": ["SEVERE: 0 quotes", "HIGH: L3", "MEDIUM: <3 quotes"]},
            {"number": 3, "name": "Information Advantage", "severity_levels": ["SEVERE: proprietary data", "HIGH: L3 + dependent client"]},
            {"number": 4, "name": "Earnings Manipulation", "severity_levels": ["SEVERE: large gain recognized", "HIGH: quarter-end timing"]},
            {"number": 5, "name": "Volume Spike", "severity_levels": ["HIGH: >5 period-end trades", "MEDIUM: >10 total"]},
            {"number": 6, "name": "Frequent Re-marks", "severity_levels": ["HIGH: >=5 re-marks", "MEDIUM: >=3 re-marks"]},
        ],
    }

"""Tests for Pydantic schemas."""

from datetime import date, datetime
from decimal import Decimal

from app.models.schemas import (
    PositionCreate,
    PositionOut,
    MarketDataSnapshotCreate,
    DealerQuoteCreate,
)


def test_position_create():
    p = PositionCreate(
        trade_id="T-001",
        product_type="IRS",
        asset_class="Rates",
        notional=Decimal("1000000"),
        currency="USD",
        trade_date=date(2024, 6, 1),
        maturity_date=date(2029, 6, 1),
    )
    assert p.trade_id == "T-001"
    assert p.notional == Decimal("1000000")


def test_position_out_from_attributes():
    data = {
        "position_id": 1,
        "trade_id": "T-001",
        "product_type": "IRS",
        "asset_class": "Rates",
        "notional": Decimal("1000000"),
        "currency": "USD",
        "trade_date": date(2024, 6, 1),
        "maturity_date": date(2029, 6, 1),
        "counterparty": "ACME",
        "desk_mark": Decimal("15000"),
        "vc_fair_value": Decimal("14800"),
        "difference": Decimal("200"),
        "difference_pct": Decimal("1.35"),
        "exception_status": "GREEN",
        "valuation_date": date(2025, 2, 14),
        "created_at": datetime(2025, 2, 14, 12, 0),
        "updated_at": datetime(2025, 2, 14, 12, 0),
    }
    p = PositionOut(**data)
    assert p.position_id == 1
    assert p.difference == Decimal("200")


def test_market_data_snapshot_create():
    s = MarketDataSnapshotCreate(
        valuation_date=date(2025, 2, 14),
        data_source="Bloomberg",
        field_name="EUR/USD_Spot",
        field_value=Decimal("1.08230000"),
    )
    assert s.field_name == "EUR/USD_Spot"


def test_dealer_quote_create():
    q = DealerQuoteCreate(
        position_id=1,
        dealer_name="JPM",
        quote_value=Decimal("15100"),
        quote_date=date(2025, 2, 14),
        quote_type="Mid",
    )
    assert q.dealer_name == "JPM"

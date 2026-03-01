"""Tests for Agent 5 reserve calculators."""

from __future__ import annotations

import pytest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.models.schemas import (
    AVAComponents,
    DealerQuoteInput,
    ModelComparisonEntry,
    PositionInput,
)
from app.services.fva import calculate_fva
from app.services.ava import (
    _calculate_mpu,
    _calculate_close_out,
    _calculate_model_risk,
    _calculate_funding,
    _calculate_admin,
    _calculate_credit_spreads,
    _calculate_concentration,
    calculate_ava,
)
from app.services.model_reserve import calculate_model_reserve
from app.services.day1_pnl import calculate_day1_pnl


# ── Fixtures ─────────────────────────────────────────────────────

def _make_position(**overrides) -> PositionInput:
    defaults = dict(
        position_id=1,
        trade_id="T-001",
        product_type="IRS",
        asset_class="Rates",
        notional=Decimal("10000000"),
        currency="USD",
        trade_date=date.today() - timedelta(days=30),
        maturity_date=date.today() + timedelta(days=365),
        desk_mark=Decimal("1050000"),
        vc_fair_value=Decimal("1000000"),
        classification="Level2",
        position_direction="LONG",
        transaction_price=Decimal("1020000"),
    )
    defaults.update(overrides)
    return PositionInput(**defaults)


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# ═══════════════════════════════════════════════════════════════════
# FVA Tests
# ═══════════════════════════════════════════════════════════════════

class TestFVA:
    @pytest.mark.asyncio
    async def test_fva_vc_less_than_desk(self):
        db = _mock_db()
        pos = _make_position(desk_mark=Decimal("1050000"), vc_fair_value=Decimal("1000000"))
        result = await calculate_fva(db, pos)

        assert result.fva_amount == Decimal("50000")
        assert "VC FV" in result.rationale
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_fva_vc_equal_desk(self):
        db = _mock_db()
        pos = _make_position(desk_mark=Decimal("1000000"), vc_fair_value=Decimal("1000000"))
        result = await calculate_fva(db, pos)

        assert result.fva_amount == Decimal("0")
        assert "No FVA required" in result.rationale

    @pytest.mark.asyncio
    async def test_fva_vc_greater_than_desk(self):
        db = _mock_db()
        pos = _make_position(desk_mark=Decimal("1000000"), vc_fair_value=Decimal("1050000"))
        result = await calculate_fva(db, pos)

        assert result.fva_amount == Decimal("0")

    @pytest.mark.asyncio
    async def test_fva_none_values_treated_as_zero(self):
        db = _mock_db()
        pos = _make_position(desk_mark=None, vc_fair_value=None)
        result = await calculate_fva(db, pos)

        assert result.fva_amount == Decimal("0")


# ═══════════════════════════════════════════════════════════════════
# AVA Tests
# ═══════════════════════════════════════════════════════════════════

class TestAVACategories:
    def test_mpu_with_quotes(self):
        pos = _make_position(classification="Level2")
        quotes = [
            DealerQuoteInput(dealer_name="A", value=Decimal("100")),
            DealerQuoteInput(dealer_name="B", value=Decimal("110")),
            DealerQuoteInput(dealer_name="C", value=Decimal("105")),
        ]
        mpu = _calculate_mpu(pos, quotes)
        # spread = 110 - 100 = 10; base = 5; × 1.5 (Level2) = 7.5
        assert mpu == Decimal("7.5")

    def test_mpu_fallback_insufficient_quotes(self):
        pos = _make_position(classification="Level3", vc_fair_value=Decimal("1000000"))
        mpu = _calculate_mpu(pos, [])
        # 5% of 1_000_000 = 50_000
        assert mpu == Decimal("50000.00")

    def test_mpu_level3_multiplier(self):
        pos = _make_position(classification="Level3")
        quotes = [
            DealerQuoteInput(dealer_name="A", value=Decimal("100")),
            DealerQuoteInput(dealer_name="B", value=Decimal("110")),
            DealerQuoteInput(dealer_name="C", value=Decimal("105")),
        ]
        mpu = _calculate_mpu(pos, quotes)
        # spread = 10; base = 5; × 2.83 = 14.15
        assert mpu == Decimal("14.15")

    def test_close_out_is_half_mpu(self):
        assert _calculate_close_out(Decimal("100")) == Decimal("50.00")

    def test_model_risk_with_model_results(self):
        pos = _make_position(classification="Level2", vc_fair_value=Decimal("1000000"))
        models = [
            ModelComparisonEntry(model="Black-Scholes", value=980000),
            ModelComparisonEntry(model="Heston", value=1020000),
            ModelComparisonEntry(model="SABR", value=1010000),
        ]
        mr = _calculate_model_risk(pos, models)
        # range = 40000; range_ava = 20000; industry = 5% × 1M = 50000
        assert mr == Decimal("50000")  # max(20000, 50000)

    def test_model_risk_fallback(self):
        pos = _make_position(classification="Level3", vc_fair_value=Decimal("1000000"))
        mr = _calculate_model_risk(pos, None)
        # 7% × 1M = 70_000
        assert mr == Decimal("70000")

    def test_funding_long_position(self):
        maturity = date.today() + timedelta(days=365)
        pos = _make_position(
            position_direction="LONG",
            vc_fair_value=Decimal("1000000"),
            maturity_date=maturity,
        )
        funding = _calculate_funding(pos)
        # ~75bps × 1M × 1yr ≈ 7500
        assert funding > Decimal("7000")
        assert funding < Decimal("8000")

    def test_funding_short_is_zero(self):
        pos = _make_position(position_direction="SHORT")
        assert _calculate_funding(pos) == Decimal("0")

    def test_admin_level3_multiplier(self):
        maturity = date.today() + timedelta(days=365)
        pos = _make_position(
            classification="Level3",
            vc_fair_value=Decimal("1000000"),
            maturity_date=maturity,
        )
        admin = _calculate_admin(pos)
        # ~10bps × 1M × 1yr × 1.58 ≈ 1580
        assert admin > Decimal("1500")
        assert admin < Decimal("1700")

    def test_credit_spreads_non_credit(self):
        pos = _make_position(asset_class="Rates")
        assert _calculate_credit_spreads(pos) == Decimal("0")

    def test_concentration_below_threshold(self):
        pos = _make_position(vc_fair_value=Decimal("100"))
        assert _calculate_concentration(pos, Decimal("100000")) == Decimal("0")

    @pytest.mark.asyncio
    async def test_full_ava_calculation(self):
        db = _mock_db()
        pos = _make_position(classification="Level2")
        result = await calculate_ava(db, pos)

        assert result.total_ava > Decimal("0")
        assert result.components.mpu >= Decimal("0")
        assert result.components.close_out >= Decimal("0")
        assert result.components.model_risk >= Decimal("0")
        assert result.calculation_date == date.today()
        # Two db.add calls: AVADetail + Reserve
        assert db.add.call_count == 2


# ═══════════════════════════════════════════════════════════════════
# Model Reserve Tests
# ═══════════════════════════════════════════════════════════════════

class TestModelReserve:
    @pytest.mark.asyncio
    async def test_model_reserve_basic(self):
        db = _mock_db()
        pos = _make_position()
        models = [
            ModelComparisonEntry(model="Model_A", value=1000000),
            ModelComparisonEntry(model="Model_B", value=1040000),
            ModelComparisonEntry(model="Model_C", value=1020000),
        ]
        result = await calculate_model_reserve(db, pos, models)

        # range = 40000; reserve = 50% = 20000
        assert result.model_reserve == Decimal("20000")
        assert result.model_range == Decimal("40000")

    @pytest.mark.asyncio
    async def test_model_reserve_no_results_raises(self):
        db = _mock_db()
        pos = _make_position()
        with pytest.raises(ValueError, match="No model results"):
            await calculate_model_reserve(db, pos, [])

    @pytest.mark.asyncio
    async def test_model_reserve_single_model(self):
        db = _mock_db()
        pos = _make_position()
        models = [ModelComparisonEntry(model="Only", value=1000000)]
        result = await calculate_model_reserve(db, pos, models)

        assert result.model_reserve == Decimal("0")
        assert result.model_range == Decimal("0")


# ═══════════════════════════════════════════════════════════════════
# Day 1 P&L Tests
# ═══════════════════════════════════════════════════════════════════

class TestDay1PnL:
    @pytest.mark.asyncio
    async def test_day1_recognized_level2(self):
        db = _mock_db()
        pos = _make_position(
            classification="Level2",
            transaction_price=Decimal("1020000"),
            vc_fair_value=Decimal("1000000"),
        )
        result = await calculate_day1_pnl(db, pos)

        assert result.day1_pnl == Decimal("20000")
        assert result.recognition_status == "RECOGNIZED"
        assert result.recognized_amount == Decimal("20000")
        assert result.deferred_amount == Decimal("0")
        assert result.amortization_schedule == []

    @pytest.mark.asyncio
    async def test_day1_deferred_level3(self):
        db = _mock_db()
        pos = _make_position(
            classification="Level3",
            transaction_price=Decimal("1020000"),
            vc_fair_value=Decimal("1000000"),
            trade_date=date.today(),
            maturity_date=date.today() + timedelta(days=365),
        )
        result = await calculate_day1_pnl(db, pos)

        assert result.day1_pnl == Decimal("20000")
        assert result.recognition_status == "DEFERRED"
        assert result.recognized_amount == Decimal("0")
        assert result.deferred_amount == Decimal("20000")
        assert len(result.amortization_schedule) > 0

    @pytest.mark.asyncio
    async def test_day1_level1_recognized(self):
        db = _mock_db()
        pos = _make_position(
            classification="Level1",
            transaction_price=Decimal("500000"),
            vc_fair_value=Decimal("490000"),
        )
        result = await calculate_day1_pnl(db, pos)

        assert result.recognition_status == "RECOGNIZED"
        assert result.day1_pnl == Decimal("10000")

    @pytest.mark.asyncio
    async def test_day1_amortization_schedule_sums(self):
        db = _mock_db()
        pos = _make_position(
            classification="Level3",
            transaction_price=Decimal("120000"),
            vc_fair_value=Decimal("100000"),
            trade_date=date.today(),
            maturity_date=date.today() + timedelta(days=180),
        )
        result = await calculate_day1_pnl(db, pos)

        if result.amortization_schedule:
            total_amortized = sum(
                e.amortization_amount for e in result.amortization_schedule
            )
            # Should approximately equal the deferred amount (rounding may differ slightly)
            assert abs(total_amortized - result.deferred_amount) < Decimal("1")

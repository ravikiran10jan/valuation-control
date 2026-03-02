"""Tests for the tolerance engine — verifies all thresholds from the IPV FX Model Excel."""

from decimal import Decimal

import pytest

from app.models.schemas import ProductCategory, RAGStatus
from app.services.tolerance_engine import (
    calculate_breach_amount_usd,
    calculate_difference,
    classify_product,
    evaluate_rag,
    full_tolerance_check,
    get_thresholds,
)


# ── Product classification tests ─────────────────────────────────
class TestClassifyProduct:
    def test_g10_spot(self):
        assert classify_product("Spot", "EUR/USD") == ProductCategory.G10_SPOT

    def test_g10_spot_gbp(self):
        assert classify_product("Spot", "GBP/USD") == ProductCategory.G10_SPOT

    def test_g10_spot_jpy(self):
        assert classify_product("Spot", "USD/JPY") == ProductCategory.G10_SPOT

    def test_em_spot_try(self):
        assert classify_product("Spot (EM)", "USD/TRY") == ProductCategory.EM_SPOT

    def test_em_spot_brl(self):
        assert classify_product("Spot (EM)", "USD/BRL") == ProductCategory.EM_SPOT

    def test_em_spot_by_currency_pair(self):
        """EM classification even without (EM) in product type."""
        assert classify_product("Spot", "USD/TRY") == ProductCategory.EM_SPOT

    def test_forward(self):
        assert classify_product("1Y Forward", "EUR/USD") == ProductCategory.FX_FORWARD

    def test_forward_fwd(self):
        assert classify_product("FWD", "GBP/USD") == ProductCategory.FX_FORWARD

    def test_barrier_dnt(self):
        assert classify_product("Barrier (DNT)", "EUR/USD") == ProductCategory.FX_OPTION

    def test_vanilla_option(self):
        assert classify_product("Vanilla Option", "EUR/USD") == ProductCategory.FX_OPTION

    def test_ndf(self):
        assert classify_product("NDF", "USD/BRL") == ProductCategory.FX_FORWARD


# ── Threshold lookup tests ───────────────────────────────────────
class TestGetThresholds:
    def test_g10_spot_thresholds(self):
        green, amber = get_thresholds(ProductCategory.G10_SPOT)
        assert green == Decimal("0.05")  # 5 bps = 0.05%
        assert amber == Decimal("0.10")  # 10 bps = 0.10%

    def test_em_spot_thresholds(self):
        green, amber = get_thresholds(ProductCategory.EM_SPOT)
        assert green == Decimal("2.0")   # 2%
        assert amber == Decimal("5.0")   # 5%

    def test_forward_thresholds(self):
        green, amber = get_thresholds(ProductCategory.FX_FORWARD)
        assert green == Decimal("0.10")  # 10 bps = 0.10%
        assert amber == Decimal("0.20")  # 20 bps = 0.20%

    def test_option_thresholds(self):
        green, amber = get_thresholds(ProductCategory.FX_OPTION)
        assert green == Decimal("5.0")   # 5%
        assert amber == Decimal("10.0")  # 10%


# ── Difference calculation tests ─────────────────────────────────
class TestCalculateDifference:
    def test_positive_difference(self):
        diff, diff_pct = calculate_difference(Decimal("1.0825"), Decimal("1.0823"))
        assert diff == Decimal("0.0002")
        assert abs(diff_pct - Decimal("0.01848")) < Decimal("0.001")

    def test_negative_difference(self):
        diff, diff_pct = calculate_difference(Decimal("149.85"), Decimal("149.88"))
        assert diff == Decimal("-0.03")
        assert diff_pct < 0

    def test_zero_ipv_price_nonzero_desk(self):
        diff, diff_pct = calculate_difference(Decimal("1.0"), Decimal("0"))
        assert diff == Decimal("1.0")
        assert diff_pct == Decimal("100")

    def test_both_zero(self):
        diff, diff_pct = calculate_difference(Decimal("0"), Decimal("0"))
        assert diff == Decimal("0")
        assert diff_pct == Decimal("0")

    def test_large_em_difference(self):
        """USD/TRY: desk 32.45, IPV 35.12 => ~-7.60% diff."""
        diff, diff_pct = calculate_difference(Decimal("32.45"), Decimal("35.12"))
        assert diff < 0  # Desk mark is lower than IPV
        assert abs(diff_pct) > Decimal("5.0")  # Should be RED for EM


# ── RAG evaluation tests matching Excel positions ────────────────
class TestEvaluateRAG:
    def test_fx_spot_001_green(self):
        """FX-SPOT-001 EUR/USD: 0.018% diff => GREEN (threshold 5bps=0.05%)."""
        rag = evaluate_rag(Decimal("0.018"), ProductCategory.G10_SPOT)
        assert rag == RAGStatus.GREEN

    def test_fx_spot_002_green(self):
        """FX-SPOT-002 GBP/USD: 0.024% diff => GREEN."""
        rag = evaluate_rag(Decimal("0.024"), ProductCategory.G10_SPOT)
        assert rag == RAGStatus.GREEN

    def test_fx_spot_003_green(self):
        """FX-SPOT-003 USD/JPY: -0.02% diff => GREEN."""
        rag = evaluate_rag(Decimal("-0.02"), ProductCategory.G10_SPOT)
        assert rag == RAGStatus.GREEN

    def test_fx_spot_004_red(self):
        """FX-SPOT-004 USD/TRY: -8.22% diff => RED (threshold >5% for EM)."""
        rag = evaluate_rag(Decimal("-8.22"), ProductCategory.EM_SPOT)
        assert rag == RAGStatus.RED

    def test_fx_spot_005_amber(self):
        """FX-SPOT-005 USD/BRL: -1.17% diff => GREEN (threshold <2% for EM)."""
        rag = evaluate_rag(Decimal("-1.17"), ProductCategory.EM_SPOT)
        assert rag == RAGStatus.GREEN

    def test_fx_fwd_001_green(self):
        """FX-FWD-001 EUR/USD Forward: 0.018% diff => GREEN (threshold 10bps=0.10%)."""
        rag = evaluate_rag(Decimal("0.018"), ProductCategory.FX_FORWARD)
        assert rag == RAGStatus.GREEN

    def test_fx_opt_001_zero_diff(self):
        """FX-OPT-001 Barrier: 0% diff => GREEN."""
        rag = evaluate_rag(Decimal("0"), ProductCategory.FX_OPTION)
        assert rag == RAGStatus.GREEN

    def test_g10_spot_at_amber_boundary(self):
        """Exactly at 5bps (0.05%) should be AMBER."""
        rag = evaluate_rag(Decimal("0.05"), ProductCategory.G10_SPOT)
        assert rag == RAGStatus.AMBER

    def test_g10_spot_at_red_boundary(self):
        """Just above 10bps (0.101%) should be RED."""
        rag = evaluate_rag(Decimal("0.101"), ProductCategory.G10_SPOT)
        assert rag == RAGStatus.RED

    def test_em_spot_at_amber_boundary(self):
        """Exactly at 2% should be AMBER for EM."""
        rag = evaluate_rag(Decimal("2.0"), ProductCategory.EM_SPOT)
        assert rag == RAGStatus.AMBER

    def test_em_spot_at_red_boundary(self):
        """Just above 5% should be RED for EM."""
        rag = evaluate_rag(Decimal("5.01"), ProductCategory.EM_SPOT)
        assert rag == RAGStatus.RED

    def test_forward_at_amber(self):
        """0.15% => AMBER for forwards (10-20bps)."""
        rag = evaluate_rag(Decimal("0.15"), ProductCategory.FX_FORWARD)
        assert rag == RAGStatus.AMBER

    def test_option_at_red(self):
        """12% diff => RED for options (>10%)."""
        rag = evaluate_rag(Decimal("12.0"), ProductCategory.FX_OPTION)
        assert rag == RAGStatus.RED


# ── Breach amount tests ──────────────────────────────────────────
class TestBreachAmount:
    def test_green_no_breach(self):
        """GREEN positions should have no breach amount."""
        result = calculate_breach_amount_usd(
            Decimal("0.02"), Decimal("150000000"), ProductCategory.G10_SPOT,
        )
        assert result is None

    def test_red_em_breach(self):
        """USD/TRY with 8.22% diff: breach = 25M * (8.22 - 2.0) / 100."""
        result = calculate_breach_amount_usd(
            Decimal("8.22"), Decimal("25000000"), ProductCategory.EM_SPOT,
        )
        expected = Decimal("25000000") * Decimal("6.22") / Decimal("100")
        assert result is not None
        assert abs(result - expected) < Decimal("0.01")

    def test_amber_forward_breach(self):
        """Forward at 0.15% diff: breach = notional * (0.15 - 0.10) / 100."""
        result = calculate_breach_amount_usd(
            Decimal("0.15"), Decimal("120000000"), ProductCategory.FX_FORWARD,
        )
        expected = Decimal("120000000") * Decimal("0.05") / Decimal("100")
        assert result is not None
        assert abs(result - expected) < Decimal("0.01")


# ── Full tolerance check integration tests ───────────────────────
class TestFullToleranceCheck:
    def test_fx_spot_001_eurusd(self):
        """FX-SPOT-001: EUR/USD Spot, desk 1.0825, IPV 1.0823."""
        result = full_tolerance_check(
            desk_mark=Decimal("1.0825"),
            ipv_price=Decimal("1.0823"),
            notional=Decimal("150000000"),
            product_type="Spot",
            currency_pair="EUR/USD",
        )
        assert result["product_category"] == ProductCategory.G10_SPOT
        assert result["rag_status"] == RAGStatus.GREEN
        assert result["breach"] is False
        assert result["breach_amount_usd"] is None

    def test_fx_spot_004_usdtry(self):
        """FX-SPOT-004: USD/TRY Spot (EM), desk 32.45, IPV 35.12."""
        result = full_tolerance_check(
            desk_mark=Decimal("32.45"),
            ipv_price=Decimal("35.12"),
            notional=Decimal("25000000"),
            product_type="Spot (EM)",
            currency_pair="USD/TRY",
        )
        assert result["product_category"] == ProductCategory.EM_SPOT
        assert result["rag_status"] == RAGStatus.RED
        assert result["breach"] is True
        assert result["breach_amount_usd"] is not None
        assert result["breach_amount_usd"] > Decimal("0")

    def test_fx_spot_005_usdbrl(self):
        """FX-SPOT-005: USD/BRL Spot (EM), desk 5.12, IPV 5.18."""
        result = full_tolerance_check(
            desk_mark=Decimal("5.12"),
            ipv_price=Decimal("5.18"),
            notional=Decimal("10000000"),
            product_type="Spot (EM)",
            currency_pair="USD/BRL",
        )
        assert result["product_category"] == ProductCategory.EM_SPOT
        # 5.12/5.18 - 1 = -1.158% => GREEN (threshold 2%)
        assert result["rag_status"] == RAGStatus.GREEN

    def test_fx_fwd_001_eurusd(self):
        """FX-FWD-001: EUR/USD 1Y Forward, desk 1.095, IPV 1.0948."""
        result = full_tolerance_check(
            desk_mark=Decimal("1.095"),
            ipv_price=Decimal("1.0948"),
            notional=Decimal("120000000"),
            product_type="1Y Forward",
            currency_pair="EUR/USD",
        )
        assert result["product_category"] == ProductCategory.FX_FORWARD
        assert result["rag_status"] == RAGStatus.GREEN

    def test_fx_opt_001_barrier(self):
        """FX-OPT-001: EUR/USD Barrier (DNT), desk 425000, IPV 425000 => 0% diff."""
        result = full_tolerance_check(
            desk_mark=Decimal("425000"),
            ipv_price=Decimal("425000"),
            notional=Decimal("50000000"),
            product_type="Barrier (DNT)",
            currency_pair="EUR/USD",
        )
        assert result["product_category"] == ProductCategory.FX_OPTION
        assert result["rag_status"] == RAGStatus.GREEN
        assert result["breach"] is False

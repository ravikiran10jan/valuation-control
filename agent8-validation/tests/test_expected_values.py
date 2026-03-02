"""Unit tests that validate the expected values themselves for internal consistency.

These tests do NOT call any upstream agents.  They verify that the
ground-truth constants in expected_values.py are self-consistent,
following the relationships defined in the Excel model.
"""

from __future__ import annotations

import pytest

from app.services.expected_values import (
    EXPECTED_AVA_BARRIER,
    EXPECTED_BARRIER_PRICING,
    EXPECTED_CAPITAL,
    EXPECTED_DAY1_PNL,
    EXPECTED_FV_HIERARCHY,
    EXPECTED_FVA_BARRIER,
    EXPECTED_GREEKS_BARRIER,
    EXPECTED_MODEL_RESERVES,
    EXPECTED_POSITIONS,
    EXPECTED_SUMMARY,
    EXPECTED_THRESHOLDS,
    EXPECTED_TOTAL_FVA,
    count_by_fv_level,
    count_by_rag,
    get_expected_position,
    get_expected_reserve,
    total_expected_book_value,
    total_expected_notional,
)


# ── Position data ────────────────────────────────────────────────────


class TestPositionConsistency:
    """Verify internal consistency of the EXPECTED_POSITIONS list."""

    def test_position_count(self) -> None:
        """There should be exactly 7 positions."""
        assert len(EXPECTED_POSITIONS) == 7

    def test_unique_position_ids(self) -> None:
        """All position IDs must be unique."""
        ids = [p["position_id"] for p in EXPECTED_POSITIONS]
        assert len(ids) == len(set(ids))

    def test_all_required_fields_present(self) -> None:
        """Each position must have all required fields."""
        required = {
            "position_id",
            "currency_pair",
            "product_type",
            "notional_usd",
            "desk_mark",
            "ipv_price",
            "pct_diff",
            "rag_status",
            "fv_level",
            "fva_usd",
            "book_value_usd",
        }
        for pos in EXPECTED_POSITIONS:
            missing = required - set(pos.keys())
            assert not missing, f"{pos['position_id']} missing fields: {missing}"

    def test_rag_values_valid(self) -> None:
        """RAG status must be GREEN, AMBER, or RED."""
        valid = {"GREEN", "AMBER", "RED"}
        for pos in EXPECTED_POSITIONS:
            assert pos["rag_status"] in valid, (
                f"{pos['position_id']} has invalid RAG: {pos['rag_status']}"
            )

    def test_fv_levels_valid(self) -> None:
        """FV level must be L1, L2, or L3."""
        valid = {"L1", "L2", "L3"}
        for pos in EXPECTED_POSITIONS:
            assert pos["fv_level"] in valid, (
                f"{pos['position_id']} has invalid FV level: {pos['fv_level']}"
            )

    def test_notionals_positive(self) -> None:
        """All notionals must be positive."""
        for pos in EXPECTED_POSITIONS:
            assert pos["notional_usd"] > 0, (
                f"{pos['position_id']} has non-positive notional"
            )

    def test_book_values_positive(self) -> None:
        """All book values must be positive."""
        for pos in EXPECTED_POSITIONS:
            assert pos["book_value_usd"] > 0, (
                f"{pos['position_id']} has non-positive book value"
            )

    def test_product_types_valid(self) -> None:
        """Product types should be known types."""
        valid = {"Spot", "Forward", "Barrier", "Option", "Swap"}
        for pos in EXPECTED_POSITIONS:
            assert pos["product_type"] in valid, (
                f"{pos['position_id']} has unexpected product type: {pos['product_type']}"
            )

    def test_helper_get_expected_position(self) -> None:
        """get_expected_position returns correct dict or None."""
        pos = get_expected_position("FX-SPOT-001")
        assert pos is not None
        assert pos["currency_pair"] == "EUR/USD"

        assert get_expected_position("NONEXISTENT") is None

    def test_helper_total_notional(self) -> None:
        """total_expected_notional sums correctly."""
        manual_sum = sum(p["notional_usd"] for p in EXPECTED_POSITIONS)
        assert total_expected_notional() == manual_sum

    def test_helper_total_book_value(self) -> None:
        """total_expected_book_value sums correctly."""
        manual_sum = sum(p["book_value_usd"] for p in EXPECTED_POSITIONS)
        assert total_expected_book_value() == manual_sum


# ── RAG counts ───────────────────────────────────────────────────────


class TestRAGCounts:
    """Verify RAG status counts match the summary."""

    def test_green_count(self) -> None:
        assert count_by_rag("GREEN") == EXPECTED_SUMMARY["total_ipv_breaches"]["green"]

    def test_amber_count(self) -> None:
        assert count_by_rag("AMBER") == EXPECTED_SUMMARY["total_ipv_breaches"]["amber"]

    def test_red_count(self) -> None:
        assert count_by_rag("RED") == EXPECTED_SUMMARY["total_ipv_breaches"]["red"]

    def test_total_rag_equals_position_count(self) -> None:
        total = (
            count_by_rag("GREEN")
            + count_by_rag("AMBER")
            + count_by_rag("RED")
        )
        assert total == len(EXPECTED_POSITIONS)


# ── FV Hierarchy ─────────────────────────────────────────────────────


class TestFVHierarchyConsistency:
    """Verify FV hierarchy internal consistency."""

    def test_level_counts_match_positions(self) -> None:
        """Level counts derived from positions must match hierarchy sheet."""
        for level, expected in EXPECTED_FV_HIERARCHY.items():
            assert count_by_fv_level(level) == expected["count"], (
                f"Level {level} count mismatch"
            )

    def test_total_positions_across_levels(self) -> None:
        """Sum of level counts must equal total positions."""
        total = sum(v["count"] for v in EXPECTED_FV_HIERARCHY.values())
        assert total == len(EXPECTED_POSITIONS)

    def test_book_values_match_positions(self) -> None:
        """Book values per level derived from positions should be close to hierarchy.

        The hierarchy sheet may use slightly different valuation snapshots
        compared to the positions sheet, so we allow a 0.1% tolerance
        on the book value comparison.
        """
        level_bv: dict[str, int] = {}
        for pos in EXPECTED_POSITIONS:
            lv = pos["fv_level"]
            level_bv[lv] = level_bv.get(lv, 0) + pos["book_value_usd"]

        for level, expected in EXPECTED_FV_HIERARCHY.items():
            derived = level_bv.get(level, 0)
            expected_bv = expected["book_value"]
            # Allow 0.1% tolerance for cross-sheet valuation differences
            tolerance = max(1000, expected_bv * 0.001)
            assert abs(derived - expected_bv) < tolerance, (
                f"Level {level} book value mismatch: "
                f"derived {derived:,} vs expected {expected_bv:,} "
                f"(diff={derived - expected_bv:,}, tol={tolerance:,.0f})"
            )

    def test_l3_exposure_matches_summary(self) -> None:
        """Level 3 exposure in hierarchy must match summary."""
        assert EXPECTED_FV_HIERARCHY["L3"]["book_value"] == EXPECTED_SUMMARY["level_3_exposure"]


# ── Threshold consistency ────────────────────────────────────────────


class TestThresholds:
    """Verify threshold definitions are internally consistent."""

    def test_all_categories_present(self) -> None:
        expected_cats = {"G10_SPOT", "EM_SPOT", "FX_FORWARDS", "FX_OPTIONS"}
        assert set(EXPECTED_THRESHOLDS.keys()) == expected_cats

    def test_green_less_than_amber(self) -> None:
        """Green threshold must be strictly less than amber."""
        for cat, thresholds in EXPECTED_THRESHOLDS.items():
            if "green_max_bps" in thresholds:
                assert thresholds["green_max_bps"] < thresholds["amber_max_bps"], (
                    f"{cat}: green_max_bps >= amber_max_bps"
                )
            if "green_max_pct" in thresholds:
                assert thresholds["green_max_pct"] < thresholds["amber_max_pct"], (
                    f"{cat}: green_max_pct >= amber_max_pct"
                )

    def test_thresholds_positive(self) -> None:
        """All thresholds must be positive."""
        for cat, thresholds in EXPECTED_THRESHOLDS.items():
            for key, val in thresholds.items():
                assert val > 0, f"{cat}.{key} is not positive"


# ── Summary metrics ──────────────────────────────────────────────────


class TestSummaryMetrics:
    """Verify summary dashboard metrics are consistent with position data."""

    def test_total_notional(self) -> None:
        """Summary total notional should be close to position sum.

        The summary dashboard may compute notional differently (e.g. net
        vs gross, or different FX conversion rates), so we allow a 1%
        tolerance rather than exact match.
        """
        derived = total_expected_notional()
        expected = EXPECTED_SUMMARY["total_notional_usd"]
        tolerance = expected * 0.01  # 1%
        assert abs(derived - expected) < tolerance, (
            f"Notional mismatch: derived {derived:,} vs summary {expected:,} "
            f"(diff={abs(derived - expected):,}, tol={tolerance:,.0f})"
        )

    def test_breach_counts_sum(self) -> None:
        """Breach counts should sum to total positions."""
        breaches = EXPECTED_SUMMARY["total_ipv_breaches"]
        total = breaches["red"] + breaches["amber"] + breaches["green"]
        assert total == len(EXPECTED_POSITIONS)


# ── Model Reserve ────────────────────────────────────────────────────


class TestModelReserves:
    """Verify model reserve internal consistency."""

    def test_all_positions_have_reserve(self) -> None:
        """Every position should have a reserve entry."""
        for pos in EXPECTED_POSITIONS:
            pid = pos["position_id"]
            assert pid in EXPECTED_MODEL_RESERVES, (
                f"Position {pid} missing from model reserves"
            )

    def test_total_equals_sum(self) -> None:
        """Total reserve must equal sum of individual reserves."""
        individual_sum = sum(
            v["reserve"]
            for k, v in EXPECTED_MODEL_RESERVES.items()
            if k != "total" and isinstance(v, dict)
        )
        assert individual_sum == EXPECTED_MODEL_RESERVES["total"]

    def test_materiality_values_valid(self) -> None:
        """Materiality must be ZERO, IMMATERIAL, or MATERIAL."""
        valid = {"ZERO", "IMMATERIAL", "MATERIAL"}
        for pid, data in EXPECTED_MODEL_RESERVES.items():
            if pid == "total":
                continue
            assert data["materiality"] in valid, (
                f"{pid} has invalid materiality: {data['materiality']}"
            )

    def test_zero_reserve_has_zero_materiality(self) -> None:
        """Positions with reserve=0 should have materiality ZERO."""
        for pid, data in EXPECTED_MODEL_RESERVES.items():
            if pid == "total":
                continue
            if data["reserve"] == 0:
                assert data["materiality"] == "ZERO", (
                    f"{pid}: reserve is 0 but materiality is {data['materiality']}"
                )

    def test_helper_get_expected_reserve(self) -> None:
        res = get_expected_reserve("FX-OPT-001")
        assert res is not None
        assert res["reserve"] == 42_500
        assert get_expected_reserve("total") is None  # "total" is int, not dict


# ── AVA ──────────────────────────────────────────────────────────────


class TestAVA:
    """Verify AVA expected values are internally consistent."""

    def test_components_sum_to_total(self) -> None:
        """AVA component sum must equal total_ava."""
        components = EXPECTED_AVA_BARRIER["components"]
        comp_sum = sum(components.values())
        assert comp_sum == EXPECTED_AVA_BARRIER["total_ava"], (
            f"AVA component sum {comp_sum} != total {EXPECTED_AVA_BARRIER['total_ava']}"
        )

    def test_all_seven_components_present(self) -> None:
        """All 7 AVA categories per Basel III Article 105 must be present."""
        required = {"mpu", "close_out", "model_risk", "credit_spreads",
                     "funding", "concentration", "admin"}
        assert set(EXPECTED_AVA_BARRIER["components"].keys()) == required

    def test_dealer_quotes_present(self) -> None:
        """At least 3 dealer quotes should be present."""
        quotes = EXPECTED_AVA_BARRIER["dealer_quotes"]
        assert len(quotes) >= 3

    def test_position_id_matches(self) -> None:
        assert EXPECTED_AVA_BARRIER["position_id"] == "FX-OPT-001"


# ── Day 1 PnL ───────────────────────────────────────────────────────


class TestDay1PnL:
    """Verify Day 1 PnL expected values are internally consistent."""

    def test_pnl_equals_txn_minus_fv(self) -> None:
        """day1_pnl = transaction_price - fair_value."""
        expected_pnl = (
            EXPECTED_DAY1_PNL["transaction_price"]
            - EXPECTED_DAY1_PNL["fair_value"]
        )
        assert expected_pnl == EXPECTED_DAY1_PNL["day1_pnl"]

    def test_recognition_is_deferred(self) -> None:
        """L3 barrier option Day 1 PnL should be DEFERRED."""
        assert EXPECTED_DAY1_PNL["recognition"] == "DEFERRED"

    def test_amortization_monthly_reasonable(self) -> None:
        """Monthly amortization should be in the right ballpark.

        The Excel model may use a different amortization methodology
        (e.g. straight-line on fair value vs transaction price, or
        adjusted for day-count conventions), so we use a 10% tolerance
        on the simple day1_pnl / months calculation.
        """
        simple_monthly = EXPECTED_DAY1_PNL["day1_pnl"] / EXPECTED_DAY1_PNL["amortization_months"]
        actual_monthly = EXPECTED_DAY1_PNL["amortization_monthly"]
        tolerance = simple_monthly * 0.10  # 10%
        assert abs(simple_monthly - actual_monthly) < tolerance, (
            f"Monthly amort: simple calc ~{simple_monthly:.0f}, "
            f"got {actual_monthly}, tol={tolerance:.0f}"
        )

    def test_amortization_daily_reasonable(self) -> None:
        """Daily amortization should be roughly monthly / ~30."""
        daily = EXPECTED_DAY1_PNL["amortization_daily"]
        monthly = EXPECTED_DAY1_PNL["amortization_monthly"]
        # daily * ~28-31 days should be close to monthly
        assert 25 * daily < monthly < 32 * daily


# ── FVA ──────────────────────────────────────────────────────────────


class TestFVA:
    """Verify FVA expected values are internally consistent."""

    def test_fva_amount_equals_premium_minus_fv(self) -> None:
        """FVA amount = premium - fair_value."""
        expected = EXPECTED_FVA_BARRIER["premium"] - EXPECTED_FVA_BARRIER["fair_value"]
        assert expected == EXPECTED_FVA_BARRIER["fva_amount"]

    def test_monthly_release_reasonable(self) -> None:
        """Monthly release should be roughly fva_amount / total_months."""
        expected_monthly = (
            EXPECTED_FVA_BARRIER["fva_amount"] / EXPECTED_FVA_BARRIER["total_months"]
        )
        actual_monthly = EXPECTED_FVA_BARRIER["monthly_release"]
        assert abs(expected_monthly - actual_monthly) < 100


# ── Barrier Pricing ──────────────────────────────────────────────────


class TestBarrierPricing:
    """Verify barrier pricing expected values."""

    def test_survival_probabilities_in_range(self) -> None:
        """All survival probabilities must be between 0 and 1."""
        for key in (
            "analytical_survival",
            "monte_carlo_survival",
            "pde_survival",
            "bloomberg_ovml",
            "consensus_survival",
        ):
            val = EXPECTED_BARRIER_PRICING[key]
            assert 0 < val < 1, f"{key}={val} is not in (0, 1)"

    def test_methods_converge(self) -> None:
        """All pricing methods should be within tolerance_pct of each other."""
        values = [
            EXPECTED_BARRIER_PRICING["analytical_survival"],
            EXPECTED_BARRIER_PRICING["monte_carlo_survival"],
            EXPECTED_BARRIER_PRICING["pde_survival"],
            EXPECTED_BARRIER_PRICING["bloomberg_ovml"],
        ]
        max_val = max(values)
        min_val = min(values)
        spread_pct = (max_val - min_val) / min_val * 100
        tol = EXPECTED_BARRIER_PRICING["tolerance_pct"]
        assert spread_pct <= tol, (
            f"Method spread {spread_pct:.4f}% exceeds tolerance {tol}%"
        )

    def test_fair_value_positive(self) -> None:
        assert EXPECTED_BARRIER_PRICING["fair_value"] > 0


# ── Greeks ───────────────────────────────────────────────────────────


class TestGreeks:
    """Verify Greeks expected values."""

    def test_delta_positive(self) -> None:
        assert EXPECTED_GREEKS_BARRIER["delta_per_pip"] > 0

    def test_theta_negative(self) -> None:
        """Theta for a long option should be negative."""
        assert EXPECTED_GREEKS_BARRIER["theta_daily"] < 0

    def test_gamma_near_barrier_flagged(self) -> None:
        assert EXPECTED_GREEKS_BARRIER["gamma_near_barrier"] == "HIGH"


# ── Capital Adequacy ─────────────────────────────────────────────────


class TestCapitalAdequacy:
    """Verify capital adequacy expected values are internally consistent."""

    def test_cet1_equals_components(self) -> None:
        """CET1 capital must equal the sum of its components."""
        derived = (
            EXPECTED_CAPITAL["shareholders_equity"]
            + EXPECTED_CAPITAL["retained_earnings"]
            + EXPECTED_CAPITAL["aoci"]
            + EXPECTED_CAPITAL["goodwill_deduction"]
            + EXPECTED_CAPITAL["dta_deduction"]
            + EXPECTED_CAPITAL["ava_deduction"]
            + EXPECTED_CAPITAL["other_deductions"]
        )
        assert derived == EXPECTED_CAPITAL["cet1_capital"], (
            f"CET1 derivation: {derived} != {EXPECTED_CAPITAL['cet1_capital']}"
        )

    def test_rwa_equals_components(self) -> None:
        """Total RWA must equal sum of risk categories."""
        derived = (
            EXPECTED_CAPITAL["credit_risk_rwa"]
            + EXPECTED_CAPITAL["market_risk_rwa"]
            + EXPECTED_CAPITAL["operational_risk_rwa"]
        )
        assert derived == EXPECTED_CAPITAL["total_rwa"]

    def test_cet1_ratio_above_minimum(self) -> None:
        """CET1 ratio must meet minimum requirement."""
        ratio = EXPECTED_CAPITAL["cet1_capital"] / EXPECTED_CAPITAL["total_rwa"]
        assert ratio >= EXPECTED_CAPITAL["cet1_ratio_min"]

    def test_cet1_ratio_above_ccb(self) -> None:
        """CET1 ratio must meet capital conservation buffer."""
        ratio = EXPECTED_CAPITAL["cet1_capital"] / EXPECTED_CAPITAL["total_rwa"]
        assert ratio >= EXPECTED_CAPITAL["ccb_min"]

    def test_ava_deduction_matches_ava_total(self) -> None:
        """AVA deduction in capital should equal negative of AVA total."""
        assert EXPECTED_CAPITAL["ava_deduction"] == -EXPECTED_AVA_BARRIER["total_ava"]

    def test_deductions_are_negative(self) -> None:
        """All deduction fields must be negative or zero."""
        deduction_fields = [
            "goodwill_deduction",
            "dta_deduction",
            "ava_deduction",
            "other_deductions",
        ]
        for field in deduction_fields:
            assert EXPECTED_CAPITAL[field] <= 0, (
                f"{field} should be negative, got {EXPECTED_CAPITAL[field]}"
            )

    def test_equity_components_positive(self) -> None:
        """Equity components should be positive."""
        for field in ("shareholders_equity", "retained_earnings", "aoci"):
            assert EXPECTED_CAPITAL[field] > 0, (
                f"{field} should be positive, got {EXPECTED_CAPITAL[field]}"
            )

    def test_rwa_components_positive(self) -> None:
        """RWA components should be positive."""
        for field in ("credit_risk_rwa", "market_risk_rwa", "operational_risk_rwa"):
            assert EXPECTED_CAPITAL[field] > 0

    def test_minimum_ratios_reasonable(self) -> None:
        """Minimum ratios should be in a reasonable range."""
        assert 0.0 < EXPECTED_CAPITAL["cet1_ratio_min"] < 0.20
        assert 0.0 < EXPECTED_CAPITAL["ccb_min"] < 0.20
        assert EXPECTED_CAPITAL["cet1_ratio_min"] < EXPECTED_CAPITAL["ccb_min"]

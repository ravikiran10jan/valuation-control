"""Tests for the IPV pipeline orchestrator.

Tests the pipeline logic without requiring actual upstream agents,
using mocked HTTP responses.
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.schemas import (
    ComparisonResult,
    ExceptionRecord,
    FairValueLevel,
    IPVRunRequest,
    IPVRunStatus,
    IPVStepName,
    MarketDataSnapshot,
    PositionInput,
    ProductCategory,
    RAGStatus,
    StepStatus,
    ValuationResult,
)
from app.services.comparison_engine import ComparisonEngine
from app.services.exception_generator import ExceptionGenerator
from app.services.ipv_pipeline import IPVPipeline
from app.services.tolerance_engine import classify_product


# ── Test data ────────────────────────────────────────────────────
SAMPLE_POSITIONS = [
    PositionInput(
        position_id="FX-SPOT-001",
        currency_pair="EUR/USD",
        product_type="Spot",
        notional=Decimal("150000000"),
        desk_mark=Decimal("1.0825"),
        fair_value_level=FairValueLevel.L1,
    ),
    PositionInput(
        position_id="FX-SPOT-004",
        currency_pair="USD/TRY",
        product_type="Spot (EM)",
        notional=Decimal("25000000"),
        desk_mark=Decimal("32.45"),
        fair_value_level=FairValueLevel.L2,
    ),
    PositionInput(
        position_id="FX-OPT-001",
        currency_pair="EUR/USD",
        product_type="Barrier (DNT)",
        notional=Decimal("50000000"),
        desk_mark=Decimal("425000"),
        fair_value_level=FairValueLevel.L3,
        lower_barrier=Decimal("1.0500"),
        upper_barrier=Decimal("1.1200"),
        barrier_type="DNT",
        volatility=Decimal("0.0850"),
        time_to_expiry=Decimal("0.5"),
        domestic_rate=Decimal("0.0425"),
        foreign_rate=Decimal("0.0300"),
    ),
]


# ── ComparisonEngine tests ───────────────────────────────────────
class TestComparisonEngine:
    def test_compare_green_position(self):
        """EUR/USD spot with small difference should be GREEN."""
        engine = ComparisonEngine()
        position = SAMPLE_POSITIONS[0]
        valuation = ValuationResult(
            position_id="FX-SPOT-001",
            ipv_price=Decimal("1.0823"),
            pricing_method="median_mid",
        )
        result = engine.compare_position(position, valuation)
        assert result.rag_status == RAGStatus.GREEN
        assert result.breach is False
        assert result.product_category == ProductCategory.G10_SPOT

    def test_compare_red_position(self):
        """USD/TRY with large difference should be RED."""
        engine = ComparisonEngine()
        position = SAMPLE_POSITIONS[1]
        valuation = ValuationResult(
            position_id="FX-SPOT-004",
            ipv_price=Decimal("35.12"),
            pricing_method="median_mid",
        )
        result = engine.compare_position(position, valuation)
        assert result.rag_status == RAGStatus.RED
        assert result.breach is True
        assert result.product_category == ProductCategory.EM_SPOT

    def test_compare_zero_diff(self):
        """Barrier option with zero difference should be GREEN."""
        engine = ComparisonEngine()
        position = SAMPLE_POSITIONS[2]
        valuation = ValuationResult(
            position_id="FX-OPT-001",
            ipv_price=Decimal("425000"),
            pricing_method="monte_carlo",
        )
        result = engine.compare_position(position, valuation)
        assert result.rag_status == RAGStatus.GREEN
        assert result.breach is False

    def test_compare_all(self):
        """Compare all sample positions at once."""
        engine = ComparisonEngine()
        valuations = {
            "FX-SPOT-001": ValuationResult(
                position_id="FX-SPOT-001",
                ipv_price=Decimal("1.0823"),
                pricing_method="median_mid",
            ),
            "FX-SPOT-004": ValuationResult(
                position_id="FX-SPOT-004",
                ipv_price=Decimal("35.12"),
                pricing_method="median_mid",
            ),
            "FX-OPT-001": ValuationResult(
                position_id="FX-OPT-001",
                ipv_price=Decimal("425000"),
                pricing_method="monte_carlo",
            ),
        }
        results = engine.compare_all(SAMPLE_POSITIONS, valuations)
        assert len(results) == 3
        assert results["FX-SPOT-001"].rag_status == RAGStatus.GREEN
        assert results["FX-SPOT-004"].rag_status == RAGStatus.RED
        assert results["FX-OPT-001"].rag_status == RAGStatus.GREEN


# ── ExceptionGenerator tests ────────────────────────────────────
class TestExceptionGenerator:
    def test_green_no_exception(self):
        """GREEN positions should not generate exceptions."""
        gen = ExceptionGenerator()
        position = SAMPLE_POSITIONS[0]
        comparison = ComparisonResult(
            position_id="FX-SPOT-001",
            desk_mark=Decimal("1.0825"),
            ipv_price=Decimal("1.0823"),
            difference=Decimal("0.0002"),
            difference_pct=Decimal("0.018"),
            product_category=ProductCategory.G10_SPOT,
            rag_status=RAGStatus.GREEN,
            threshold_green=Decimal("0.05"),
            threshold_amber=Decimal("0.10"),
            breach=False,
        )
        result = gen.flag_exception(position, comparison)
        assert result is None

    def test_red_generates_escalation_for_material_breach(self):
        """RED L2 position with material breach (>500K) should ESCALATE."""
        gen = ExceptionGenerator()
        position = SAMPLE_POSITIONS[1]
        comparison = ComparisonResult(
            position_id="FX-SPOT-004",
            desk_mark=Decimal("32.45"),
            ipv_price=Decimal("35.12"),
            difference=Decimal("-2.67"),
            difference_pct=Decimal("-7.60"),
            product_category=ProductCategory.EM_SPOT,
            rag_status=RAGStatus.RED,
            threshold_green=Decimal("2.0"),
            threshold_amber=Decimal("5.0"),
            breach=True,
        )
        result = gen.flag_exception(position, comparison)
        assert result is not None
        assert result.severity == RAGStatus.RED
        # Breach is 7.6% of 25M = $1.9M > 500K materiality threshold -> ESCALATE
        assert result.auto_action == "ESCALATE"

    def test_red_l3_generates_escalation(self):
        """RED L3 position should generate an ESCALATE exception."""
        gen = ExceptionGenerator()
        # Create a L3 position that breaches
        position = PositionInput(
            position_id="FX-OPT-TEST",
            currency_pair="EUR/USD",
            product_type="Barrier (DNT)",
            notional=Decimal("50000000"),
            desk_mark=Decimal("500000"),
            fair_value_level=FairValueLevel.L3,
        )
        comparison = ComparisonResult(
            position_id="FX-OPT-TEST",
            desk_mark=Decimal("500000"),
            ipv_price=Decimal("425000"),
            difference=Decimal("75000"),
            difference_pct=Decimal("17.65"),
            product_category=ProductCategory.FX_OPTION,
            rag_status=RAGStatus.RED,
            threshold_green=Decimal("5.0"),
            threshold_amber=Decimal("10.0"),
            breach=True,
        )
        result = gen.flag_exception(position, comparison)
        assert result is not None
        assert result.severity == RAGStatus.RED
        assert result.auto_action == "ESCALATE"

    def test_flag_all_mixed(self):
        """Flag exceptions for a mix of GREEN and RED positions."""
        gen = ExceptionGenerator()
        comparisons = {
            "FX-SPOT-001": ComparisonResult(
                position_id="FX-SPOT-001",
                desk_mark=Decimal("1.0825"),
                ipv_price=Decimal("1.0823"),
                difference=Decimal("0.0002"),
                difference_pct=Decimal("0.018"),
                product_category=ProductCategory.G10_SPOT,
                rag_status=RAGStatus.GREEN,
                threshold_green=Decimal("0.05"),
                threshold_amber=Decimal("0.10"),
                breach=False,
            ),
            "FX-SPOT-004": ComparisonResult(
                position_id="FX-SPOT-004",
                desk_mark=Decimal("32.45"),
                ipv_price=Decimal("35.12"),
                difference=Decimal("-2.67"),
                difference_pct=Decimal("-7.60"),
                product_category=ProductCategory.EM_SPOT,
                rag_status=RAGStatus.RED,
                threshold_green=Decimal("2.0"),
                threshold_amber=Decimal("5.0"),
                breach=True,
            ),
        }
        results = gen.flag_all(SAMPLE_POSITIONS[:2], comparisons)
        assert results["FX-SPOT-001"] is None  # GREEN
        assert results["FX-SPOT-004"] is not None  # RED
        assert results["FX-SPOT-004"].severity == RAGStatus.RED


# ── Pipeline integration test (mocked upstream) ─────────────────
class TestIPVPipelineMocked:
    @pytest.mark.asyncio
    async def test_pipeline_runs_all_steps(self):
        """Verify the pipeline runs all 8 steps with mocked agents."""
        progress_updates = []

        async def capture_progress(update):
            progress_updates.append(update)

        pipeline = IPVPipeline(db=None, progress_callback=capture_progress)

        # Mock all upstream calls
        with patch.object(pipeline._market_data_gatherer, "gather_all") as mock_gather, \
             patch.object(pipeline._valuation_runner, "price_all") as mock_price, \
             patch.object(pipeline._escalation_manager, "process_exception") as mock_escalate, \
             patch.object(pipeline._resolution_engine, "resolve_all") as mock_resolve, \
             patch.object(pipeline._report_trigger, "trigger_all_reports") as mock_reports:

            # Setup mock returns
            mock_gather.return_value = {
                "FX-SPOT-001": MarketDataSnapshot(
                    position_id="FX-SPOT-001",
                    currency_pair="EUR/USD",
                    spot_rate=Decimal("1.0823"),
                    quality_score=1.0,
                ),
            }

            mock_price.return_value = {
                "FX-SPOT-001": ValuationResult(
                    position_id="FX-SPOT-001",
                    ipv_price=Decimal("1.0823"),
                    pricing_method="median_mid",
                ),
            }

            mock_resolve.return_value = {}
            mock_reports.return_value = []

            request = IPVRunRequest(
                valuation_date=date(2024, 1, 15),
                position_ids=["FX-SPOT-001"],
                triggered_by="test",
            )

            positions = [SAMPLE_POSITIONS[0]]
            summary = await pipeline.run(request, positions)

            assert summary.run_id.startswith("IPV-")
            assert summary.total_positions == 1
            assert summary.status in (IPVRunStatus.COMPLETED, IPVRunStatus.PARTIAL)
            assert len(summary.steps) == 8
            assert any(u.event_type == "RUN_COMPLETED" for u in progress_updates)

    @pytest.mark.asyncio
    async def test_pipeline_handles_step_failure(self):
        """Verify the pipeline continues on step failure (graceful degradation)."""
        pipeline = IPVPipeline(db=None)

        with patch.object(pipeline._market_data_gatherer, "gather_all") as mock_gather:
            mock_gather.side_effect = ConnectionError("Agent 1 unreachable")

            request = IPVRunRequest(
                valuation_date=date(2024, 1, 15),
                triggered_by="test",
            )

            summary = await pipeline.run(request, [SAMPLE_POSITIONS[0]])

            # Pipeline should still complete, but with PARTIAL status
            assert summary.status == IPVRunStatus.PARTIAL
            # First step should be FAILED
            assert summary.steps[0].status == StepStatus.FAILED
            assert len(summary.steps[0].errors) > 0

    @pytest.mark.asyncio
    async def test_pipeline_skip_steps(self):
        """Verify steps can be skipped via request configuration."""
        pipeline = IPVPipeline(db=None)

        with patch.object(pipeline._market_data_gatherer, "gather_all") as mock_gather, \
             patch.object(pipeline._valuation_runner, "price_all") as mock_price, \
             patch.object(pipeline._resolution_engine, "resolve_all") as mock_resolve, \
             patch.object(pipeline._report_trigger, "trigger_all_reports") as mock_reports:

            mock_gather.return_value = {}
            mock_price.return_value = {}
            mock_resolve.return_value = {}
            mock_reports.return_value = []

            request = IPVRunRequest(
                valuation_date=date(2024, 1, 15),
                triggered_by="test",
                skip_steps=[
                    IPVStepName.INVESTIGATE_DISPUTE,
                    IPVStepName.ESCALATE_TO_COMMITTEE,
                    IPVStepName.REPORT,
                ],
            )

            summary = await pipeline.run(request, [SAMPLE_POSITIONS[0]])

            # Skipped steps should have SKIPPED status
            skipped = [s for s in summary.steps if s.status == StepStatus.SKIPPED]
            assert len(skipped) == 3
            skipped_names = {s.step_name for s in skipped}
            assert IPVStepName.INVESTIGATE_DISPUTE in skipped_names
            assert IPVStepName.ESCALATE_TO_COMMITTEE in skipped_names
            assert IPVStepName.REPORT in skipped_names


# ── Position result building tests ───────────────────────────────
class TestPositionResultBuilding:
    @pytest.mark.asyncio
    async def test_build_results_all_seven_positions(self):
        """Verify position results are built correctly for all 7 Excel positions."""
        from app.api.routes import REFERENCE_POSITIONS

        assert len(REFERENCE_POSITIONS) == 7

        # Verify each position's data matches the Excel
        pos_map = {p.position_id: p for p in REFERENCE_POSITIONS}

        assert pos_map["FX-SPOT-001"].currency_pair == "EUR/USD"
        assert pos_map["FX-SPOT-001"].desk_mark == Decimal("1.0825")
        assert pos_map["FX-SPOT-001"].fair_value_level == FairValueLevel.L1

        assert pos_map["FX-SPOT-004"].currency_pair == "USD/TRY"
        assert pos_map["FX-SPOT-004"].desk_mark == Decimal("32.45")
        assert pos_map["FX-SPOT-004"].fair_value_level == FairValueLevel.L2

        assert pos_map["FX-OPT-001"].currency_pair == "EUR/USD"
        assert pos_map["FX-OPT-001"].desk_mark == Decimal("425000")
        assert pos_map["FX-OPT-001"].fair_value_level == FairValueLevel.L3
        assert pos_map["FX-OPT-001"].barrier_type == "DNT"


# ── Product classification of all 7 positions ───────────────────
class TestAllSevenPositions:
    def test_position_categories(self):
        """Verify all 7 positions are classified into correct tolerance buckets."""
        from app.api.routes import REFERENCE_POSITIONS

        categories = {
            p.position_id: classify_product(p.product_type, p.currency_pair)
            for p in REFERENCE_POSITIONS
        }

        assert categories["FX-SPOT-001"] == ProductCategory.G10_SPOT
        assert categories["FX-SPOT-002"] == ProductCategory.G10_SPOT
        assert categories["FX-SPOT-003"] == ProductCategory.G10_SPOT
        assert categories["FX-SPOT-004"] == ProductCategory.EM_SPOT
        assert categories["FX-SPOT-005"] == ProductCategory.EM_SPOT
        assert categories["FX-FWD-001"] == ProductCategory.FX_FORWARD
        assert categories["FX-OPT-001"] == ProductCategory.FX_OPTION

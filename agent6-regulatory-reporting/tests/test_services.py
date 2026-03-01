"""Tests for regulatory reporting services."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.schemas import (
    AVABreakdown,
    FairValueLevel,
    Pillar3Table32,
    PRA110SectionD,
    ReportStatus,
)


class TestPillar3Reporter:
    """Tests for Pillar3Reporter service."""

    @pytest.mark.asyncio
    async def test_generate_table_3_2_with_data(self):
        """Test Table 3.2 generation with AVA data."""
        from app.services.pillar3 import Pillar3Reporter

        # Mock database session
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
        mock_db.scalar_one_or_none = MagicMock(return_value=None)

        reporter = Pillar3Reporter(mock_db)

        # Mock _get_all_avas
        reporter._get_all_avas = AsyncMock(return_value=[{
            "mpu": Decimal("1000000"),
            "close_out": Decimal("500000"),
            "model_risk": Decimal("750000"),
            "credit_spreads": Decimal("250000"),
            "funding": Decimal("300000"),
            "concentration": Decimal("200000"),
            "admin": Decimal("100000"),
        }])

        # Mock _get_cet1
        reporter._get_cet1 = AsyncMock(return_value=Decimal("50000000000"))

        result = await reporter._generate_table_3_2(date(2024, 3, 31))

        assert result is not None
        assert "Market Price Uncertainty" in result.breakdown
        assert result.breakdown["Market Price Uncertainty"] == Decimal("1000000")

    @pytest.mark.asyncio
    async def test_generate_table_3_2_empty_data(self):
        """Test Table 3.2 with no AVA data."""
        from app.services.pillar3 import Pillar3Reporter

        mock_db = AsyncMock()
        reporter = Pillar3Reporter(mock_db)

        # Mock empty AVAs
        reporter._get_all_avas = AsyncMock(return_value=[])
        reporter._get_cet1 = AsyncMock(return_value=Decimal("50000000000"))

        result = await reporter._generate_table_3_2(date(2024, 3, 31))

        assert result is not None
        assert result.total_ava == "€0"
        assert result.as_pct_of_cet1 == "0.00%"


class TestIFRS13Reporter:
    """Tests for IFRS13Reporter service."""

    def test_classify_position_level1(self):
        """Test Level 1 classification for equities."""
        from app.services.ifrs13 import IFRS13Reporter

        mock_db = AsyncMock()
        reporter = IFRS13Reporter(mock_db)

        position = {"product_type": "EQUITY", "asset_class": "EQUITY"}
        result = reporter._classify_position(position)

        assert result == FairValueLevel.LEVEL_1.value

    def test_classify_position_level2(self):
        """Test Level 2 classification for vanilla derivatives."""
        from app.services.ifrs13 import IFRS13Reporter

        mock_db = AsyncMock()
        reporter = IFRS13Reporter(mock_db)

        position = {"product_type": "IRS", "asset_class": "RATES"}
        result = reporter._classify_position(position)

        assert result == FairValueLevel.LEVEL_2.value

    def test_classify_position_level3(self):
        """Test Level 3 classification for exotic options."""
        from app.services.ifrs13 import IFRS13Reporter

        mock_db = AsyncMock()
        reporter = IFRS13Reporter(mock_db)

        position = {"product_type": "EXOTIC_OPTION", "asset_class": "FX"}
        result = reporter._classify_position(position)

        assert result == FairValueLevel.LEVEL_3.value

    def test_valuation_techniques(self):
        """Test valuation technique generation."""
        from app.services.ifrs13 import IFRS13Reporter

        mock_db = AsyncMock()
        reporter = IFRS13Reporter(mock_db)

        techniques = reporter._generate_valuation_techniques()

        assert len(techniques) > 0
        assert any(t.product_type == "Exotic Options" for t in techniques)
        assert any(t.technique == "Monte Carlo Simulation" for t in techniques)


class TestPRA110Reporter:
    """Tests for PRA110Reporter service."""

    @pytest.mark.asyncio
    async def test_generate_section_d(self):
        """Test Section D generation."""
        from app.services.pra110 import PRA110Reporter
        from app.services.pillar3 import Pillar3Reporter

        mock_db = AsyncMock()
        reporter = PRA110Reporter(mock_db)

        # Mock Pillar3Reporter._generate_table_3_2
        mock_table_3_2 = Pillar3Table32(
            total_ava="€1,000,000",
            breakdown={
                "Market Price Uncertainty": Decimal("300000"),
                "Close-Out Costs": Decimal("150000"),
                "Model Risk": Decimal("200000"),
                "Unearned Credit Spreads": Decimal("100000"),
                "Investment & Funding": Decimal("100000"),
                "Concentrated Positions": Decimal("100000"),
                "Future Admin Costs": Decimal("50000"),
            },
            as_pct_of_cet1="2.00%",
        )

        with patch.object(
            reporter.pillar3_reporter, "_generate_table_3_2", return_value=mock_table_3_2
        ):
            section_d = await reporter._generate_section_d(date(2024, 3, 31))

        assert section_d.d010_mpu == Decimal("300000")
        assert section_d.d080_total_ava == Decimal("1000000")

    def test_render_pra110_xml(self):
        """Test XML rendering."""
        from app.services.pra110 import PRA110Reporter

        mock_db = AsyncMock()
        reporter = PRA110Reporter(mock_db)

        section_d = PRA110SectionD(
            d010_mpu=Decimal("100"),
            d020_close_out=Decimal("50"),
            d030_model_risk=Decimal("75"),
            d040_credit_spreads=Decimal("25"),
            d050_funding=Decimal("30"),
            d060_concentration=Decimal("20"),
            d070_admin=Decimal("10"),
            d080_total_ava=Decimal("310"),
        )

        xml = reporter._render_pra110_xml(date(2024, 3, 31), section_d)

        assert "<PRA110" in xml
        assert "<SectionD" in xml
        assert "D010" in xml
        assert "D080" in xml


class TestFRY14QReporter:
    """Tests for FRY14QReporter service."""

    def test_render_csv(self):
        """Test CSV rendering."""
        from app.services.fry14q import FRY14QReporter
        from app.models.schemas import FRY14QScheduleH1, FairValueLevelSummary, VaRMetrics

        mock_db = AsyncMock()
        reporter = FRY14QReporter(mock_db)

        schedule_h1 = FRY14QScheduleH1(
            fair_value_hierarchy=[
                FairValueLevelSummary(
                    level=FairValueLevel.LEVEL_1,
                    count=100,
                    total_fair_value=Decimal("1000000"),
                    percentage_of_total=Decimal("50"),
                ),
                FairValueLevelSummary(
                    level=FairValueLevel.LEVEL_2,
                    count=50,
                    total_fair_value=Decimal("500000"),
                    percentage_of_total=Decimal("25"),
                ),
                FairValueLevelSummary(
                    level=FairValueLevel.LEVEL_3,
                    count=25,
                    total_fair_value=Decimal("500000"),
                    percentage_of_total=Decimal("25"),
                ),
            ],
            prudent_valuation=AVABreakdown(),
            var_metrics=VaRMetrics(
                var_1day_99=Decimal("50000000"),
                var_10day_99=Decimal("158113883"),
            ),
        )

        csv = reporter._render_fr_y14q_csv(date(2024, 3, 31), schedule_h1)

        assert "FR Y-14Q Schedule H.1" in csv
        assert "Fair Value Hierarchy" in csv
        assert "Level 1" in csv
        assert "VaR (1-day, 99%)" in csv

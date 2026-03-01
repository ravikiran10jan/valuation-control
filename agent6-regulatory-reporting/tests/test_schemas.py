"""Tests for Pydantic schemas."""

from datetime import date
from decimal import Decimal

import pytest

from app.models.schemas import (
    AVABreakdown,
    AuditEventType,
    FairValueLevel,
    FairValueLevelSummary,
    Level3Movement,
    Pillar3Table32,
    PRA110SectionD,
    ReportStatus,
    ReportType,
    VaRMetrics,
)


class TestAVABreakdown:
    """Tests for AVABreakdown schema."""

    def test_total_calculation(self):
        """Test that total is calculated correctly."""
        ava = AVABreakdown(
            mpu=Decimal("1000"),
            close_out=Decimal("500"),
            model_risk=Decimal("750"),
            credit_spreads=Decimal("250"),
            funding=Decimal("300"),
            concentration=Decimal("200"),
            admin=Decimal("100"),
        )
        assert ava.total == Decimal("3100")

    def test_default_values(self):
        """Test that defaults are zero."""
        ava = AVABreakdown()
        assert ava.total == Decimal("0")
        assert ava.market_price_uncertainty == Decimal("0")


class TestFairValueLevelSummary:
    """Tests for FairValueLevelSummary schema."""

    def test_valid_level(self):
        """Test valid fair value level."""
        summary = FairValueLevelSummary(
            level=FairValueLevel.LEVEL_1,
            count=100,
            total_fair_value=Decimal("1000000"),
            percentage_of_total=Decimal("50.0"),
        )
        assert summary.level == FairValueLevel.LEVEL_1
        assert summary.count == 100


class TestLevel3Movement:
    """Tests for Level3Movement schema."""

    def test_reconciliation_check(self):
        """Test reconciliation passes when balanced."""
        movement = Level3Movement(
            opening_balance=Decimal("1000"),
            purchases=Decimal("200"),
            issuances=Decimal("0"),
            transfers_in=Decimal("50"),
            transfers_out=Decimal("100"),
            settlements=Decimal("50"),
            pnl=Decimal("100"),
            oci=Decimal("0"),
            closing_balance=Decimal("1200"),  # 1000 + 200 + 50 - 100 - 50 + 100
            check_passed=True,
        )
        expected = (
            movement.opening_balance
            + movement.purchases
            + movement.transfers_in
            - movement.transfers_out
            - movement.settlements
            + movement.pnl
        )
        assert expected == movement.closing_balance


class TestPillar3Table32:
    """Tests for Pillar3Table32 schema."""

    def test_table_creation(self):
        """Test table creation."""
        table = Pillar3Table32(
            total_ava="€1,000,000",
            breakdown={
                "Market Price Uncertainty": Decimal("500000"),
                "Close-Out Costs": Decimal("200000"),
                "Model Risk": Decimal("300000"),
            },
            as_pct_of_cet1="2.50%",
        )
        assert table.total_ava == "€1,000,000"
        assert len(table.breakdown) == 3


class TestPRA110SectionD:
    """Tests for PRA110SectionD schema."""

    def test_section_d_totals(self):
        """Test Section D fields."""
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
        assert section_d.d080_total_ava == Decimal("310")


class TestVaRMetrics:
    """Tests for VaRMetrics schema."""

    def test_var_metrics(self):
        """Test VaR metrics creation."""
        var = VaRMetrics(
            var_1day_99=Decimal("50000000"),
            var_10day_99=Decimal("158113883"),
            stressed_var=Decimal("100000000"),
        )
        assert var.var_1day_99 == Decimal("50000000")
        assert var.stressed_var == Decimal("100000000")

    def test_var_without_stressed(self):
        """Test VaR metrics without stressed VaR."""
        var = VaRMetrics(
            var_1day_99=Decimal("50000000"),
            var_10day_99=Decimal("158113883"),
        )
        assert var.stressed_var is None


class TestEnums:
    """Tests for enum values."""

    def test_fair_value_levels(self):
        """Test fair value level enum."""
        assert FairValueLevel.LEVEL_1.value == "Level 1"
        assert FairValueLevel.LEVEL_2.value == "Level 2"
        assert FairValueLevel.LEVEL_3.value == "Level 3"

    def test_audit_event_types(self):
        """Test audit event type enum."""
        assert AuditEventType.VALUATION_RUN.value == "VALUATION_RUN"
        assert AuditEventType.REPORT_GENERATED.value == "REPORT_GENERATED"
        assert AuditEventType.REPORT_SUBMITTED.value == "REPORT_SUBMITTED"

    def test_report_status(self):
        """Test report status enum."""
        assert ReportStatus.DRAFT.value == "DRAFT"
        assert ReportStatus.APPROVED.value == "APPROVED"
        assert ReportStatus.SUBMITTED.value == "SUBMITTED"

    def test_report_types(self):
        """Test report type enum."""
        assert ReportType.PILLAR3.value == "PILLAR3"
        assert ReportType.IFRS13.value == "IFRS13"
        assert ReportType.PRA110.value == "PRA110"
        assert ReportType.FRY14Q.value == "FRY14Q"

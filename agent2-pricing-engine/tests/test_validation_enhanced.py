"""Tests for the enhanced validation framework.

Covers: severity classification, desk-mark comparison, stale-data
detection, per-asset-class tolerance lookup.
"""

import math
from datetime import datetime, timedelta

import pytest

from app.core.config import AssetClassTolerances, tolerances
from app.pricing.equity_option import EquityOptionPricer
from app.pricing.fx_forward import FXForwardPricer
from app.pricing.fx_vanilla import FXVanillaOptionPricer
from app.validation.framework import ModelValidator, ValidationResult


@pytest.fixture
def validator() -> ModelValidator:
    return ModelValidator()


@pytest.fixture
def equity_pricer() -> EquityOptionPricer:
    return EquityOptionPricer(
        spot=100, strike=100, maturity=1, vol=0.20, r_dom=0.05,
    )


@pytest.fixture
def fwd_pricer() -> FXForwardPricer:
    return FXForwardPricer(
        spot=1.10, r_dom=0.05, r_for=0.03, maturity=1.0, notional=1_000_000,
    )


@pytest.fixture
def vanilla_pricer() -> FXVanillaOptionPricer:
    return FXVanillaOptionPricer(
        spot=1.10, strike=1.10, maturity=1.0, vol=0.10,
        r_dom=0.05, r_for=0.03, notional=1_000_000,
    )


# ── Tolerance lookup ────────────────────────────────────────────────


class TestAssetClassTolerances:
    def test_fx_spot_tolerance(self):
        tol = tolerances.get_tolerance("fx", "spot")
        assert tol == tolerances.fx_spot_bps / 10_000

    def test_fx_forward_tolerance(self):
        tol = tolerances.get_tolerance("fx", "forward")
        assert tol == tolerances.fx_forward_bps / 10_000

    def test_fx_vanilla_tolerance(self):
        tol = tolerances.get_tolerance("fx", "vanilla")
        assert tol == tolerances.fx_vanilla_pct

    def test_fx_barrier_tolerance(self):
        tol = tolerances.get_tolerance("fx", "barrier")
        assert tol == tolerances.fx_barrier_pct

    def test_credit_loan_tolerance(self):
        tol = tolerances.get_tolerance("credit", "loan")
        assert tol == tolerances.credit_loan_pct

    def test_equity_option_tolerance(self):
        tol = tolerances.get_tolerance("equity", "option")
        assert tol == tolerances.equity_option_pct

    def test_fallback_exotic(self):
        tol = tolerances.get_tolerance("unknown", "exotic_widget")
        assert tol == 0.05

    def test_fallback_vanilla(self):
        tol = tolerances.get_tolerance("unknown", "vanilla_widget")
        assert tol == 0.02


# ── Severity classification ─────────────────────────────────────────


class TestSeverityClassification:
    def test_green_within_tolerance(self):
        assert ModelValidator.classify_severity(0.01, 0.02) == "GREEN"

    def test_amber_between_1x_and_2x(self):
        assert ModelValidator.classify_severity(0.03, 0.02) == "AMBER"

    def test_red_above_2x(self):
        assert ModelValidator.classify_severity(0.05, 0.02) == "RED"

    def test_exact_tolerance_is_green(self):
        assert ModelValidator.classify_severity(0.02, 0.02) == "GREEN"


# ── Desk mark comparison ────────────────────────────────────────────


class TestDeskMarkComparison:
    def test_desk_mark_pass(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        fair_value = equity_pricer.price().fair_value
        desk_mark = fair_value * 1.005  # 0.5% off -> within 2% vanilla tolerance
        result = validator.validate(equity_pricer, desk_mark=desk_mark)
        assert result.checks["desk_mark_comparison"] is True
        assert result.severity == "GREEN"

    def test_desk_mark_fail_amber(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        fair_value = equity_pricer.price().fair_value
        desk_mark = fair_value * 1.03  # 3% off -> AMBER (> 2% but < 4%)
        result = validator.validate(equity_pricer, desk_mark=desk_mark)
        assert result.checks["desk_mark_comparison"] is False
        assert result.severity in ("AMBER", "RED")

    def test_desk_mark_fail_red(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        fair_value = equity_pricer.price().fair_value
        desk_mark = fair_value * 1.10  # 10% off -> RED
        result = validator.validate(equity_pricer, desk_mark=desk_mark)
        assert result.checks["desk_mark_comparison"] is False
        assert result.severity == "RED"

    def test_desk_mark_details_populated(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        fair_value = equity_pricer.price().fair_value
        result = validator.validate(equity_pricer, desk_mark=fair_value * 1.01)
        details = result.details["desk_mark_comparison"]
        assert "vc_fair_value" in details
        assert "desk_mark" in details
        assert "relative_diff_pct" in details
        assert "severity" in details


# ── Asset-class-specific validation ─────────────────────────────────


class TestAssetClassValidation:
    def test_fx_vanilla_tolerance_used(self, validator: ModelValidator, vanilla_pricer: FXVanillaOptionPricer):
        fair_value = vanilla_pricer.price().fair_value
        # Within FX vanilla tolerance (2%)
        desk_mark = fair_value * 1.01
        result = validator.validate(
            vanilla_pricer, desk_mark=desk_mark,
            asset_class="fx", product_type="vanilla",
        )
        assert result.checks["desk_mark_comparison"] is True

    def test_fx_forward_tolerance_used(self, validator: ModelValidator, fwd_pricer: FXForwardPricer):
        fair_value = fwd_pricer.price().fair_value
        # FX forward tolerance is 10bps = 0.001
        # A 0.05% deviation should fail this tight tolerance
        desk_mark = fair_value * 1.005
        result = validator.validate(
            fwd_pricer, desk_mark=desk_mark,
            asset_class="fx", product_type="forward",
        )
        # 0.5% > 0.1% tolerance -> should fail
        assert result.checks["desk_mark_comparison"] is False


# ── Stale data detection ────────────────────────────────────────────


class TestStaleDataDetection:
    def test_fresh_data_passes(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        now = datetime.utcnow()
        result = validator.validate(equity_pricer, data_timestamp=now)
        assert result.checks["data_freshness"] is True
        assert result.details["data_freshness"]["is_fresh"] is True

    def test_stale_data_fails(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        old = datetime.utcnow() - timedelta(seconds=600)
        result = validator.validate(equity_pricer, data_timestamp=old)
        assert result.checks["data_freshness"] is False

    def test_stale_data_sets_amber(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        old = datetime.utcnow() - timedelta(seconds=600)
        result = validator.validate(equity_pricer, data_timestamp=old)
        assert result.severity in ("AMBER", "RED")

    def test_iso_string_timestamp(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        now_str = datetime.utcnow().isoformat()
        result = validator.validate(equity_pricer, data_timestamp=now_str)
        assert "data_freshness" in result.checks


# ── Result structure ────────────────────────────────────────────────


class TestValidationResultStructure:
    def test_to_dict_has_severity(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        result = validator.validate(equity_pricer)
        d = result.to_dict()
        assert "severity" in d
        assert d["severity"] in ("GREEN", "AMBER", "RED")

    def test_failed_checks_list(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        result = validator.validate(equity_pricer, benchmark_value=999999.0)
        assert "benchmark" in result.failed_checks
        assert result.status == "FAILED"

    def test_all_checks_are_python_bools(self, validator: ModelValidator, equity_pricer: EquityOptionPricer):
        result = validator.validate(equity_pricer, benchmark_value=equity_pricer.price().fair_value)
        for k, v in result.checks.items():
            assert type(v) is bool, f"Check '{k}' is {type(v)}, expected bool"

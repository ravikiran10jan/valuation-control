"""Tests for the Model Validation framework."""

import pytest

from app.pricing.equity_option import EquityOptionPricer
from app.pricing.fx_barrier import FXBarrierPricer
from app.validation.framework import ModelValidator


@pytest.fixture
def validator() -> ModelValidator:
    return ModelValidator()


@pytest.fixture
def valid_equity_pricer() -> EquityOptionPricer:
    return EquityOptionPricer(
        spot=100, strike=100, maturity=1, vol=0.20, r_dom=0.05,
    )


@pytest.fixture
def valid_fx_pricer() -> FXBarrierPricer:
    return FXBarrierPricer(
        spot=1.10, lower_barrier=1.05, upper_barrier=1.15,
        maturity=0.5, notional=1e6, vol=0.10, r_dom=0.05, r_for=0.03,
    )


class TestValidationFramework:
    def test_passes_for_valid_pricer(self, validator: ModelValidator, valid_equity_pricer: EquityOptionPricer):
        result = validator.validate(valid_equity_pricer)
        assert result.status == "VALIDATED"
        assert result.checks["input_validation"] is True
        assert result.checks["price_finite"] is True
        assert result.checks["greeks_finite"] is True

    def test_benchmark_pass(self, validator: ModelValidator, valid_equity_pricer: EquityOptionPricer):
        # Get the BS price and use it as benchmark (should pass)
        bs_price = valid_equity_pricer.price_black_scholes()
        result = validator.validate(valid_equity_pricer, benchmark_value=bs_price)
        assert result.checks["benchmark"] is True

    def test_benchmark_fail(self, validator: ModelValidator, valid_equity_pricer: EquityOptionPricer):
        # Way off benchmark
        result = validator.validate(valid_equity_pricer, benchmark_value=999.0)
        assert result.checks["benchmark"] is False
        assert "benchmark" in result.failed_checks

    def test_cross_method_consistency(self, validator: ModelValidator, valid_fx_pricer: FXBarrierPricer):
        result = validator.validate(valid_fx_pricer, is_exotic=True)
        assert "cross_method_consistency" in result.checks

    def test_non_negative_price(self, validator: ModelValidator, valid_equity_pricer: EquityOptionPricer):
        result = validator.validate(valid_equity_pricer)
        assert result.checks["non_negative_price"] is True

    def test_result_dict(self, validator: ModelValidator, valid_equity_pricer: EquityOptionPricer):
        result = validator.validate(valid_equity_pricer)
        d = result.to_dict()
        assert "status" in d
        assert "checks" in d
        assert "failed_checks" in d

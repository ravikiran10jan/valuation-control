"""API routes for the pricing engine."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import tolerances
from app.models.schemas import (
    BermudanSwaptionRequest,
    CommoditiesBasketRequest,
    DistressedLoanRequest,
    EquityOptionRequest,
    FXBarrierRequest,
    FXForwardRequest,
    FXForwardResponse,
    FXSpotRequest,
    FXSpotResponse,
    FXVanillaOptionRequest,
    GreeksCalculateRequest,
    GreeksCalculateResponse,
    GreeksLimitsCheckRequest,
    GreeksLimitsCheckResponse,
    GreeksLimitsDefinitionResponse,
    GreeksVarianceRequest,
    GreeksVarianceResponse,
    PnLAttributionRequest,
    PnLAttributionResponse,
    PricingResponse,
    ToleranceLookupRequest,
    ToleranceLookupResponse,
    ValidationRequest,
    ValidationResponse,
    VolSurfaceRequest,
    VolSurfaceResponse,
)
from app.pricing.commodities_basket import CommoditiesBasketPricer
from app.pricing.credit_loan import DistressedLoanPricer
from app.pricing.equity_option import EquityOptionPricer
from app.pricing.fx_barrier import FXBarrierPricer
from app.pricing.fx_forward import FXForwardPricer
from app.pricing.fx_spot import FXSpotPricer
from app.pricing.fx_vanilla import FXVanillaOptionPricer
from app.pricing.rates_swaption import HullWhitePricer
from app.pricing.vol_surface import VolSurfaceInterpolator
from app.validation.framework import ModelValidator

router = APIRouter(prefix="/pricing", tags=["pricing"])
greeks_router = APIRouter(prefix="/greeks", tags=["greeks"])


# ── FX Spot ─────────────────────────────────────────────────────
@router.post("/fx-spot", response_model=FXSpotResponse)
async def price_fx_spot(req: FXSpotRequest) -> FXSpotResponse:
    try:
        from datetime import datetime

        ref_time = None
        if req.reference_time:
            try:
                ref_time = datetime.fromisoformat(req.reference_time)
            except ValueError:
                pass

        pricer = FXSpotPricer(
            currency_pair=req.currency_pair,
            quotes=req.quotes,
            stale_seconds=req.stale_seconds,
            outlier_threshold_bps=req.outlier_threshold_bps,
            reference_time=ref_time,
        )
        result = pricer.compute_mid_market()
        return FXSpotResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── FX Forward ──────────────────────────────────────────────────
@router.post("/fx-forward", response_model=FXForwardResponse)
async def price_fx_forward(req: FXForwardRequest) -> FXForwardResponse:
    try:
        pricer = FXForwardPricer(
            spot=req.spot,
            r_dom=req.r_dom,
            r_for=req.r_for,
            maturity=req.maturity,
            notional=req.notional,
            strike=req.strike,
            currency_pair=req.currency_pair,
            currency=req.currency,
            compounding=req.compounding,
        )
        result = pricer.price()
        fwd = pricer.forward_rate()
        pts = pricer.forward_points_pips()
        term_struct = pricer.term_structure() if req.strike is None else None

        return FXForwardResponse(
            fair_value=round(result.fair_value, 6),
            method=result.method,
            forward_rate=round(fwd, 6),
            forward_points_pips=round(pts, 2),
            currency_pair=pricer.currency_pair,
            greeks={k: round(v, 2) for k, v in result.greeks.items()},
            term_structure=term_struct,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── FX Vanilla Option ──────────────────────────────────────────
@router.post("/fx-vanilla-option", response_model=PricingResponse)
async def price_fx_vanilla_option(req: FXVanillaOptionRequest) -> PricingResponse:
    try:
        pricer = FXVanillaOptionPricer(
            spot=req.spot,
            strike=req.strike,
            maturity=req.maturity,
            vol=req.vol,
            r_dom=req.r_dom,
            r_for=req.r_for,
            notional=req.notional,
            option_type=req.option_type,
            currency_pair=req.currency_pair,
            currency=req.currency,
        )
        result = pricer.price()
        return PricingResponse(**result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── FX Barrier ──────────────────────────────────────────────────
@router.post("/fx-barrier", response_model=PricingResponse)
async def price_fx_barrier(req: FXBarrierRequest) -> PricingResponse:
    try:
        pricer = FXBarrierPricer(
            spot=req.spot,
            lower_barrier=req.lower_barrier,
            upper_barrier=req.upper_barrier,
            maturity=req.maturity,
            notional=req.notional,
            vol=req.vol,
            r_dom=req.r_dom,
            r_for=req.r_for,
            barrier_type=req.barrier_type,
            currency=req.currency,
            mc_paths=req.mc_paths,
        )
        result = pricer.price()
        return PricingResponse(**result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Bermudan Swaption ──────────────────────────────────────────
@router.post("/bermudan-swaption", response_model=PricingResponse)
async def price_bermudan_swaption(req: BermudanSwaptionRequest) -> PricingResponse:
    try:
        pricer = HullWhitePricer(
            notional=req.notional,
            fixed_rate=req.fixed_rate,
            exercise_dates_years=req.exercise_dates_years,
            swap_tenor=req.swap_tenor,
            yield_curve=req.yield_curve,
            kappa=req.kappa,
            sigma=req.sigma,
            pay_frequency=req.pay_frequency,
            currency=req.currency,
        )
        result = pricer.price()
        return PricingResponse(**result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Distressed Loan ────────────────────────────────────────────
@router.post("/distressed-loan", response_model=PricingResponse)
async def price_distressed_loan(req: DistressedLoanRequest) -> PricingResponse:
    try:
        pricer = DistressedLoanPricer(
            notional=req.notional,
            collateral=req.collateral,
            financials=req.financials,
            time_horizon=req.time_horizon,
            currency=req.currency,
            scenario_weights=req.scenario_weights,
            discount_rate=req.discount_rate,
        )
        result = pricer.price()
        return PricingResponse(**result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Commodities Basket ──────────────────────────────────────────
@router.post("/commodities-basket", response_model=PricingResponse)
async def price_commodities_basket(req: CommoditiesBasketRequest) -> PricingResponse:
    try:
        pricer = CommoditiesBasketPricer(
            asset_names=req.asset_names,
            spots=req.spots,
            vols=req.vols,
            drifts=req.drifts,
            correlation_matrix=req.correlation_matrix,
            barriers=req.barriers,
            maturity=req.maturity,
            notional=req.notional,
            risk_free_rate=req.risk_free_rate,
            currency=req.currency,
            mc_paths=req.mc_paths,
        )
        result = pricer.price()
        return PricingResponse(**result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Equity Option ──────────────────────────────────────────────
@router.post("/equity-option", response_model=PricingResponse)
async def price_equity_option(req: EquityOptionRequest) -> PricingResponse:
    try:
        pricer = EquityOptionPricer(
            spot=req.spot,
            strike=req.strike,
            maturity=req.maturity,
            vol=req.vol,
            r_dom=req.r_dom,
            dividend_yield=req.dividend_yield,
            option_type=req.option_type,
            exercise_style=req.exercise_style,
            notional=req.notional,
            currency=req.currency,
        )
        result = pricer.price()
        return PricingResponse(**result.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Vol Surface ─────────────────────────────────────────────────
@router.post("/vol-surface", response_model=VolSurfaceResponse)
async def interpolate_vol_surface(req: VolSurfaceRequest) -> VolSurfaceResponse:
    try:
        interp = VolSurfaceInterpolator(
            deltas=req.deltas,
            vols=req.vols,
            forward=req.forward,
            maturity=req.maturity,
            beta=req.beta,
        )
        surface = interp.build_surface(req.target_deltas)
        return VolSurfaceResponse(**surface)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Model Validation ───────────────────────────────────────────
_PRICER_MAP = {
    "fx_spot": lambda p: FXSpotPricer(**p),
    "fx_forward": lambda p: FXForwardPricer(**p),
    "fx_vanilla": lambda p: FXVanillaOptionPricer(**p),
    "fx_barrier": lambda p: FXBarrierPricer(**p),
    "bermudan_swaption": lambda p: HullWhitePricer(**p),
    "credit_loan": lambda p: DistressedLoanPricer(**p),
    "commodities_basket": lambda p: CommoditiesBasketPricer(**p),
    "equity_option": lambda p: EquityOptionPricer(**p),
}


@router.post("/validate", response_model=ValidationResponse)
async def validate_model(req: ValidationRequest) -> ValidationResponse:
    factory = _PRICER_MAP.get(req.model_name)
    if factory is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model '{req.model_name}'. "
            f"Supported: {list(_PRICER_MAP.keys())}",
        )
    try:
        pricer = factory(req.position)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot build pricer: {e}")

    validator = ModelValidator()
    result = validator.validate(
        pricer,
        benchmark_value=req.benchmark_value,
        desk_mark=req.desk_mark,
        is_exotic=req.is_exotic,
        asset_class=req.asset_class,
        product_type=req.product_type,
    )
    return ValidationResponse(**result.to_dict())


# ── Tolerance Lookup ────────────────────────────────────────────
@router.post("/tolerances", response_model=ToleranceLookupResponse)
async def lookup_tolerance(req: ToleranceLookupRequest) -> ToleranceLookupResponse:
    tol = tolerances.get_tolerance(req.asset_class, req.product_type)
    return ToleranceLookupResponse(
        asset_class=req.asset_class,
        product_type=req.product_type,
        tolerance_pct=round(tol * 100, 4),
        green_threshold=round(tol * 100, 4),
        amber_threshold=round(tol * tolerances.amber_threshold * 100, 4),
    )


# ══════════════════════════════════════════════════════════════════
# Greeks & PnL Attribution Endpoints
# ══════════════════════════════════════════════════════════════════

# Pricer map for Greeks calculation (subset of models that support Greeks)
_GREEKS_PRICER_MAP = {
    "fx_vanilla": lambda p: FXVanillaOptionPricer(**p),
    "fx_barrier": lambda p: FXBarrierPricer(**p),
    "fx_forward": lambda p: FXForwardPricer(**p),
    "equity_option": lambda p: EquityOptionPricer(**p),
    "bermudan_swaption": lambda p: HullWhitePricer(**p),
}


@greeks_router.post("/calculate", response_model=GreeksCalculateResponse)
async def calculate_greeks(req: GreeksCalculateRequest) -> GreeksCalculateResponse:
    """Calculate all Greeks for a position using finite-difference bumping.

    Supports: fx_vanilla, fx_barrier, fx_forward, equity_option, bermudan_swaption.
    """
    from app.greeks.calculator import GreeksCalculator

    factory = _GREEKS_PRICER_MAP.get(req.model_name)
    if factory is None:
        raise HTTPException(
            status_code=400,
            detail=f"Model '{req.model_name}' does not support Greeks calculation. "
            f"Supported: {list(_GREEKS_PRICER_MAP.keys())}",
        )

    try:
        pricer = factory(req.position)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Cannot build pricer: {e}")

    try:
        # Use the pricer's own calculate_greeks if available
        if hasattr(pricer, "calculate_greeks"):
            greeks = pricer.calculate_greeks()
        else:
            # Fallback to generic finite-difference calculator
            price_fn = pricer.price_analytical if hasattr(pricer, "price_analytical") else pricer.price
            calc = GreeksCalculator(pricer, price_fn)
            greeks = calc.all(
                spot_attr=req.spot_attr,
                vol_attr=req.vol_attr,
                maturity_attr=req.maturity_attr,
                rate_attr=req.rate_attr,
            )

        return GreeksCalculateResponse(
            greeks={k: round(v, 6) for k, v in greeks.items()},
            model_name=req.model_name,
            method="finite_difference",
            diagnostics={
                "position_params": list(req.position.keys()),
                "bump_attributes": {
                    "spot": req.spot_attr,
                    "vol": req.vol_attr,
                    "maturity": req.maturity_attr,
                    "rate": req.rate_attr,
                },
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Greeks calculation failed: {e}")


@greeks_router.post("/pnl-attribution", response_model=PnLAttributionResponse)
async def pnl_attribution(req: PnLAttributionRequest) -> PnLAttributionResponse:
    """Full P&L decomposition into risk-factor components.

    Breaks down total P&L into Delta, Gamma, Vega, Theta, Rho,
    Cross-Gamma, and Unexplained components using Taylor expansion
    of the option value function.
    """
    from app.greeks.pnl_attribution import (
        GreeksSnapshot,
        MarketDataSnapshot,
        PnLAttributionEngine,
    )

    try:
        greeks = GreeksSnapshot(
            delta=req.greeks.delta,
            gamma=req.greeks.gamma,
            vega=req.greeks.vega,
            theta=req.greeks.theta,
            rho=req.greeks.rho,
            vanna=req.greeks.vanna,
            volga=req.greeks.volga,
            charm=req.greeks.charm,
        )

        md_t0 = MarketDataSnapshot(
            spot=req.market_data_t0.spot,
            vol=req.market_data_t0.vol,
            r_dom=req.market_data_t0.r_dom,
            r_for=req.market_data_t0.r_for,
            observation_date=req.market_data_t0.observation_date,
        )

        md_t1 = MarketDataSnapshot(
            spot=req.market_data_t1.spot,
            vol=req.market_data_t1.vol,
            r_dom=req.market_data_t1.r_dom,
            r_for=req.market_data_t1.r_for,
            observation_date=req.market_data_t1.observation_date,
        )

        engine = PnLAttributionEngine(
            notional=req.notional,
            pip_size=req.pip_size,
        )

        # Use barrier-specific decomposition if barrier params provided
        if req.lower_barrier is not None and req.upper_barrier is not None:
            result = engine.decompose_barrier(
                greeks=greeks,
                market_data_t0=md_t0,
                market_data_t1=md_t1,
                total_pnl=req.total_pnl,
                lower_barrier=req.lower_barrier,
                upper_barrier=req.upper_barrier,
                time_elapsed_days=req.time_elapsed_days,
            )
        else:
            result = engine.decompose(
                greeks=greeks,
                market_data_t0=md_t0,
                market_data_t1=md_t1,
                total_pnl=req.total_pnl,
                time_elapsed_days=req.time_elapsed_days,
            )

        return PnLAttributionResponse(**result.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PnL attribution failed: {e}")


@greeks_router.post("/variance-analysis", response_model=GreeksVarianceResponse)
async def variance_analysis(req: GreeksVarianceRequest) -> GreeksVarianceResponse:
    """Compare desk Greeks vs VC Greeks and identify root causes.

    Flags variances exceeding thresholds:
    - Delta > 5%, Gamma > 10%, Vega > 5%, Theta > 5%

    Root cause categories: Market Data Timing (45%),
    Vol Surface Diff (25%), Trade Pop Mismatch (15%),
    Calc Method (8%), Model Version (4%), Rounding (2%), Other (1%).
    """
    from app.greeks.variance_analysis import GreeksVarianceAnalyzer

    try:
        analyzer = GreeksVarianceAnalyzer(thresholds=req.thresholds)
        result = analyzer.analyze(
            desk_greeks=req.desk_greeks,
            vc_greeks=req.vc_greeks,
            position_id=req.position_id,
            additional_context=req.additional_context,
        )

        return GreeksVarianceResponse(**result.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Variance analysis failed: {e}"
        )


@greeks_router.post("/limits-check", response_model=GreeksLimitsCheckResponse)
async def limits_check(req: GreeksLimitsCheckRequest) -> GreeksLimitsCheckResponse:
    """Check current Greek positions against limits.

    Alert levels: <70% GREEN, 70-90% AMBER, >90% RED.
    Breach handling: 100-110% email, 110-125% reduce in 2hrs,
    125-150% immediate hedge, >150% STOP.
    """
    from app.greeks.limits import (
        GreekLimit,
        GreekLimitSet,
        GreeksLimitsMonitor,
        get_default_barrier_limits,
        get_default_fx_limits,
    )

    try:
        # Select default limit set based on type
        if req.limit_type == "barrier":
            limit_set = get_default_barrier_limits(req.currency_pair)
        else:
            limit_set = get_default_fx_limits(req.currency_pair)

        # Apply custom limit overrides if provided
        if req.custom_limits:
            for greek_name, limit_value in req.custom_limits.items():
                limit_set.limits[greek_name] = GreekLimit(
                    greek_name=greek_name,
                    limit_value=limit_value,
                    unit="USD",
                    description=f"Custom limit for {greek_name}",
                )

        monitor = GreeksLimitsMonitor(limit_set=limit_set)
        result = monitor.check_all_greeks(
            greeks=req.greeks,
            desk_name=req.desk_name,
            currency_pair=req.currency_pair,
        )

        return GreeksLimitsCheckResponse(**result.to_dict())
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Limits check failed: {e}"
        )


@greeks_router.get("/limits", response_model=GreeksLimitsDefinitionResponse)
async def get_limits(
    currency_pair: str = "EURUSD",
    limit_type: str = "fx",
) -> GreeksLimitsDefinitionResponse:
    """Get current Greek limit definitions.

    Returns limits, alert thresholds, and breach action escalation rules.
    """
    from app.greeks.limits import (
        GreeksLimitsMonitor,
        get_default_barrier_limits,
        get_default_fx_limits,
    )

    try:
        if limit_type == "barrier":
            limit_set = get_default_barrier_limits(currency_pair)
        else:
            limit_set = get_default_fx_limits(currency_pair)

        monitor = GreeksLimitsMonitor(limit_set=limit_set)
        definitions = monitor.get_limit_definitions()

        return GreeksLimitsDefinitionResponse(**definitions)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve limits: {e}"
        )

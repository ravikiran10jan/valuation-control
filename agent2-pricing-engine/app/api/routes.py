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

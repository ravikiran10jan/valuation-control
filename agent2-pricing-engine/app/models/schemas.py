"""Pydantic schemas for pricing-engine API requests and responses."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Common response ─────────────────────────────────────────────
class PricingResponse(BaseModel):
    fair_value: float
    method: str
    currency: str
    greeks: dict[str, float] = {}
    diagnostics: dict[str, Any] = {}
    methods: dict[str, float] = {}


# ── FX Spot ─────────────────────────────────────────────────────
class FXSpotRequest(BaseModel):
    currency_pair: str = Field(..., description="e.g. EURUSD")
    quotes: list[dict[str, Any]] = Field(
        ..., min_length=1,
        description="List of {source, bid, ask, timestamp, currency_pair}",
    )
    stale_seconds: int = Field(300, ge=1)
    outlier_threshold_bps: float = Field(50.0, ge=0)
    reference_time: Optional[str] = None


class FXSpotResponse(BaseModel):
    mid_rate: Optional[float]
    sources_used: int
    sources: list[str] = []
    average_spread_bps: Optional[float] = None
    quality: str
    filters_applied: dict[str, int] = {}
    individual_mids: dict[str, float] = {}


# ── FX Forward ──────────────────────────────────────────────────
class FXForwardRequest(BaseModel):
    spot: float = Field(..., gt=0)
    r_dom: float = Field(..., description="Domestic risk-free rate")
    r_for: float = Field(..., description="Foreign risk-free rate")
    maturity: float = Field(..., ge=0, description="Time to delivery in years")
    notional: float = Field(1_000_000, gt=0)
    strike: Optional[float] = Field(None, description="Contracted forward rate for MTM")
    currency_pair: str = "EURUSD"
    currency: str = "USD"
    compounding: str = Field("continuous", description="continuous or simple")


class FXForwardResponse(BaseModel):
    fair_value: float
    method: str
    forward_rate: float
    forward_points_pips: float
    currency_pair: str
    greeks: dict[str, float] = {}
    term_structure: Optional[list[dict[str, float]]] = None


# ── FX Vanilla Option ──────────────────────────────────────────
class FXVanillaOptionRequest(BaseModel):
    spot: float = Field(..., gt=0)
    strike: float = Field(..., gt=0)
    maturity: float = Field(..., gt=0, description="Years to expiry")
    vol: float = Field(..., gt=0, description="Implied vol (decimal)")
    r_dom: float
    r_for: float
    notional: float = Field(1_000_000, gt=0)
    option_type: str = Field("call", description="call or put")
    currency_pair: str = "EURUSD"
    currency: str = "USD"


# ── FX Barrier ──────────────────────────────────────────────────
class FXBarrierRequest(BaseModel):
    spot: float = Field(..., gt=0, description="Current FX spot rate")
    lower_barrier: float = Field(..., gt=0)
    upper_barrier: float = Field(..., gt=0)
    maturity: float = Field(..., gt=0, description="Time to expiry in years")
    notional: float = Field(..., gt=0)
    vol: float = Field(..., gt=0, description="Implied volatility (decimal)")
    r_dom: float = Field(..., description="Domestic risk-free rate")
    r_for: float = Field(..., description="Foreign risk-free rate")
    barrier_type: str = Field("DNT", description="DNT, DOT, KI, KO")
    currency: str = "USD"
    mc_paths: int = Field(50_000, ge=1000)


# ── Bermudan Swaption ──────────────────────────────────────────
class BermudanSwaptionRequest(BaseModel):
    notional: float = Field(..., gt=0)
    fixed_rate: float = Field(..., description="Strike coupon rate")
    exercise_dates_years: list[float] = Field(..., min_length=1)
    swap_tenor: float = Field(..., gt=0)
    yield_curve: list[tuple[float, float]] = Field(
        ..., description="List of (tenor, zero_rate) pairs"
    )
    kappa: float = Field(..., gt=0, description="Mean-reversion speed")
    sigma: float = Field(..., gt=0, description="Short-rate vol")
    pay_frequency: float = Field(0.5, gt=0)
    currency: str = "USD"


# ── Distressed Loan ────────────────────────────────────────────
class DistressedLoanRequest(BaseModel):
    notional: float = Field(..., gt=0)
    collateral: dict[str, float] = Field(
        ..., description="Asset type -> value mapping"
    )
    financials: dict[str, float] = Field(
        ..., description="Must contain 'ebitda'; may contain 'total_debt'"
    )
    time_horizon: float = Field(1.5, gt=0)
    currency: str = "USD"
    scenario_weights: Optional[dict[str, float]] = None
    discount_rate: float = 0.15


# ── Commodities Basket ──────────────────────────────────────────
class CommoditiesBasketRequest(BaseModel):
    asset_names: list[str] = Field(..., min_length=1)
    spots: list[float]
    vols: list[float]
    drifts: list[float]
    correlation_matrix: list[list[float]]
    barriers: list[float]
    maturity: float = Field(..., gt=0)
    notional: float = Field(..., gt=0)
    risk_free_rate: float = 0.05
    currency: str = "USD"
    mc_paths: int = Field(50_000, ge=1000)


# ── Equity Option ──────────────────────────────────────────────
class EquityOptionRequest(BaseModel):
    spot: float = Field(..., gt=0)
    strike: float = Field(..., gt=0)
    maturity: float = Field(..., gt=0)
    vol: float = Field(..., gt=0)
    r_dom: float
    dividend_yield: float = 0.0
    option_type: str = Field("call", description="call or put")
    exercise_style: str = Field("european", description="european or american")
    notional: float = 1.0
    currency: str = "USD"


# ── Vol Surface ─────────────────────────────────────────────────
class VolSurfaceRequest(BaseModel):
    deltas: list[float]
    vols: list[float]
    forward: float = Field(..., gt=0)
    maturity: float = Field(..., gt=0)
    beta: float = Field(0.5, ge=0, le=1)
    target_deltas: Optional[list[float]] = None


class VolSurfaceResponse(BaseModel):
    cubic_spline: dict[str, float]
    sabr: dict[str, float]
    sabr_params: dict[str, float]


# ── Validation ──────────────────────────────────────────────────
class ValidationRequest(BaseModel):
    model_name: str = Field(
        ...,
        description=(
            "fx_spot | fx_forward | fx_vanilla | fx_barrier | "
            "bermudan_swaption | credit_loan | commodities_basket | equity_option"
        ),
    )
    position: dict[str, Any]
    benchmark_value: Optional[float] = None
    desk_mark: Optional[float] = None
    is_exotic: bool = False
    asset_class: Optional[str] = None
    product_type: Optional[str] = None


class ValidationResponse(BaseModel):
    status: str
    severity: str
    checks: dict[str, bool]
    details: dict[str, Any]
    failed_checks: list[str]


# ── Tolerance lookup ────────────────────────────────────────────
class ToleranceLookupRequest(BaseModel):
    asset_class: str
    product_type: str = "vanilla"


class ToleranceLookupResponse(BaseModel):
    asset_class: str
    product_type: str
    tolerance_pct: float
    green_threshold: float
    amber_threshold: float

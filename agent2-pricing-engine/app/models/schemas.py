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


# ── Greeks Calculation ─────────────────────────────────────────
class GreeksCalculateRequest(BaseModel):
    """Request to calculate all Greeks for a position."""

    model_name: str = Field(
        ...,
        description=(
            "fx_vanilla | fx_barrier | fx_forward | "
            "equity_option | bermudan_swaption"
        ),
    )
    position: dict[str, Any] = Field(
        ..., description="Pricer parameters (same as used for pricing)"
    )
    spot_attr: str = Field("spot", description="Attribute name for spot price")
    vol_attr: str = Field("vol", description="Attribute name for volatility")
    maturity_attr: str = Field("maturity", description="Attribute name for time to expiry")
    rate_attr: str = Field("r_dom", description="Attribute name for domestic rate")


class GreeksCalculateResponse(BaseModel):
    """Response containing calculated Greeks."""

    greeks: dict[str, float]
    model_name: str
    method: str = "finite_difference"
    diagnostics: dict[str, Any] = {}


# ── PnL Attribution ────────────────────────────────────────────
class MarketDataSnapshotSchema(BaseModel):
    """Market data at a point in time."""

    spot: float = Field(..., gt=0, description="FX spot rate")
    vol: float = Field(..., gt=0, description="Implied volatility (decimal)")
    r_dom: float = Field(..., description="Domestic risk-free rate")
    r_for: float = Field(..., description="Foreign risk-free rate")
    observation_date: Optional[str] = Field(
        None, description="ISO date string (YYYY-MM-DD)"
    )


class GreeksSnapshotSchema(BaseModel):
    """Greeks values at a point in time."""

    delta: float = Field(0.0, description="dV/dS")
    gamma: float = Field(0.0, description="d2V/dS2")
    vega: float = Field(0.0, description="dV/d(sigma)")
    theta: float = Field(0.0, description="dV/dt")
    rho: float = Field(0.0, description="dV/dr")
    vanna: float = Field(0.0, description="d2V/(dS*d_sigma)")
    volga: float = Field(0.0, description="d2V/d_sigma2")
    charm: float = Field(0.0, description="d2V/(dS*dt)")


class PnLAttributionRequest(BaseModel):
    """Request for full P&L decomposition."""

    greeks: GreeksSnapshotSchema = Field(
        ..., description="Start-of-day Greeks"
    )
    market_data_t0: MarketDataSnapshotSchema = Field(
        ..., description="Start-of-day market data"
    )
    market_data_t1: MarketDataSnapshotSchema = Field(
        ..., description="End-of-day market data"
    )
    total_pnl: float = Field(
        ..., description="Actual observed P&L for the period"
    )
    notional: float = Field(1_000_000, gt=0, description="Position notional")
    time_elapsed_days: float = Field(
        1.0, ge=0, description="Calendar days elapsed"
    )
    pip_size: float = Field(0.0001, gt=0, description="Size of 1 pip")
    # Optional barrier parameters for barrier-specific attribution
    lower_barrier: Optional[float] = Field(
        None, description="Lower barrier for barrier options"
    )
    upper_barrier: Optional[float] = Field(
        None, description="Upper barrier for barrier options"
    )


class PnLComponentSchema(BaseModel):
    """Single P&L component."""

    component_type: str
    value: float
    description: str
    percentage_of_total: float = 0.0


class PnLAttributionResponse(BaseModel):
    """Full P&L decomposition response."""

    total_pnl: float
    delta_pnl: float
    gamma_pnl: float
    vega_pnl: float
    theta_pnl: float
    rho_pnl: float
    cross_gamma_pnl: float
    unexplained_pnl: float
    explained_pnl: float
    explanation_ratio: float
    components: list[dict[str, Any]]
    market_moves: dict[str, float]
    greeks_used: dict[str, float]
    diagnostics: dict[str, Any]


# ── Greeks Variance Analysis ──────────────────────────────────
class GreeksVarianceRequest(BaseModel):
    """Request to compare desk Greeks vs VC Greeks."""

    desk_greeks: dict[str, float] = Field(
        ..., description="Greeks from front-office (desk) system"
    )
    vc_greeks: dict[str, float] = Field(
        ..., description="Greeks independently computed by Valuation Control"
    )
    position_id: str = Field(
        "UNKNOWN", description="Position or trade identifier"
    )
    thresholds: Optional[dict[str, float]] = Field(
        None,
        description=(
            "Override variance thresholds per Greek (pct). "
            "Defaults: delta=5%, gamma=10%, vega=5%, theta=5%"
        ),
    )
    additional_context: Optional[dict[str, Any]] = Field(
        None,
        description="Extra context (product type, market conditions, etc.)",
    )


class GreekVarianceDetail(BaseModel):
    """Variance details for a single Greek."""

    greek_name: str
    desk_value: float
    vc_value: float
    absolute_variance: float
    relative_variance_pct: float
    threshold_pct: float
    is_flagged: bool
    flag_severity: str
    likely_root_causes: list[dict[str, Any]]


class GreeksVarianceResponse(BaseModel):
    """Complete variance analysis response."""

    position_id: str
    analysis_timestamp: str
    overall_status: str
    flagged_count: int
    total_greeks_compared: int
    greek_variances: list[dict[str, Any]]
    root_cause_summary: dict[str, Any]
    recommendations: list[str]
    diagnostics: dict[str, Any]


# ── Greeks Limits ──────────────────────────────────────────────
class GreeksLimitsCheckRequest(BaseModel):
    """Request to check Greek positions against limits."""

    greeks: dict[str, float] = Field(
        ..., description="Current Greek values (delta, gamma, vega, theta, rho)"
    )
    desk_name: Optional[str] = Field(
        None, description="Override desk name"
    )
    currency_pair: str = Field(
        "EURUSD", description="Currency pair for limit lookup"
    )
    limit_type: str = Field(
        "fx", description="Limit type: 'fx' for standard, 'barrier' for barrier-specific"
    )
    custom_limits: Optional[dict[str, float]] = Field(
        None,
        description=(
            "Custom limit overrides per Greek. "
            "If provided, overrides default limits."
        ),
    )


class UtilizationDetailSchema(BaseModel):
    """Utilization detail for a single Greek."""

    greek_name: str
    current_value: float
    limit_value: float
    utilization_pct: float
    alert_level: str
    is_breached: bool
    breach_action: str
    breach_action_description: str


class GreeksLimitsCheckResponse(BaseModel):
    """Aggregate limits check response."""

    desk_name: str
    currency_pair: str
    check_timestamp: str
    overall_status: str
    highest_alert: str
    has_breaches: bool
    breach_count: int
    utilizations: list[dict[str, Any]]
    breaches: list[dict[str, Any]]
    summary: dict[str, Any]


class GreeksLimitsDefinitionResponse(BaseModel):
    """Response containing current limit definitions."""

    limit_set: dict[str, Any]
    alert_thresholds: dict[str, Any]
    breach_actions: list[dict[str, Any]]

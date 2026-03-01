"""Application configuration for the pricing engine."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings


class AssetClassTolerances(BaseSettings):
    """Per-asset-class tolerance thresholds for IPV.

    Each threshold defines the maximum acceptable % deviation between
    the desk mark and the VC independent fair value before an
    exception is raised.
    """

    # FX
    fx_spot_bps: float = 5.0  # 0.5 bp
    fx_forward_bps: float = 10.0  # 1 bp
    fx_vanilla_pct: float = 0.02  # 2%
    fx_barrier_pct: float = 0.05  # 5% (exotic)
    fx_exotic_pct: float = 0.05  # 5%

    # Rates
    rates_irs_bps: float = 2.0  # 0.2 bp of notional
    rates_swaption_pct: float = 0.05  # 5%
    rates_cap_floor_pct: float = 0.03  # 3%

    # Credit
    credit_cds_bps: float = 10.0  # 1 bp of spread
    credit_loan_pct: float = 0.10  # 10% (illiquid)
    credit_bond_pct: float = 0.02  # 2%

    # Equity
    equity_option_pct: float = 0.02  # 2%
    equity_exotic_pct: float = 0.05  # 5%

    # Commodities
    commodities_vanilla_pct: float = 0.03  # 3%
    commodities_exotic_pct: float = 0.07  # 7%

    def get_tolerance(self, asset_class: str, product_type: str = "vanilla") -> float:
        """Lookup tolerance by asset class and product type."""
        key = f"{asset_class}_{product_type}_pct"
        # Try exact match first
        val = getattr(self, key, None)
        if val is not None:
            return val
        # Try bps variant (convert to pct)
        key_bps = f"{asset_class}_{product_type}_bps"
        val_bps = getattr(self, key_bps, None)
        if val_bps is not None:
            return val_bps / 10_000
        # Fallback to generic exotic/vanilla
        if "exotic" in product_type.lower() or "barrier" in product_type.lower():
            return 0.05
        return 0.02

    # Exception severity thresholds (multiplier of tolerance)
    green_threshold: float = 1.0  # within tolerance
    amber_threshold: float = 2.0  # 1-2x tolerance
    # > amber_threshold -> RED


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # Monte Carlo defaults
    mc_default_paths: int = 50_000
    mc_default_time_steps: int = 252
    mc_seed: int = 42

    # Greeks bump sizes
    delta_bump_pct: float = 0.01  # 1%
    vega_bump_abs: float = 0.01  # 1 vol point
    gamma_bump_pct: float = 0.01  # 1%
    theta_bump_days: int = 1
    rho_bump_abs: float = 0.0001  # 1bp

    # Validation thresholds (generic, overridden by per-asset-class)
    vanilla_tolerance_pct: float = 0.02  # 2%
    exotic_tolerance_pct: float = 0.05  # 5%
    mc_convergence_tolerance: float = 0.005  # 0.5%

    # Data quality
    stale_data_threshold_seconds: int = 300  # 5 minutes
    min_quote_sources: int = 2
    cross_validation_threshold_bps: float = 5.0

    # QuantLib toggle
    use_quantlib: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
tolerances = AssetClassTolerances()

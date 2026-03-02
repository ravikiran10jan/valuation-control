"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Settings for the Validation Agent.

    Contains URLs for all upstream agents and configurable validation
    thresholds used when comparing actual values against the Excel model.
    """

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # ── Upstream Agent URLs ──────────────────────────────────────
    agent1_base_url: str = "http://localhost:8000"   # Data Layer
    agent2_base_url: str = "http://localhost:8002"   # Pricing Engine
    agent3_base_url: str = "http://localhost:8003"   # IPV Orchestrator
    agent4_base_url: str = "http://localhost:8004"   # Dispute Workflow
    agent5_base_url: str = "http://localhost:8005"   # Reserve Calculations
    agent6_base_url: str = "http://localhost:8006"   # Regulatory Reporting
    agent7_base_url: str = "http://localhost:8007"   # Dashboard

    # ── HTTP client settings ─────────────────────────────────────
    upstream_timeout_seconds: float = 30.0
    upstream_max_retries: int = 3
    upstream_retry_delay_seconds: float = 1.0

    # ── Validation tolerance thresholds ──────────────────────────
    # Numeric comparison tolerances used when comparing actual agent
    # outputs against the expected Excel model values.

    # Percentage tolerance for price comparisons (e.g. 0.01 = 1%)
    price_tolerance_pct: float = 0.01

    # Absolute tolerance for USD amounts (rounding differences)
    amount_tolerance_usd: float = 1.0

    # Percentage tolerance for ratio/percentage fields
    ratio_tolerance_pct: float = 0.001

    # Tolerance for survival probability comparisons
    survival_prob_tolerance: float = 0.005

    # Tolerance for capital ratio comparisons (absolute)
    capital_ratio_tolerance: float = 0.001

    # Tolerance for BPS threshold comparisons
    bps_tolerance: float = 0.5

    # Tolerance for percentage threshold comparisons
    pct_threshold_tolerance: float = 0.1

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

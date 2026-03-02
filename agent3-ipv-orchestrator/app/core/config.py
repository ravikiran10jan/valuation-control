"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "valuation_control"
    postgres_user: str = "vc_user"
    postgres_password: str = "changeme"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # ── Upstream Agent URLs ──────────────────────────────────────
    agent1_base_url: str = "http://localhost:8000"
    agent2_base_url: str = "http://localhost:8002"
    agent4_base_url: str = "http://localhost:8004"
    agent5_base_url: str = "http://localhost:8005"
    agent6_base_url: str = "http://localhost:8006"
    agent7_base_url: str = "http://localhost:8007"

    # ── HTTP client settings ────────────────────────────────────
    upstream_timeout_seconds: float = 30.0
    upstream_max_retries: int = 3
    upstream_retry_delay_seconds: float = 1.0

    # ── Tolerance Thresholds (from IPV FX Model) ────────────────
    # G10 Spot: GREEN <5bps, AMBER 5-10bps, RED >10bps
    fx_g10_spot_threshold_green_bps: float = 5.0    # 5 bps
    fx_g10_spot_threshold_amber_bps: float = 10.0   # 10 bps

    # EM Spot: GREEN <2%, AMBER 2-5%, RED >5%
    fx_em_spot_threshold_green_pct: float = 2.0      # 2%
    fx_em_spot_threshold_amber_pct: float = 5.0      # 5%

    # FX Forwards: GREEN <10bps, AMBER 10-20bps, RED >20bps
    fx_forward_threshold_green_bps: float = 10.0     # 10 bps
    fx_forward_threshold_amber_bps: float = 20.0     # 20 bps

    # FX Options / Barrier: GREEN <5%, AMBER 5-10%, RED >10%
    fx_option_threshold_green_pct: float = 5.0       # 5%
    fx_option_threshold_amber_pct: float = 10.0      # 10%

    # ── Escalation rules ────────────────────────────────────────
    escalation_amber_days: int = 5          # AMBER auto-escalation after N days
    escalation_red_days: int = 2            # RED auto-escalation after N days
    escalation_committee_days: int = 5      # Escalate to committee after N days
    materiality_threshold_usd: float = 500_000.0  # USD impact for auto-committee

    # ── Pipeline settings ───────────────────────────────────────
    pipeline_max_concurrent: int = 5
    pipeline_step_timeout_seconds: float = 60.0

    # ── EM currency pairs ───────────────────────────────────────
    em_currencies: str = "TRY,BRL,ZAR,MXN,INR,IDR,PHP,THB,COP,CLP,PEN,ARS,EGP,NGN,KES"

    @property
    def em_currency_set(self) -> set[str]:
        return {c.strip().upper() for c in self.em_currencies.split(",")}

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_dsn_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

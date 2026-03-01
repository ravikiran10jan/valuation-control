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

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "valuation_control_ts"

    # Bloomberg
    bloomberg_enabled: bool = False
    bloomberg_host: str = "localhost"
    bloomberg_port: int = 8194

    # Reuters / Refinitiv
    reuters_enabled: bool = False
    reuters_app_key: str = ""

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    data_stale_threshold_hours: int = 24
    cross_validation_threshold_bps: float = 5.0

    # Exception thresholds — FX-specific (from IPV_FX_Model tolerance policy)
    # G10 Spot (EUR, GBP, JPY): GREEN <5bps, AMBER 5-10bps, RED >10bps
    fx_g10_spot_threshold_green: float = 0.05   # 5 bps = 0.05%
    fx_g10_spot_threshold_amber: float = 0.10   # 10 bps = 0.10%
    # EM Spot (TRY, BRL): GREEN <2%, AMBER 2-5%, RED >5%
    fx_em_spot_threshold_green: float = 2.0     # 2%
    fx_em_spot_threshold_amber: float = 5.0     # 5%
    # FX Forwards: GREEN <10bps, AMBER 10-20bps, RED >20bps
    fx_forward_threshold_green: float = 0.10    # 10 bps = 0.10%
    fx_forward_threshold_amber: float = 0.20    # 20 bps = 0.20%
    # FX Options (Barrier): GREEN <5%, AMBER 5-10%, RED >10%
    fx_option_threshold_green: float = 5.0      # 5%
    fx_option_threshold_amber: float = 10.0     # 10%

    # Legacy generic thresholds (kept for backward compatibility)
    exception_threshold_green: float = 5.0
    exception_threshold_amber: float = 10.0

    # Escalation rules (days)
    escalation_amber_to_manager: int = 5
    escalation_red_to_manager: int = 2
    escalation_red_to_committee: int = 5

    # Email settings (for escalation notifications)
    smtp_host: str = "smtp.bank.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    vc_manager_email: str = "vc.manager@bank.com"
    vc_committee_email: str = "vc.committee@bank.com"

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

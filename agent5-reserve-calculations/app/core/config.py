"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL (shared with agent1)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "valuation_control"
    postgres_user: str = "vc_user"
    postgres_password: str = "changeme"

    # Agent 1 data-layer URL (for position & quote lookups)
    agent1_base_url: str = "http://localhost:8001"

    # Agent 2 pricing-engine URL (for model comparison)
    agent2_base_url: str = "http://localhost:8002"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # AVA calibration defaults
    ava_mpu_fallback_pct: float = 0.05  # 5 % of FV for Level 3 fallback
    ava_admin_rate_bps: float = 10.0  # 10 bps p.a.
    ava_funding_spread_bps: float = 75.0  # 75 bps

    # Model reserve default
    model_reserve_pct: float = 0.50  # 50 % of model range

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

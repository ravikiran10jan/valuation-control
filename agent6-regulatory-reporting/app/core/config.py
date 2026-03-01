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

    # Agent 5 reserve-calculations URL (for AVA data)
    agent5_base_url: str = "http://localhost:8005"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # Regulatory reporting settings
    regulator_ecb_endpoint: str = ""
    regulator_pra_endpoint: str = ""
    regulator_fed_endpoint: str = ""
    firm_reference_uk: str = "BofA_UK_123456"
    firm_reference_us: str = "BofA_US_789012"
    firm_reference_eu: str = "BofA_EU_345678"

    # Audit retention days
    audit_retention_days: int = 2555  # ~7 years for SOX compliance

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

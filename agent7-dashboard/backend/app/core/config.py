"""Configuration for Agent 7 Dashboard BFF."""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Upstream service URLs – docker-compose passes AGENT<N>_BASE_URL
    agent1_url: str = Field(
        default="http://localhost:8000",
        validation_alias="AGENT1_BASE_URL",
    )
    agent2_url: str = Field(
        default="http://localhost:8002",
        validation_alias="AGENT2_BASE_URL",
    )
    agent3_url: str = Field(
        default="http://localhost:8003",
        validation_alias="AGENT3_BASE_URL",
    )
    agent4_url: str = Field(
        default="http://localhost:8004",
        validation_alias="AGENT4_BASE_URL",
    )
    agent5_url: str = Field(
        default="http://localhost:8005",
        validation_alias="AGENT5_BASE_URL",
    )
    agent6_url: str = Field(
        default="http://localhost:8006",
        validation_alias="AGENT6_BASE_URL",
    )
    agent8_url: str = Field(
        default="http://localhost:8008",
        validation_alias="AGENT8_BASE_URL",
    )

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8007

    # Alert polling interval (seconds)
    alert_poll_interval: int = 300  # 5 minutes

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

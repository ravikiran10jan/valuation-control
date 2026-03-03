"""Configuration for Agent 7 Dashboard BFF."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Upstream service URLs
    agent1_url: str = "http://localhost:8000"
    agent2_url: str = "http://localhost:8002"
    agent3_url: str = "http://localhost:8003"
    agent4_url: str = "http://localhost:8004"
    agent5_url: str = "http://localhost:8005"
    agent6_url: str = "http://localhost:8006"
    agent8_url: str = "http://localhost:8008"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8007

    # Alert polling interval (seconds)
    alert_poll_interval: int = 300  # 5 minutes

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

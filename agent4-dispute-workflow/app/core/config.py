"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL (shared with agent1)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "valuation_control"
    postgres_user: str = "vc_user"
    postgres_password: str = "changeme"

    # Application
    app_env: str = "development"
    log_level: str = "INFO"

    # Dispute settings
    desk_response_deadline_days: int = 2
    escalation_auto_days: int = 5
    max_negotiation_rounds: int = 10

    # Email / Microsoft Graph API
    email_provider: str = "outlook"  # outlook | smtp
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_tenant_id: str = ""
    smtp_host: str = "smtp.bank.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    vc_platform_base_url: str = "https://vc-platform.bank.com"

    # S3 document storage
    s3_bucket: str = "vc-platform-documents"
    s3_region: str = "us-east-1"
    s3_presigned_url_expiry_seconds: int = 604800  # 7 days
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Notification emails
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

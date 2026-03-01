"""Factory that returns the appropriate market data connector based on config."""

from typing import Optional

from app.connectors.base import MarketDataConnector
from app.core.config import settings


def get_primary_connector() -> MarketDataConnector:
    """Return Bloomberg if enabled, else fall back to mock."""
    if settings.bloomberg_enabled:
        from app.connectors.bloomberg import BloombergConnector

        return BloombergConnector(settings.bloomberg_host, settings.bloomberg_port)

    from app.connectors.mock import MockConnector

    return MockConnector()


def get_secondary_connector() -> Optional[MarketDataConnector]:
    """Return Reuters if enabled, else None."""
    if settings.reuters_enabled:
        from app.connectors.reuters import ReutersConnector

        return ReutersConnector(settings.reuters_app_key)

    return None

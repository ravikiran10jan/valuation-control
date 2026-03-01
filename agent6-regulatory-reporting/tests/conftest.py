"""Pytest configuration and fixtures."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_ava_data():
    """Sample AVA data for testing."""
    from decimal import Decimal
    return {
        "mpu": Decimal("1000000"),
        "close_out": Decimal("500000"),
        "model_risk": Decimal("750000"),
        "credit_spreads": Decimal("250000"),
        "funding": Decimal("300000"),
        "concentration": Decimal("200000"),
        "admin": Decimal("100000"),
    }


@pytest.fixture
def sample_position():
    """Sample position data for testing."""
    from decimal import Decimal
    return {
        "position_id": 1,
        "trade_id": "TEST001",
        "product_type": "IRS",
        "asset_class": "RATES",
        "notional": Decimal("10000000"),
        "currency": "USD",
        "vc_fair_value": Decimal("150000"),
    }

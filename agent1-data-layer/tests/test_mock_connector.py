"""Tests for the mock market data connector."""

import pytest

from app.connectors.mock import MockConnector


@pytest.fixture
def connector():
    return MockConnector()


@pytest.mark.asyncio
async def test_get_spot_known_pair(connector):
    result = await connector.get_spot("EUR/USD")
    assert "value" in result
    assert result["source"] == "Mock"
    assert abs(result["value"] - 1.0823) < 0.01  # close to base rate


@pytest.mark.asyncio
async def test_get_spot_unknown_pair(connector):
    result = await connector.get_spot("ZAR/BRL")
    assert "value" in result
    # Unknown pair falls back to 1.0 base


@pytest.mark.asyncio
async def test_get_vol_surface(connector):
    result = await connector.get_vol_surface("EUR/USD", "1Y")
    assert "25P" in result
    assert "ATM" in result
    assert "25C" in result
    assert result["25P"] > 0
    assert result["ATM"] > 0
    assert result["25C"] > 0


@pytest.mark.asyncio
async def test_get_yield_curve(connector):
    result = await connector.get_yield_curve("USD_SOFR")
    assert "tenors" in result
    assert "1M" in result["tenors"]
    assert "10Y" in result["tenors"]
    assert all(v > 0 for v in result["tenors"].values())


@pytest.mark.asyncio
async def test_get_cds_spread(connector):
    result = await connector.get_cds_spread("ITRAXX", "5Y")
    assert result["spread_bps"] > 0
    assert result["recovery_rate"] == 0.40


@pytest.mark.asyncio
async def test_get_forward_points(connector):
    result = await connector.get_forward_points("EUR/USD", "1M")
    assert "points" in result


@pytest.mark.asyncio
async def test_health_check(connector):
    assert await connector.health_check() is True

"""Shared test fixtures for agent4 dispute workflow tests."""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.postgres import Dispute, DisputeApproval, DisputeAttachment, DisputeMessage


@pytest_asyncio.fixture
async def db():
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def sample_dispute_data() -> dict:
    return {
        "exception_id": 1,
        "position_id": 100,
        "vc_position": "VC model shows fair value of 306,000 based on MC simulation with 50k paths",
        "vc_analyst": "vc_analyst@bank.com",
        "desk_trader": "fx_trader@bank.com",
        "desk_mark": Decimal("425000.00"),
        "vc_fair_value": Decimal("306000.00"),
    }

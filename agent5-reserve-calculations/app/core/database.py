"""Database engine and session factories."""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    pass


@lru_cache(maxsize=1)
def _engine():
    return create_async_engine(settings.postgres_dsn, echo=(settings.app_env == "development"))


@lru_cache(maxsize=1)
def _session_factory():
    return async_sessionmaker(_engine(), class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async SQLAlchemy session."""
    async with _session_factory()() as session:
        yield session

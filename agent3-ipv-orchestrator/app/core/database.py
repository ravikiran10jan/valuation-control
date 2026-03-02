"""Database engine and session factories."""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# PostgreSQL (async)
engine = create_async_engine(settings.postgres_dsn, echo=(settings.app_env == "development"))
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async SQLAlchemy session."""
    async with async_session_factory() as session:
        yield session

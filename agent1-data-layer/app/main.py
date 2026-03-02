"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging
from app.models.mongo import ensure_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await ensure_indexes()
    yield


app = FastAPI(
    title="Valuation Control - Data Layer & Market Data Engine",
    description="Agent 1: Market data ingestion, position management, and data quality monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api.market_data import router as market_data_router  # noqa: E402
from app.api.positions import router as positions_router  # noqa: E402
from app.api.dealer_quotes import router as dealer_quotes_router  # noqa: E402
from app.api.data_quality import router as data_quality_router  # noqa: E402
from app.api.exceptions import (  # noqa: E402
    router as exceptions_router,
    comparison_router,
    escalation_router,
    committee_router,
)
from app.api.seed_routes import router as seed_router  # noqa: E402

app.include_router(market_data_router)
app.include_router(positions_router)
app.include_router(dealer_quotes_router)
app.include_router(data_quality_router)
app.include_router(exceptions_router)
app.include_router(comparison_router)
app.include_router(escalation_router)
app.include_router(committee_router)
app.include_router(seed_router)


@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "agent1-data-layer", "env": settings.app_env}

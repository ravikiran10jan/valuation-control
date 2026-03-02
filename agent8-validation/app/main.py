"""FastAPI application entry point for Agent 8 -- Validation Agent.

Cross-checks ALL calculations produced by agents 1-7 against the
expected values from the FX IPV Model Excel workbook.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    log.info(
        "agent8_starting",
        env=settings.app_env,
        agents={
            "agent1": settings.agent1_base_url,
            "agent2": settings.agent2_base_url,
            "agent3": settings.agent3_base_url,
            "agent4": settings.agent4_base_url,
            "agent5": settings.agent5_base_url,
            "agent6": settings.agent6_base_url,
            "agent7": settings.agent7_base_url,
        },
    )
    yield
    log.info("agent8_shutdown")


app = FastAPI(
    title="Agent 8: Validation Agent",
    description=(
        "Cross-checks ALL calculations from agents 1-7 against the "
        "FX IPV Model Excel workbook expected values.  Validates the "
        "entire IPV lifecycle for accuracy."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api.routes import router as validation_router  # noqa: E402

app.include_router(validation_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agent8-validation",
        "version": "1.0.0",
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint with service information."""
    return {
        "service": "Agent 8: Validation Agent",
        "description": (
            "Cross-validates all IPV lifecycle calculations against "
            "the FX IPV Model Excel expected values"
        ),
        "endpoints": {
            "validate_all": "POST /validate/all",
            "validate_positions": "POST /validate/positions",
            "validate_tolerances": "POST /validate/tolerances",
            "validate_reserves": "POST /validate/reserves",
            "validate_pricing": "POST /validate/pricing",
            "validate_capital": "POST /validate/capital",
            "validate_hierarchy": "POST /validate/hierarchy",
            "report": "GET /validate/report",
            "gaps": "GET /validate/gaps",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8008,
        reload=settings.app_env == "development",
    )

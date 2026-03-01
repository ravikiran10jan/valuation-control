"""Agent 6: Regulatory Reporting & Compliance

FastAPI application for generating regulatory reports and maintaining audit trails.

Supports:
- Pillar 3 disclosures (Basel III)
- IFRS 13 / ASC 820 fair value hierarchy
- PRA110 returns (UK)
- FR Y-14Q (US Fed)
- Internal audit trails (SOX compliance)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.api.reports import router as reports_router, audit_router
from app.core.config import settings
from app.core.logging import setup_logging

setup_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    log.info(
        "agent6_starting",
        env=settings.app_env,
        postgres_host=settings.postgres_host,
    )
    yield
    log.info("agent6_shutdown")


app = FastAPI(
    title="Agent 6: Regulatory Reporting & Compliance",
    description=(
        "Generates regulatory reports (Pillar 3, IFRS 13, PRA110, FR Y-14Q) "
        "and maintains audit trails for SOX compliance."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(reports_router)
app.include_router(audit_router)


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "agent6-regulatory-reporting",
        "version": "1.0.0",
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint with service information."""
    return {
        "service": "Agent 6: Regulatory Reporting & Compliance",
        "description": "Regulatory report generation and audit trail management",
        "endpoints": {
            "reports": {
                "pillar3": "POST /reports/pillar3",
                "ifrs13": "POST /reports/ifrs13",
                "pra110": "POST /reports/pra110",
                "fry14q": "POST /reports/fry14q",
            },
            "audit": {
                "trail": "GET /audit/trail",
                "report": "GET /audit/report",
                "statistics": "GET /audit/statistics",
            },
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8006,
        reload=settings.app_env == "development",
    )

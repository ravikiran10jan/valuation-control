"""FastAPI application entry point for Agent 7 — Dashboard BFF.

Backend-for-Frontend that aggregates data from Agent 1 (Data Layer)
and Agent 5 (Reserve Calculations) for the dashboard UI.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
import os

from app.core.config import settings
from app.services.upstream import close_client
from app.services.alerts import alert_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background alert polling
    task = asyncio.create_task(_alert_poll_loop())
    yield
    # Cleanup
    task.cancel()
    await close_client()


async def _alert_poll_loop():
    """Background task: poll for alerts on a fixed interval."""
    while True:
        try:
            await alert_service.check_for_alerts()
        except Exception:
            pass
        await asyncio.sleep(settings.alert_poll_interval)


app = FastAPI(
    title="Valuation Control - Dashboard & Analytics",
    description="Agent 7: BFF aggregating Agent 1 & Agent 5 for the dashboard UI",
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

# Register API routers
from app.api.dashboard import router as dashboard_router  # noqa: E402
from app.api.exceptions import router as exceptions_router  # noqa: E402
from app.api.positions import router as positions_router  # noqa: E402
from app.api.alerts import router as alerts_router  # noqa: E402
from app.api.reserves import router as reserves_router  # noqa: E402
from app.api.valuations import router as valuations_router  # noqa: E402
from app.api.routes import router as ipv_lifecycle_router  # noqa: E402
from app.api.simulator import router as simulator_router  # noqa: E402
from app.api.disputes import router as disputes_router  # noqa: E402
from app.api.reports import router as reports_router  # noqa: E402
from app.api.day1_pnl import router as day1_pnl_router  # noqa: E402

app.include_router(dashboard_router)
app.include_router(exceptions_router)
app.include_router(positions_router)
app.include_router(alerts_router)
app.include_router(reserves_router)
app.include_router(valuations_router)
app.include_router(ipv_lifecycle_router)
app.include_router(simulator_router)
app.include_router(disputes_router)
app.include_router(reports_router)
app.include_router(day1_pnl_router)

# Serve the built frontend from dist/ in production
dist_dir = os.path.join(os.path.dirname(__file__), "..", "..", "dist")
if os.path.isdir(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")


@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "agent7-dashboard", "env": settings.app_env}

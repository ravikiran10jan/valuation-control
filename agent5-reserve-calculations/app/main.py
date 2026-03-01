"""FastAPI application entry point for Agent 5 — Reserve Calculations."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title="Valuation Control - Reserve Calculations",
    description=(
        "Agent 5: FVA, AVA (Basel III Article 105), "
        "Model Reserve, and Day 1 P&L recognition"
    ),
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
from app.api.fva import router as fva_router  # noqa: E402
from app.api.ava import router as ava_router  # noqa: E402
from app.api.model_reserve import router as model_reserve_router  # noqa: E402
from app.api.day1_pnl import router as day1_pnl_router  # noqa: E402
from app.api.reserves import router as reserves_router  # noqa: E402

app.include_router(fva_router)
app.include_router(ava_router)
app.include_router(model_reserve_router)
app.include_router(day1_pnl_router)
app.include_router(reserves_router)


@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "agent5-reserve-calculations", "env": settings.app_env}

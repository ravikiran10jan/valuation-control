"""Pricing Engine & Model Library — FastAPI entry point."""

from fastapi import FastAPI

from app.api.routes import greeks_router, router as pricing_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.simulator.api.routes import router as simulator_router

setup_logging(settings.log_level)

app = FastAPI(
    title="Valuation Control — Pricing Engine",
    description=(
        "Independent pricing engine for FX, Rates, Credit, Equity, "
        "and Commodities derivatives. Provides multi-method pricing, "
        "Greeks calculation, and model validation."
    ),
    version="0.1.0",
)

app.include_router(pricing_router)
app.include_router(greeks_router)
app.include_router(simulator_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "pricing-engine"}

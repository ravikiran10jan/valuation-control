"""FastAPI application entry point for Agent 3 — IPV Orchestrator.

The central orchestration agent that runs the full 8-step Independent
Price Verification (IPV) lifecycle, coordinating between all other agents:
  - Agent 1 (port 8000): Data Layer — positions, market data
  - Agent 2 (port 8002): Pricing Engine — FX spot/forward/barrier/options
  - Agent 4 (port 8004): Dispute Workflow
  - Agent 5 (port 8005): Reserve Calculations
  - Agent 6 (port 8006): Regulatory Reporting
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.core.config import settings
from app.core.logging import setup_logging
from app.api.websocket import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log = structlog.get_logger()
    log.info(
        "agent3_starting",
        env=settings.app_env,
        agent1=settings.agent1_base_url,
        agent2=settings.agent2_base_url,
        agent4=settings.agent4_base_url,
        agent5=settings.agent5_base_url,
        agent6=settings.agent6_base_url,
    )
    yield
    log.info("agent3_shutdown")


app = FastAPI(
    title="Valuation Control - IPV Orchestrator",
    description=(
        "Agent 3: Orchestrates the full 8-step Independent Price Verification "
        "(IPV) lifecycle. Coordinates between Data Layer (Agent 1), Pricing Engine "
        "(Agent 2), Dispute Workflow (Agent 4), Reserve Calculations (Agent 5), "
        "and Regulatory Reporting (Agent 6)."
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

# Register REST API router
from app.api.routes import router as ipv_router  # noqa: E402

app.include_router(ipv_router)


# WebSocket endpoint for real-time progress updates
@app.websocket("/ipv/ws")
async def websocket_all(websocket: WebSocket):
    """WebSocket endpoint for receiving all IPV run progress updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Clients can send a run_id to subscribe to specific runs
            if data.startswith("subscribe:"):
                run_id = data.split(":", 1)[1].strip()
                await manager.subscribe(websocket, run_id)
                await websocket.send_text(f'{{"subscribed": "{run_id}"}}')
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.websocket("/ipv/ws/{run_id}")
async def websocket_run(websocket: WebSocket, run_id: str):
    """WebSocket endpoint for receiving progress updates for a specific IPV run."""
    await manager.connect(websocket, run_id=run_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.get("/health")
async def root_health():
    return {
        "status": "ok",
        "service": "agent3-ipv-orchestrator",
        "env": settings.app_env,
        "ws_connections": manager.active_count,
    }


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "Agent 3: IPV Orchestrator",
        "description": "Full 8-step Independent Price Verification lifecycle orchestrator",
        "version": "0.1.0",
        "pipeline_steps": [
            "1. GATHER MARKET DATA",
            "2. RUN VALUATION MODEL",
            "3. COMPARE DESK vs VC",
            "4. FLAG EXCEPTIONS",
            "5. INVESTIGATE & DISPUTE",
            "6. ESCALATE TO VC COMMITTEE",
            "7. RESOLVE & ADJUST",
            "8. REPORT",
        ],
        "upstream_agents": {
            "agent1_data_layer": settings.agent1_base_url,
            "agent2_pricing_engine": settings.agent2_base_url,
            "agent4_dispute_workflow": settings.agent4_base_url,
            "agent5_reserve_calculations": settings.agent5_base_url,
            "agent6_regulatory_reporting": settings.agent6_base_url,
        },
        "endpoints": {
            "runs": "POST /ipv/runs — Start a new IPV run",
            "runs_async": "POST /ipv/runs/async — Start async IPV run",
            "list_runs": "GET /ipv/runs — List IPV runs",
            "get_run": "GET /ipv/runs/{run_id} — Get run details",
            "positions": "GET /ipv/positions — List reference positions",
            "thresholds": "GET /ipv/thresholds — View tolerance thresholds",
            "agents_health": "GET /ipv/agents/health — Check upstream agents",
            "ws_all": "WS /ipv/ws — WebSocket for all progress updates",
            "ws_run": "WS /ipv/ws/{run_id} — WebSocket for specific run",
        },
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8003,
        reload=settings.app_env == "development",
    )

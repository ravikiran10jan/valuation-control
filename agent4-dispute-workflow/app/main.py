"""FastAPI application entry point for Dispute Workflow & Collaboration."""

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
    title="Valuation Control - Dispute Workflow & Collaboration",
    description="Agent 4: Dispute initiation, tracking, email integration, document management, and approval workflows",
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
from app.api.disputes import router as disputes_router  # noqa: E402
from app.api.messages import router as messages_router  # noqa: E402
from app.api.approvals import router as approvals_router  # noqa: E402
from app.api.documents import router as documents_router  # noqa: E402

app.include_router(disputes_router)
app.include_router(messages_router)
app.include_router(approvals_router)
app.include_router(documents_router)


@app.get("/health")
async def root_health():
    return {"status": "ok", "service": "agent4-dispute-workflow", "env": settings.app_env}

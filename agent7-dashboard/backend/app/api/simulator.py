"""Simulator routes — proxy to Agent 2 (Pricing Engine) simulator endpoints.

Provides model discovery, pricing calculation, comparison, and sensitivity
analysis by forwarding requests to the Agent 2 simulator module.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.upstream import agent2_get, agent2_post

router = APIRouter(prefix="/api/simulator", tags=["Simulator"])


# ── List Products ───────────────────────────────────────────────


@router.get("/products")
async def list_products() -> dict[str, Any]:
    """List all available models grouped by asset class.

    Proxies to Agent 2 GET /simulator/products.
    """
    try:
        return await agent2_get("/simulator/products")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Pricing engine unavailable: {exc}")


# ── Model Metadata ──────────────────────────────────────────────


@router.get("/models/{model_id}")
async def get_model_metadata(model_id: str) -> dict[str, Any]:
    """Return full metadata for a model: description, formula, parameters, samples.

    Proxies to Agent 2 GET /simulator/models/{model_id}.
    """
    try:
        return await agent2_get(f"/simulator/models/{model_id}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch model {model_id}: {exc}")


@router.get("/models/{model_id}/samples")
async def get_model_samples(model_id: str) -> dict[str, Any]:
    """Return sample parameter sets for a model.

    Proxies to Agent 2 GET /simulator/models/{model_id}/samples.
    """
    try:
        return await agent2_get(f"/simulator/models/{model_id}/samples")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch samples for {model_id}: {exc}")


# ── Calculate ───────────────────────────────────────────────────


class CalculateRequest(BaseModel):
    model_id: str
    parameters: dict[str, Any]


@router.post("/calculate")
async def calculate(req: CalculateRequest) -> dict[str, Any]:
    """Run a pricing calculation with step-by-step trace.

    Proxies to Agent 2 POST /simulator/calculate.
    """
    try:
        return await agent2_post("/simulator/calculate", json=req.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Calculation failed: {exc}")


# ── Compare ─────────────────────────────────────────────────────


class CompareRequest(BaseModel):
    model_ids: list[str] = Field(..., min_length=1, max_length=10)
    parameters: dict[str, Any]


@router.post("/compare")
async def compare(req: CompareRequest) -> dict[str, Any]:
    """Run the same parameters through multiple models and compare.

    Proxies to Agent 2 POST /simulator/compare.
    """
    try:
        return await agent2_post("/simulator/compare", json=req.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Comparison failed: {exc}")


# ── Sensitivity ─────────────────────────────────────────────────


class SensitivityRequest(BaseModel):
    model_ids: list[str] = Field(..., min_length=1, max_length=5)
    parameters: dict[str, Any]
    sweep_param: str
    sweep_min: float
    sweep_max: float
    sweep_steps: int = Field(default=20, ge=3, le=100)


@router.post("/sensitivity")
async def sensitivity(req: SensitivityRequest) -> dict[str, Any]:
    """Sweep one parameter across a range and price with each model.

    Proxies to Agent 2 POST /simulator/sensitivity.
    """
    try:
        return await agent2_post("/simulator/sensitivity", json=req.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sensitivity analysis failed: {exc}")


# ── Model Reserve ───────────────────────────────────────────────


class ModelReserveRequest(BaseModel):
    model_ids: list[str] = Field(..., min_length=2, max_length=10)
    parameters: dict[str, Any]


@router.post("/model-reserve")
async def model_reserve(req: ModelReserveRequest) -> dict[str, Any]:
    """Compute model reserve (price spread) across models at a single point.

    Proxies to Agent 2 POST /simulator/model-reserve.
    """
    try:
        return await agent2_post("/simulator/model-reserve", json=req.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Model reserve calculation failed: {exc}")


# ── Applicability ───────────────────────────────────────────────


@router.get("/applicability")
async def applicability_matrix() -> list[dict[str, Any]]:
    """Return the full product x model applicability matrix.

    Proxies to Agent 2 GET /simulator/applicability.
    """
    try:
        return await agent2_get("/simulator/applicability")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch applicability matrix: {exc}")


@router.get("/applicability/recommend")
async def recommend_models(product: str = Query(..., description="Product description")) -> list[dict[str, Any]]:
    """Given a product description, return matching model recommendations.

    Proxies to Agent 2 GET /simulator/applicability/recommend.
    """
    try:
        return await agent2_get("/simulator/applicability/recommend", params={"product": product})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to get recommendations: {exc}")

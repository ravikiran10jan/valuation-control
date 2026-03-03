"""Simulator API routes — dynamic model discovery, pricing, and comparison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from pydantic import BaseModel, Field

from app.simulator.registry import ModelRegistry
from app.simulator.schemas import (
    SimulatorCalculateRequest,
    SimulatorCalculateResponse,
    SimulatorCompareRequest,
    SimulatorCompareResponse,
)
from app.simulator.comparison import run_sensitivity, compute_model_reserve
from app.simulator.applicability import get_applicability_matrix, get_product_recommendations

# Force model registration by importing the models package
import app.simulator.models  # noqa: F401

router = APIRouter(prefix="/simulator", tags=["simulator"])


@router.get("/products")
async def list_products() -> dict[str, Any]:
    """List all available models grouped by asset class."""
    return ModelRegistry.list_products()


@router.get("/models/{model_id}")
async def get_model_metadata(model_id: str) -> dict[str, Any]:
    """Return full metadata for a model: description, formula, parameters, samples."""
    try:
        model = ModelRegistry.get_model(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return model.get_metadata()


@router.get("/models/{model_id}/samples")
async def get_model_samples(model_id: str) -> dict[str, Any]:
    """Return sample parameter sets for a model."""
    try:
        model = ModelRegistry.get_model(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return model.get_samples()


@router.post("/calculate", response_model=SimulatorCalculateResponse)
async def calculate(req: SimulatorCalculateRequest) -> SimulatorCalculateResponse:
    """Run a pricing calculation with step-by-step trace."""
    try:
        model = ModelRegistry.get_model(req.model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    try:
        result = model.calculate(req.parameters)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Calculation failed: {e}")

    return SimulatorCalculateResponse(
        model_id=model.model_id,
        model_name=model.model_name,
        fair_value=result.fair_value,
        method=result.method,
        greeks=result.greeks,
        calculation_steps=[
            {
                "step_number": s.step_number,
                "label": s.label,
                "formula": s.formula,
                "substitution": s.substitution,
                "result": s.result,
                "explanation": s.explanation,
            }
            for s in result.calculation_steps
        ],
        diagnostics=result.diagnostics,
    )


@router.post("/compare", response_model=SimulatorCompareResponse)
async def compare(req: SimulatorCompareRequest) -> SimulatorCompareResponse:
    """Run the same parameters through multiple models and compare.

    Resilient: if one model fails, others still return with partial results.
    """
    results = []
    errors: dict[str, str] = {}

    for mid in req.model_ids:
        try:
            model = ModelRegistry.get_model(mid)
        except KeyError:
            errors[mid] = f"Model '{mid}' not found"
            continue

        try:
            merged = model.params_with_defaults(req.parameters)
            result = model.calculate(merged)
        except Exception as e:
            errors[mid] = f"Calculation failed: {e}"
            continue

        results.append(SimulatorCalculateResponse(
            model_id=model.model_id,
            model_name=model.model_name,
            fair_value=result.fair_value,
            method=result.method,
            greeks=result.greeks,
            calculation_steps=[
                {
                    "step_number": s.step_number,
                    "label": s.label,
                    "formula": s.formula,
                    "substitution": s.substitution,
                    "result": s.result,
                    "explanation": s.explanation,
                }
                for s in result.calculation_steps
            ],
            diagnostics=result.diagnostics,
        ))

    if not results:
        detail = "; ".join(f"{mid}: {msg}" for mid, msg in errors.items())
        raise HTTPException(status_code=422, detail=detail or "No models produced results")

    # Build comparison summary
    prices = {r.model_id: r.fair_value for r in results}
    price_values = list(prices.values())
    comparison: dict[str, Any] = {
        "prices": prices,
        "max_price": max(price_values),
        "min_price": min(price_values),
        "model_reserve": round(max(price_values) - min(price_values), 4),
    }
    if errors:
        comparison["errors"] = errors

    # Greek comparison
    all_greeks = {r.model_id: r.greeks for r in results if r.greeks}
    if all_greeks:
        greek_names = set()
        for g in all_greeks.values():
            greek_names.update(g.keys())
        greek_comparison = {}
        for gn in greek_names:
            vals = {mid: gs.get(gn) for mid, gs in all_greeks.items()}
            numeric_vals = [v for v in vals.values() if v is not None]
            spread = round(max(numeric_vals) - min(numeric_vals), 6) if len(numeric_vals) >= 2 else 0.0
            greek_comparison[gn] = {
                "values": vals,
                "spread": spread,
            }
        comparison["greeks"] = greek_comparison

    return SimulatorCompareResponse(results=results, comparison=comparison)


# ── Phase 4: Sensitivity & Applicability ─────────────────────


class SensitivityRequest(BaseModel):
    model_ids: list[str] = Field(..., min_length=1, max_length=5)
    parameters: dict[str, Any]
    sweep_param: str
    sweep_min: float
    sweep_max: float
    sweep_steps: int = Field(default=20, ge=3, le=100)


@router.post("/sensitivity")
async def sensitivity(req: SensitivityRequest) -> dict[str, Any]:
    """Sweep one parameter across a range and price with each model."""
    step_size = (req.sweep_max - req.sweep_min) / max(req.sweep_steps - 1, 1)
    sweep_values = [
        round(req.sweep_min + i * step_size, 6) for i in range(req.sweep_steps)
    ]
    try:
        return run_sensitivity(req.model_ids, req.parameters, req.sweep_param, sweep_values)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Sensitivity failed: {e}")


class ModelReserveRequest(BaseModel):
    model_ids: list[str] = Field(..., min_length=2, max_length=10)
    parameters: dict[str, Any]


@router.post("/model-reserve")
async def model_reserve(req: ModelReserveRequest) -> dict[str, Any]:
    """Compute model reserve (price spread) across models at a single point."""
    try:
        return compute_model_reserve(req.model_ids, req.parameters)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Model reserve failed: {e}")


@router.get("/applicability")
async def applicability_matrix() -> list[dict[str, Any]]:
    """Return the full product × model applicability matrix."""
    return get_applicability_matrix()


@router.get("/applicability/recommend")
async def recommend_models(product: str) -> list[dict[str, Any]]:
    """Given a product description, return matching model recommendations."""
    return get_product_recommendations(product)

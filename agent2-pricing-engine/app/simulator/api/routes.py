"""Simulator API routes — dynamic model discovery, pricing, and comparison."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from app.simulator.registry import ModelRegistry
from app.simulator.schemas import (
    SimulatorCalculateRequest,
    SimulatorCalculateResponse,
    SimulatorCompareRequest,
    SimulatorCompareResponse,
)

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
    """Run the same parameters through multiple models and compare."""
    results = []
    for mid in req.model_ids:
        try:
            model = ModelRegistry.get_model(mid)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e))

        try:
            result = model.calculate(req.parameters)
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Calculation failed for {mid}: {e}",
            )

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

    # Build comparison summary
    prices = {r.model_id: r.fair_value for r in results}
    price_values = list(prices.values())
    comparison: dict[str, Any] = {
        "prices": prices,
        "max_price": max(price_values),
        "min_price": min(price_values),
        "model_reserve": round(max(price_values) - min(price_values), 4),
    }

    # Greek comparison
    all_greeks = {r.model_id: r.greeks for r in results if r.greeks}
    if all_greeks:
        greek_names = set()
        for g in all_greeks.values():
            greek_names.update(g.keys())
        greek_comparison = {}
        for gn in greek_names:
            vals = {mid: gs.get(gn, 0) for mid, gs in all_greeks.items()}
            greek_comparison[gn] = {
                "values": vals,
                "spread": round(max(vals.values()) - min(vals.values()), 6),
            }
        comparison["greeks"] = greek_comparison

    return SimulatorCompareResponse(results=results, comparison=comparison)

"""Pydantic schemas for the simulator API."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class SimulatorCalculateRequest(BaseModel):
    model_id: str = Field(..., description="Registered model identifier")
    parameters: dict[str, Any] = Field(..., description="Model parameters")


class SimulatorCompareRequest(BaseModel):
    model_ids: list[str] = Field(
        ..., min_length=2, max_length=5, description="Models to compare"
    )
    parameters: dict[str, Any] = Field(..., description="Shared parameters")


class CalculationStepSchema(BaseModel):
    step_number: int
    label: str
    formula: str
    substitution: str
    result: float
    explanation: str = ""


class SimulatorCalculateResponse(BaseModel):
    model_id: str
    model_name: str
    fair_value: float
    method: str
    greeks: dict[str, float] = {}
    calculation_steps: list[CalculationStepSchema] = []
    diagnostics: dict[str, Any] = {}


class SimulatorCompareResponse(BaseModel):
    results: list[SimulatorCalculateResponse]
    comparison: dict[str, Any] = {}

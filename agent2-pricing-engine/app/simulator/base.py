"""Base class and data structures for all simulator models."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CalculationStep:
    """A single step in a step-by-step pricing calculation."""

    step_number: int
    label: str
    formula: str
    substitution: str
    result: float
    explanation: str = ""


@dataclass
class SimulatorResult:
    """Result returned by every simulator model."""

    fair_value: float
    method: str
    greeks: dict[str, float] = field(default_factory=dict)
    calculation_steps: list[CalculationStep] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fair_value": self.fair_value,
            "method": self.method,
            "greeks": self.greeks,
            "calculation_steps": [
                {
                    "step_number": s.step_number,
                    "label": s.label,
                    "formula": s.formula,
                    "substitution": s.substitution,
                    "result": s.result,
                    "explanation": s.explanation,
                }
                for s in self.calculation_steps
            ],
            "diagnostics": self.diagnostics,
        }


@dataclass
class ParameterSpec:
    """Specification for a single model parameter."""

    name: str
    label: str
    description: str
    type: str  # "float", "int", "str", "select"
    default: Any
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    options: list[str] | None = None
    unit: str = ""


class BaseSimulatorModel(abc.ABC):
    """Every simulator model must implement this interface."""

    # ── Identity ──
    model_id: str
    model_name: str
    product_type: str
    asset_class: str

    # ── Description ──
    short_description: str
    long_description: str

    # ── Applicability ──
    when_to_use: list[str]
    when_not_to_use: list[str]
    assumptions: list[str]
    limitations: list[str]

    # ── Formula ──
    formula_latex: str
    formula_plain: str

    @abc.abstractmethod
    def get_parameters(self) -> list[ParameterSpec]:
        """Return parameter specifications for UI form generation."""

    @abc.abstractmethod
    def get_samples(self) -> dict[str, dict[str, Any]]:
        """Return named sample parameter sets."""

    @abc.abstractmethod
    def calculate(self, params: dict[str, Any]) -> SimulatorResult:
        """Run the full pricing calculation with step-by-step trace."""

    def get_metadata(self) -> dict[str, Any]:
        """Return full model metadata for the API."""
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "product_type": self.product_type,
            "asset_class": self.asset_class,
            "short_description": self.short_description,
            "long_description": self.long_description,
            "when_to_use": self.when_to_use,
            "when_not_to_use": self.when_not_to_use,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
            "formula_latex": self.formula_latex,
            "formula_plain": self.formula_plain,
            "parameters": [
                {
                    "name": p.name,
                    "label": p.label,
                    "description": p.description,
                    "type": p.type,
                    "default": p.default,
                    "min_value": p.min_value,
                    "max_value": p.max_value,
                    "step": p.step,
                    "options": p.options,
                    "unit": p.unit,
                }
                for p in self.get_parameters()
            ],
            "samples": self.get_samples(),
        }

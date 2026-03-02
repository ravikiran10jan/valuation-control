"""Model registry for auto-discovery of simulator models."""

from __future__ import annotations

from app.simulator.base import BaseSimulatorModel


class ModelRegistry:
    """Singleton registry — models register via decorator."""

    _models: dict[str, BaseSimulatorModel] = {}

    @classmethod
    def register(cls, model_class: type[BaseSimulatorModel]):
        """Decorator to register a model class."""
        instance = model_class()
        cls._models[instance.model_id] = instance
        return model_class

    @classmethod
    def get_model(cls, model_id: str) -> BaseSimulatorModel:
        if model_id not in cls._models:
            available = list(cls._models.keys())
            raise KeyError(
                f"Model '{model_id}' not found. Available: {available}"
            )
        return cls._models[model_id]

    @classmethod
    def list_products(cls) -> dict[str, list[dict[str, str]]]:
        """Return models grouped by asset class."""
        grouped: dict[str, list[dict[str, str]]] = {}
        for model in cls._models.values():
            ac = model.asset_class
            if ac not in grouped:
                grouped[ac] = []
            grouped[ac].append(
                {
                    "model_id": model.model_id,
                    "model_name": model.model_name,
                    "product_type": model.product_type,
                    "short_description": model.short_description,
                }
            )
        return grouped

    @classmethod
    def list_all(cls) -> list[dict[str, str]]:
        return [
            {
                "model_id": m.model_id,
                "model_name": m.model_name,
                "asset_class": m.asset_class,
                "product_type": m.product_type,
            }
            for m in cls._models.values()
        ]

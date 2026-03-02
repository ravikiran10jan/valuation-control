"""Model Comparison Engine — enhanced multi-model analysis.

Provides:
1. Side-by-side pricing from multiple models
2. Parameter sensitivity analysis (bump one param, compare all models)
3. Model reserve calculation (max - min across models)
4. Greek comparison with spreads
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.simulator.base import SimulatorResult
from app.simulator.registry import ModelRegistry


def run_sensitivity(
    model_ids: list[str],
    base_params: dict[str, Any],
    sweep_param: str,
    sweep_values: list[float],
) -> dict[str, Any]:
    """Sweep one parameter across a range and price with each model.

    Returns a structure like:
    {
      "sweep_param": "vol",
      "sweep_values": [0.10, 0.15, 0.20, ...],
      "models": {
        "black_scholes": {
          "prices": [8.12, 9.45, 10.80, ...],
          "deltas": [0.55, 0.56, 0.57, ...],
        },
        "cev": { ... },
      },
      "model_reserve": [0.12, 0.25, 0.38, ...],
    }
    """
    models = {}
    for mid in model_ids:
        try:
            models[mid] = ModelRegistry.get_model(mid)
        except KeyError:
            continue

    results: dict[str, dict[str, list]] = {}
    for mid in models:
        results[mid] = {"prices": [], "deltas": [], "gammas": [], "vegas": []}

    reserves = []

    for val in sweep_values:
        p = {**base_params, sweep_param: val}
        prices_at_val = []

        for mid, model in models.items():
            try:
                res = model.calculate(p)
                results[mid]["prices"].append(round(res.fair_value, 4))
                results[mid]["deltas"].append(round(res.greeks.get("delta", 0), 6))
                results[mid]["gammas"].append(round(res.greeks.get("gamma", 0), 6))
                results[mid]["vegas"].append(round(res.greeks.get("vega", 0), 6))
                prices_at_val.append(res.fair_value)
            except Exception:
                results[mid]["prices"].append(None)
                results[mid]["deltas"].append(None)
                results[mid]["gammas"].append(None)
                results[mid]["vegas"].append(None)

        valid_prices = [p for p in prices_at_val if p is not None]
        if len(valid_prices) >= 2:
            reserves.append(round(max(valid_prices) - min(valid_prices), 4))
        else:
            reserves.append(0)

    return {
        "sweep_param": sweep_param,
        "sweep_values": sweep_values,
        "models": {
            mid: {
                "model_name": models[mid].model_name,
                **data,
            }
            for mid, data in results.items()
        },
        "model_reserve": reserves,
    }


def compute_model_reserve(
    model_ids: list[str],
    base_params: dict[str, Any],
) -> dict[str, Any]:
    """Compute the model reserve (price spread) across models at a single point."""
    results = {}
    for mid in model_ids:
        try:
            model = ModelRegistry.get_model(mid)
            res = model.calculate(base_params)
            results[mid] = {
                "model_name": model.model_name,
                "fair_value": res.fair_value,
                "greeks": res.greeks,
                "method": res.method,
            }
        except Exception as e:
            results[mid] = {"error": str(e)}

    valid = {k: v for k, v in results.items() if "fair_value" in v}
    prices = [v["fair_value"] for v in valid.values()]

    if len(prices) >= 2:
        reserve = round(max(prices) - min(prices), 4)
        reserve_pct = round(reserve / np.mean(prices) * 100, 2) if np.mean(prices) != 0 else 0
    else:
        reserve = 0
        reserve_pct = 0

    return {
        "results": results,
        "model_reserve": reserve,
        "model_reserve_pct": reserve_pct,
        "best_price": round(max(prices), 4) if prices else 0,
        "worst_price": round(min(prices), 4) if prices else 0,
        "mean_price": round(float(np.mean(prices)), 4) if prices else 0,
    }

"""Applicability Matrix — product × model cross-reference.

For each product type, lists which models are valid, which are preferred,
and what the key differentiators are. This is the "when to use what" guide
that a valuation control analyst would consult.
"""

from __future__ import annotations

from typing import Any

from app.simulator.registry import ModelRegistry


# ── Static applicability data ────────────────────────────────
# Each entry maps a product type to the models that can price it,
# with a rating (preferred / valid / limited / invalid) and notes.

APPLICABILITY: list[dict[str, Any]] = [
    {
        "product": "European Vanilla Call/Put",
        "asset_class": "equity",
        "models": {
            "black_scholes": {"rating": "preferred", "notes": "Industry standard, analytical Greeks, fastest"},
            "cev": {"rating": "valid", "notes": "Adds leverage/skew via β parameter"},
            "variance_gamma": {"rating": "valid", "notes": "Captures fat tails and skew, slower (FFT)"},
            "pde_solver": {"rating": "valid", "notes": "Numerical — useful for validation, slower"},
            "local_vol_dupire": {"rating": "valid", "notes": "Fits full vol surface, best for consistency with exotics"},
        },
        "key_differentiator": "Model choice depends on whether skew/kurtosis matters for the specific strike and maturity.",
    },
    {
        "product": "American Vanilla Call/Put",
        "asset_class": "equity",
        "models": {
            "black_scholes": {"rating": "invalid", "notes": "Cannot handle early exercise"},
            "pde_solver": {"rating": "preferred", "notes": "Crank-Nicolson with early exercise constraint"},
            "cev": {"rating": "limited", "notes": "Closed-form is European only; needs PDE extension for American"},
            "variance_gamma": {"rating": "limited", "notes": "No efficient American pricing under VG"},
        },
        "key_differentiator": "Only PDE/tree methods handle early exercise. BSM gives a lower bound.",
    },
    {
        "product": "Barrier Option (Continuous)",
        "asset_class": "equity",
        "models": {
            "black_scholes": {"rating": "limited", "notes": "Analytical barriers exist but ignore smile"},
            "pde_solver": {"rating": "preferred", "notes": "PDE with Dirichlet boundary at barrier"},
            "local_vol_dupire": {"rating": "preferred", "notes": "Local vol + PDE for smile-consistent barriers"},
        },
        "key_differentiator": "Barrier options are highly sensitive to the vol smile near the barrier.",
    },
    {
        "product": "LEAPS (Long-Dated Options)",
        "asset_class": "equity",
        "models": {
            "black_scholes": {"rating": "valid", "notes": "Baseline, but ignores leverage compounding"},
            "cev": {"rating": "preferred", "notes": "Leverage effect compounds over long horizons"},
            "variance_gamma": {"rating": "valid", "notes": "Non-normality compounds; captures tail risk"},
        },
        "key_differentiator": "For LEAPS, model choice significantly impacts price — model reserve can be 2-5%.",
    },
    {
        "product": "Delta Hedging Strategy",
        "asset_class": "equity",
        "models": {
            "hedge_simulator": {"rating": "preferred", "notes": "Purpose-built for hedging analysis"},
        },
        "key_differentiator": "Not a pricing model — simulates hedging P&L under different true processes.",
    },
    {
        "product": "Bond Option / Swaption",
        "asset_class": "rates",
        "models": {
            "hull_white_1f": {"rating": "preferred", "notes": "Trinomial tree, handles Bermudan exercise"},
            "black_scholes": {"rating": "limited", "notes": "Black-76 for European swaptions only"},
        },
        "key_differentiator": "Hull-White calibrates to yield curve and handles early exercise via tree.",
    },
    {
        "product": "Single-Name CDS",
        "asset_class": "credit",
        "models": {
            "cds_isda": {"rating": "preferred", "notes": "ISDA standard, hazard rate bootstrap"},
            "merton_structural": {"rating": "limited", "notes": "Gives implied spread from equity, not market-standard"},
        },
        "key_differentiator": "ISDA model is market standard for CDS. Merton is for equity-credit analysis.",
    },
    {
        "product": "Basket CDS / nth-to-Default",
        "asset_class": "credit",
        "models": {
            "first_to_default": {"rating": "preferred", "notes": "Gaussian Copula MC, correlation-driven"},
            "cds_isda": {"rating": "invalid", "notes": "Single-name only, no basket/correlation"},
        },
        "key_differentiator": "Correlation parameter ρ is the key driver. Need copula model for baskets.",
    },
    {
        "product": "Default Probability Estimation",
        "asset_class": "credit",
        "models": {
            "merton_structural": {"rating": "preferred", "notes": "Infers PD from equity value + vol"},
            "cds_isda": {"rating": "valid", "notes": "Extracts PD from market CDS spread"},
        },
        "key_differentiator": "Merton uses equity data, ISDA uses credit market data. They may diverge (basis).",
    },
]


def get_applicability_matrix() -> list[dict[str, Any]]:
    """Return the full applicability matrix with live model availability."""
    available = set(m["model_id"] for m in ModelRegistry.list_all())
    matrix = []
    for entry in APPLICABILITY:
        row = {**entry}
        # Annotate which models are actually registered
        annotated_models = {}
        for mid, info in entry["models"].items():
            annotated_models[mid] = {
                **info,
                "available": mid in available,
                "model_name": ModelRegistry.get_model(mid).model_name if mid in available else mid,
            }
        row["models"] = annotated_models
        matrix.append(row)
    return matrix


def get_product_recommendations(product_hint: str) -> list[dict[str, Any]]:
    """Given a product description, return matching applicability entries."""
    hint_lower = product_hint.lower()
    matches = []
    for entry in APPLICABILITY:
        score = 0
        product_lower = entry["product"].lower()
        for word in hint_lower.split():
            if word in product_lower:
                score += 1
        if entry["asset_class"].lower() in hint_lower:
            score += 1
        if score > 0:
            matches.append({**entry, "_score": score})
    matches.sort(key=lambda x: x["_score"], reverse=True)
    return matches

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
    # ── FX Products ──────────────────────────────────────────
    {
        "product": "European FX Vanilla Call/Put",
        "asset_class": "fx",
        "models": {
            "garman_kohlhagen": {"rating": "preferred", "notes": "Industry standard FX BSM, analytical Greeks"},
            "fx_variance_gamma": {"rating": "valid", "notes": "Captures EM FX jumps and fat tails (FFT)"},
            "fx_local_vol": {"rating": "valid", "notes": "Smile-consistent pricing with 25Δ RR/BF inputs"},
            "fx_pde_solver": {"rating": "valid", "notes": "Numerical validation, slower than GK"},
        },
        "key_differentiator": "GK is the standard. Use FX VG for EM pairs with jumps, Local Vol for smile-sensitive pricing.",
    },
    {
        "product": "FX Barrier Option (Knock-In/Out)",
        "asset_class": "fx",
        "models": {
            "fx_pde_solver": {"rating": "preferred", "notes": "PDE with Dirichlet boundary at barrier level"},
            "fx_local_vol": {"rating": "preferred", "notes": "Smile-consistent barrier pricing (barrier sensitive to smile)"},
            "garman_kohlhagen": {"rating": "limited", "notes": "Analytical barriers ignore smile — can misprice significantly"},
        },
        "key_differentiator": "FX barriers are highly smile-sensitive. Local vol PDE is the industry standard.",
    },
    {
        "product": "American FX Option",
        "asset_class": "fx",
        "models": {
            "fx_pde_solver": {"rating": "preferred", "notes": "Crank-Nicolson with early exercise constraint"},
            "garman_kohlhagen": {"rating": "invalid", "notes": "European only — no early exercise"},
        },
        "key_differentiator": "Only PDE handles early exercise. American FX options common for corporate hedging.",
    },
    {
        "product": "EM FX Options (with jump risk)",
        "asset_class": "fx",
        "models": {
            "fx_variance_gamma": {"rating": "preferred", "notes": "Captures devaluation jumps, fat tails, asymmetry"},
            "garman_kohlhagen": {"rating": "limited", "notes": "Underprices OTM puts in EM FX (no jumps)"},
            "fx_local_vol": {"rating": "valid", "notes": "Fits smile but no explicit jump modelling"},
        },
        "key_differentiator": "EM FX (BRL, TRY, ZAR) has significant jump risk. VG captures this; GK does not.",
    },
    # ── Income Products ──────────────────────────────────────
    {
        "product": "Net Interest Income (IRRBB)",
        "asset_class": "income",
        "models": {
            "nii_forecast": {"rating": "preferred", "notes": "Repricing gap analysis with rate shocks and pass-through"},
        },
        "key_differentiator": "Core ALM/Treasury tool for earnings-at-risk from rate movements.",
    },
    {
        "product": "Non-Interest Income Forecast",
        "asset_class": "income",
        "models": {
            "non_interest_income": {"rating": "preferred", "notes": "Scenario-based projection of fee, trading, and securities income"},
        },
        "key_differentiator": "Complements NII for total revenue forecasting under market stress scenarios.",
    },
    {
        "product": "Total Bank Revenue Forecast",
        "asset_class": "income",
        "models": {
            "nii_forecast": {"rating": "preferred", "notes": "NII component — interest rate sensitive"},
            "non_interest_income": {"rating": "preferred", "notes": "Non-interest component — market sensitive"},
        },
        "key_differentiator": "Total revenue = NII + non-interest income. Both should be projected together for stress testing.",
    },
]


def get_applicability_matrix() -> list[dict[str, Any]]:
    """Return the full applicability matrix with live model availability.

    Returns each entry with ``applicable_models`` as an array (not a dict) so
    the frontend can iterate directly.
    """
    available = set(m["model_id"] for m in ModelRegistry.list_all())
    matrix = []
    for entry in APPLICABILITY:
        applicable_models = []
        for mid, info in entry["models"].items():
            applicable_models.append({
                "model_id": mid,
                "model_name": ModelRegistry.get_model(mid).model_name if mid in available else mid,
                "rating": info["rating"],
                "notes": info["notes"],
                "available": mid in available,
            })
        matrix.append({
            "product": entry["product"],
            "asset_class": entry["asset_class"],
            "applicable_models": applicable_models,
            "key_differentiator": entry.get("key_differentiator", ""),
        })
    return matrix


def get_product_recommendations(product_hint: str) -> list[dict[str, Any]]:
    """Given a product description, return matching model recommendations.

    Returns a flat list of per-model entries so the frontend can render them
    directly without further transformation.
    """
    available = set(m["model_id"] for m in ModelRegistry.list_all())
    hint_lower = product_hint.lower()
    scored: list[tuple[int, dict[str, Any], str, dict[str, Any]]] = []
    for entry in APPLICABILITY:
        score = 0
        product_lower = entry["product"].lower()
        for word in hint_lower.split():
            if word in product_lower:
                score += 1
        if entry["asset_class"].lower() in hint_lower:
            score += 1
        if score > 0:
            for mid, info in entry["models"].items():
                scored.append((score, entry, mid, info))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "model_id": mid,
            "model_name": ModelRegistry.get_model(mid).model_name if mid in available else mid,
            "rating": info["rating"],
            "notes": info["notes"],
            "product": entry["product"],
            "asset_class": entry["asset_class"],
        }
        for _, entry, mid, info in scored
    ]

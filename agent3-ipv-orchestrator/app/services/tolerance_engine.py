"""Tolerance checking logic with all thresholds from the IPV FX Model Excel.

Tolerance Thresholds:
    G10 Spot:        GREEN <5bps,  AMBER 5-10bps,  RED >10bps
    EM Spot:         GREEN <2%,    AMBER 2-5%,     RED >5%
    FX Forwards:     GREEN <10bps, AMBER 10-20bps, RED >20bps
    FX Options/Barrier: GREEN <5%, AMBER 5-10%,    RED >10%
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

import structlog

from app.core.config import settings
from app.models.schemas import (
    ProductCategory,
    RAGStatus,
)

log = structlog.get_logger()

# G10 currency list — anything NOT in the EM set is G10
_EM_CURRENCIES = settings.em_currency_set


def classify_product(
    product_type: str,
    currency_pair: str,
) -> ProductCategory:
    """Determine which tolerance category a position falls into.

    Args:
        product_type: Product type string, e.g. "Spot", "Spot (EM)", "1Y Forward",
                      "Barrier (DNT)", "Vanilla Option", etc.
        currency_pair: Currency pair, e.g. "EUR/USD", "USD/TRY".

    Returns:
        The ProductCategory that determines which thresholds to use.
    """
    pt_lower = product_type.lower()

    # Check for options/barrier first (most specific)
    if any(kw in pt_lower for kw in ("barrier", "option", "dnt", "kiko", "vanilla", "exotic")):
        return ProductCategory.FX_OPTION

    # Check for forwards
    if any(kw in pt_lower for kw in ("forward", "fwd", "ndf", "outright")):
        return ProductCategory.FX_FORWARD

    # Spot: determine if EM or G10
    if _is_em_pair(currency_pair) or "em" in pt_lower:
        return ProductCategory.EM_SPOT

    return ProductCategory.G10_SPOT


def _is_em_pair(currency_pair: str) -> bool:
    """Check if a currency pair involves an EM currency."""
    parts = currency_pair.upper().replace("/", "").replace("-", "")
    # Split into two 3-letter currency codes
    if len(parts) == 6:
        ccy1 = parts[:3]
        ccy2 = parts[3:]
        return ccy1 in _EM_CURRENCIES or ccy2 in _EM_CURRENCIES
    # Fallback: check if any EM code appears in the string
    return any(em in currency_pair.upper() for em in _EM_CURRENCIES)


def get_thresholds(category: ProductCategory) -> tuple[Decimal, Decimal]:
    """Return (green_threshold_pct, amber_threshold_pct) for a product category.

    Values are in percentage terms:
      - G10 Spot: 5bps = 0.05%, 10bps = 0.10%
      - EM Spot: 2.0%, 5.0%
      - FX Forward: 10bps = 0.10%, 20bps = 0.20%
      - FX Option: 5.0%, 10.0%

    Returns:
        Tuple of (green_threshold_pct, amber_threshold_pct) as Decimal.
    """
    if category == ProductCategory.G10_SPOT:
        green = Decimal(str(settings.fx_g10_spot_threshold_green_bps)) / Decimal("100")
        amber = Decimal(str(settings.fx_g10_spot_threshold_amber_bps)) / Decimal("100")
    elif category == ProductCategory.EM_SPOT:
        green = Decimal(str(settings.fx_em_spot_threshold_green_pct))
        amber = Decimal(str(settings.fx_em_spot_threshold_amber_pct))
    elif category == ProductCategory.FX_FORWARD:
        green = Decimal(str(settings.fx_forward_threshold_green_bps)) / Decimal("100")
        amber = Decimal(str(settings.fx_forward_threshold_amber_bps)) / Decimal("100")
    elif category == ProductCategory.FX_OPTION:
        green = Decimal(str(settings.fx_option_threshold_green_pct))
        amber = Decimal(str(settings.fx_option_threshold_amber_pct))
    else:
        # Default fallback — use G10 spot
        green = Decimal("0.05")
        amber = Decimal("0.10")

    return green, amber


def evaluate_rag(
    difference_pct: Decimal,
    category: ProductCategory,
) -> RAGStatus:
    """Evaluate RAG status based on absolute percentage difference.

    Args:
        difference_pct: The percentage difference (can be negative).
        category: The product category for threshold lookup.

    Returns:
        RAGStatus.GREEN, AMBER, or RED.
    """
    abs_diff = abs(difference_pct)
    green_threshold, amber_threshold = get_thresholds(category)

    if abs_diff < green_threshold:
        return RAGStatus.GREEN
    elif abs_diff <= amber_threshold:
        return RAGStatus.AMBER
    else:
        return RAGStatus.RED


def calculate_difference(
    desk_mark: Decimal,
    ipv_price: Decimal,
) -> tuple[Decimal, Decimal]:
    """Calculate absolute and percentage difference between desk mark and IPV price.

    Args:
        desk_mark: The desk's mark-to-market value.
        ipv_price: The independent price verification value.

    Returns:
        Tuple of (difference, difference_pct) where:
        - difference = desk_mark - ipv_price
        - difference_pct = (desk_mark - ipv_price) / ipv_price * 100
    """
    difference = desk_mark - ipv_price
    if ipv_price == 0:
        if desk_mark == 0:
            difference_pct = Decimal("0")
        else:
            difference_pct = Decimal("100")
    else:
        difference_pct = (difference / ipv_price) * Decimal("100")
    return difference, difference_pct


def calculate_breach_amount_usd(
    difference_pct: Decimal,
    notional: Decimal,
    category: ProductCategory,
) -> Optional[Decimal]:
    """Calculate the USD breach amount when thresholds are exceeded.

    Only returns a value if the position is AMBER or RED.
    The breach amount = notional * |diff_pct - green_threshold| / 100.

    Args:
        difference_pct: Percentage difference.
        notional: Position notional in USD.
        category: Product category for threshold lookup.

    Returns:
        Breach amount in USD, or None if within GREEN threshold.
    """
    abs_diff = abs(difference_pct)
    green_threshold, _ = get_thresholds(category)

    if abs_diff <= green_threshold:
        return None

    excess_pct = abs_diff - green_threshold
    breach = (notional * excess_pct) / Decimal("100")
    return breach.quantize(Decimal("0.01"))


def full_tolerance_check(
    desk_mark: Decimal,
    ipv_price: Decimal,
    notional: Decimal,
    product_type: str,
    currency_pair: str,
) -> dict:
    """Run the complete tolerance check for a position.

    Returns a dictionary with all tolerance results:
        - difference: absolute difference
        - difference_pct: percentage difference
        - product_category: which tolerance bucket
        - rag_status: GREEN/AMBER/RED
        - threshold_green: green threshold percentage
        - threshold_amber: amber threshold percentage
        - breach: whether tolerance is breached
        - breach_amount_usd: USD impact (None if GREEN)
    """
    category = classify_product(product_type, currency_pair)
    difference, difference_pct = calculate_difference(desk_mark, ipv_price)
    rag = evaluate_rag(difference_pct, category)
    green_threshold, amber_threshold = get_thresholds(category)
    breach = rag != RAGStatus.GREEN
    breach_usd = calculate_breach_amount_usd(difference_pct, notional, category)

    log.debug(
        "tolerance_check",
        currency_pair=currency_pair,
        product_type=product_type,
        category=category.value,
        desk_mark=str(desk_mark),
        ipv_price=str(ipv_price),
        diff_pct=str(difference_pct),
        rag=rag.value,
        breach=breach,
    )

    return {
        "difference": difference,
        "difference_pct": difference_pct,
        "product_category": category,
        "rag_status": rag,
        "threshold_green": green_threshold,
        "threshold_amber": amber_threshold,
        "breach": breach,
        "breach_amount_usd": breach_usd,
    }

"""Step 3: Compare Desk vs VC.

Calculates differences between desk marks and VC independent prices,
applies tolerance thresholds, and determines RAG status for each position.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from app.models.schemas import (
    ComparisonResult,
    PositionInput,
    ValuationResult,
)
from app.services.tolerance_engine import (
    calculate_breach_amount_usd,
    calculate_difference,
    classify_product,
    evaluate_rag,
    get_thresholds,
)

log = structlog.get_logger()


class ComparisonEngine:
    """Compares desk marks against VC independent prices."""

    def compare_position(
        self,
        position: PositionInput,
        valuation: ValuationResult,
    ) -> ComparisonResult:
        """Compare desk mark vs IPV price for a single position.

        Calculates the difference, percentage difference, and RAG status
        using the tolerance engine thresholds.
        """
        desk_mark = position.desk_mark
        ipv_price = valuation.ipv_price
        category = classify_product(position.product_type, position.currency_pair)
        difference, difference_pct = calculate_difference(desk_mark, ipv_price)
        rag = evaluate_rag(difference_pct, category)
        green_threshold, amber_threshold = get_thresholds(category)
        breach = rag.value != "GREEN"

        log.info(
            "comparison_result",
            position_id=position.position_id,
            desk_mark=str(desk_mark),
            ipv_price=str(ipv_price),
            diff=str(difference),
            diff_pct=f"{difference_pct:.4f}%",
            rag=rag.value,
            category=category.value,
        )

        return ComparisonResult(
            position_id=position.position_id,
            desk_mark=desk_mark,
            ipv_price=ipv_price,
            difference=difference,
            difference_pct=difference_pct,
            product_category=category,
            rag_status=rag,
            threshold_green=green_threshold,
            threshold_amber=amber_threshold,
            breach=breach,
        )

    def compare_all(
        self,
        positions: list[PositionInput],
        valuations: dict[str, ValuationResult],
    ) -> dict[str, ComparisonResult]:
        """Compare all positions against their IPV prices.

        Returns a dict mapping position_id -> ComparisonResult.
        """
        comparisons: dict[str, ComparisonResult] = {}
        for pos in positions:
            val = valuations.get(pos.position_id)
            if val is None:
                log.warning(
                    "comparison_skipped_no_valuation",
                    position_id=pos.position_id,
                )
                continue
            comparisons[pos.position_id] = self.compare_position(pos, val)

        # Log summary statistics
        green = sum(1 for c in comparisons.values() if c.rag_status.value == "GREEN")
        amber = sum(1 for c in comparisons.values() if c.rag_status.value == "AMBER")
        red = sum(1 for c in comparisons.values() if c.rag_status.value == "RED")
        log.info(
            "comparison_summary",
            total=len(comparisons),
            green=green,
            amber=amber,
            red=red,
        )

        return comparisons

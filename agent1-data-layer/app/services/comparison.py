"""Comparison Engine for VC vs Desk mark valuations.

Implements Basel III / IFRS 13 aligned threshold-based comparison logic
with automated exception flagging (GREEN/AMBER/RED).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.core.config import settings
from app.models.postgres import (
    VCException as ExceptionModel,
    Position,
    ValuationComparison,
)
from app.models.schemas import ExceptionSummary

log = structlog.get_logger()


class ComparisonEngine:
    """Compare VC independent valuations against desk marks and flag exceptions."""

    # Currency pairs classified by liquidity category
    G10_PAIRS = {"EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "USD/CAD",
                 "NZD/USD", "EUR/GBP", "EUR/JPY", "GBP/JPY"}
    EM_PAIRS = {"USD/TRY", "USD/BRL", "USD/ZAR", "USD/MXN", "USD/INR",
                "USD/CNH", "USD/RUB", "USD/PLN", "USD/HUF", "USD/CZK"}

    def __init__(self, db: AsyncSession):
        self.db = db
        # FX-specific thresholds from IPV_FX_Model tolerance policy
        self.fx_thresholds = {
            "G10_SPOT": {
                "GREEN": settings.fx_g10_spot_threshold_green,  # 0.05% (5 bps)
                "AMBER": settings.fx_g10_spot_threshold_amber,  # 0.10% (10 bps)
            },
            "EM_SPOT": {
                "GREEN": settings.fx_em_spot_threshold_green,   # 2.0%
                "AMBER": settings.fx_em_spot_threshold_amber,   # 5.0%
            },
            "FORWARD": {
                "GREEN": settings.fx_forward_threshold_green,   # 0.10% (10 bps)
                "AMBER": settings.fx_forward_threshold_amber,   # 0.20% (20 bps)
            },
            "OPTION": {
                "GREEN": settings.fx_option_threshold_green,    # 5.0%
                "AMBER": settings.fx_option_threshold_amber,    # 10.0%
            },
        }
        # Fallback generic thresholds
        self.thresholds = {
            "GREEN": settings.exception_threshold_green,
            "AMBER": settings.exception_threshold_amber,
        }

    def _get_fx_category(self, position: Position) -> str:
        """Determine the FX threshold category for a position."""
        product_type = (position.product_type or "").lower()
        currency_pair = position.currency_pair or ""

        if "barrier" in product_type or "option" in product_type or "dnt" in product_type:
            return "OPTION"
        elif "forward" in product_type or "fwd" in product_type:
            return "FORWARD"
        elif currency_pair in self.EM_PAIRS or "em" in product_type:
            return "EM_SPOT"
        else:
            return "G10_SPOT"

    def determine_status(self, abs_diff_pct: float, position: Position = None) -> str:
        """Apply materiality thresholds to determine exception status.

        Uses FX-specific thresholds when position info is available,
        otherwise falls back to generic thresholds.

        Args:
            abs_diff_pct: Absolute percentage difference between VC and Desk values.
            position: Optional position to determine FX category.

        Returns:
            Status string: 'GREEN', 'AMBER', or 'RED'.
        """
        if position and position.asset_class == "FX":
            category = self._get_fx_category(position)
            thresholds = self.fx_thresholds[category]
        else:
            thresholds = self.thresholds

        if abs_diff_pct < thresholds["GREEN"]:
            return "GREEN"
        elif abs_diff_pct < thresholds["AMBER"]:
            return "AMBER"
        else:
            return "RED"

    async def compare_valuation(self, position_id: int) -> dict:
        """Compare VC fair value vs Desk mark for a single position.

        Args:
            position_id: The ID of the position to compare.

        Returns:
            Dictionary with comparison results including status.

        Raises:
            ValueError: If position not found or missing valuation data.
        """
        position = await self.db.get(Position, position_id)
        if not position:
            raise ValueError(f"Position {position_id} not found")

        desk_mark = position.desk_mark
        vc_fv = position.vc_fair_value

        if desk_mark is None or vc_fv is None:
            raise ValueError(
                f"Position {position_id} missing desk_mark or vc_fair_value"
            )

        # Calculate difference
        difference = vc_fv - desk_mark
        difference_pct = (
            float((difference / desk_mark) * 100) if desk_mark != 0 else 0.0
        )

        # Determine status based on absolute percentage
        status = self.determine_status(abs(difference_pct), position)

        # Save comparison to history
        comparison = ValuationComparison(
            position_id=position_id,
            desk_mark=desk_mark,
            vc_fair_value=vc_fv,
            difference=difference,
            difference_pct=Decimal(str(round(difference_pct, 2))),
            status=status,
            comparison_date=date.today(),
        )
        self.db.add(comparison)

        # Update position with latest comparison data
        position.difference = difference
        position.difference_pct = Decimal(str(round(difference_pct, 2)))
        position.exception_status = status

        # Trigger exception creation if AMBER or RED
        exception_id = None
        if status in ("AMBER", "RED"):
            exception_id = await self._create_exception(
                position_id=position_id,
                difference=difference,
                difference_pct=difference_pct,
                severity=status,
            )

        await self.db.commit()
        await self.db.refresh(comparison)

        log.info(
            "valuation_compared",
            position_id=position_id,
            status=status,
            difference_pct=difference_pct,
            exception_id=exception_id,
        )

        return {
            "position_id": position_id,
            "desk_mark": float(desk_mark),
            "vc_fair_value": float(vc_fv),
            "difference": float(difference),
            "difference_pct": difference_pct,
            "status": status,
            "comparison_date": date.today(),
            "comparison_id": comparison.comparison_id,
            "exception_id": exception_id,
        }

    async def _create_exception(
        self,
        position_id: int,
        difference: Decimal,
        difference_pct: float,
        severity: str,
    ) -> int:
        """Create an exception record for a flagged position.

        Args:
            position_id: The position ID.
            difference: Absolute difference amount.
            difference_pct: Percentage difference.
            severity: 'AMBER' or 'RED'.

        Returns:
            The exception_id of the created record.
        """
        # Check if there's already an open exception for this position
        existing = await self.db.execute(
            select(ExceptionModel).where(
                ExceptionModel.position_id == position_id,
                ExceptionModel.status.in_(["OPEN", "INVESTIGATING"]),
            )
        )
        existing_exc = existing.scalar_one_or_none()

        if existing_exc:
            # Update existing exception if severity increased
            if severity == "RED" and existing_exc.severity == "AMBER":
                existing_exc.severity = "RED"
                existing_exc.difference = difference
                existing_exc.difference_pct = Decimal(str(round(difference_pct, 2)))
                log.info(
                    "exception_upgraded",
                    exception_id=existing_exc.exception_id,
                    new_severity=severity,
                )
            return existing_exc.exception_id

        # Create new exception
        exception = ExceptionModel(
            position_id=position_id,
            difference=difference,
            difference_pct=Decimal(str(round(difference_pct, 2))),
            status="OPEN",
            severity=severity,
            created_date=date.today(),
            days_open=0,
            escalation_level=1,  # Analyst level
        )
        self.db.add(exception)
        await self.db.flush()  # Get the ID

        log.info(
            "exception_created",
            exception_id=exception.exception_id,
            position_id=position_id,
            severity=severity,
        )

        return exception.exception_id

    async def compare_all_positions(
        self, asset_class: Optional[str] = None
    ) -> dict:
        """Run daily comparison on all positions (or filtered by asset class).

        Args:
            asset_class: Optional filter by asset class.

        Returns:
            Summary of comparison results.
        """
        stmt = select(Position).where(
            Position.desk_mark.isnot(None),
            Position.vc_fair_value.isnot(None),
        )
        if asset_class:
            stmt = stmt.where(Position.asset_class == asset_class)

        result = await self.db.execute(stmt)
        positions = result.scalars().all()

        summary = {
            "total_compared": 0,
            "green": 0,
            "amber": 0,
            "red": 0,
            "errors": [],
        }

        for pos in positions:
            try:
                comparison_result = await self.compare_valuation(pos.position_id)
                summary["total_compared"] += 1
                status_key = comparison_result["status"].lower()
                summary[status_key] += 1
            except ValueError as e:
                summary["errors"].append(
                    {"position_id": pos.position_id, "error": str(e)}
                )

        log.info(
            "batch_comparison_complete",
            total=summary["total_compared"],
            green=summary["green"],
            amber=summary["amber"],
            red=summary["red"],
            errors=len(summary["errors"]),
        )

        return summary

    async def get_comparison_history(
        self,
        position_id: int,
        limit: int = 30,
    ) -> list[ValuationComparison]:
        """Get historical comparisons for a position.

        Args:
            position_id: The position to query.
            limit: Maximum records to return.

        Returns:
            List of ValuationComparison records ordered by date desc.
        """
        stmt = (
            select(ValuationComparison)
            .where(ValuationComparison.position_id == position_id)
            .order_by(ValuationComparison.comparison_date.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_exception_summary(self) -> ExceptionSummary:
        """Get summary statistics for exceptions.

        Returns:
            ExceptionSummary with counts and averages.
        """
        # Total open exceptions
        total_result = await self.db.execute(
            select(func.count(ExceptionModel.exception_id)).where(
                ExceptionModel.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"])
            )
        )
        total = total_result.scalar() or 0

        # RED count
        red_result = await self.db.execute(
            select(func.count(ExceptionModel.exception_id)).where(
                ExceptionModel.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"]),
                ExceptionModel.severity == "RED",
            )
        )
        red_count = red_result.scalar() or 0

        # AMBER count
        amber_result = await self.db.execute(
            select(func.count(ExceptionModel.exception_id)).where(
                ExceptionModel.status.in_(["OPEN", "INVESTIGATING", "ESCALATED"]),
                ExceptionModel.severity == "AMBER",
            )
        )
        amber_count = amber_result.scalar() or 0

        # Average days to resolve (resolved exceptions only)
        avg_result = await self.db.execute(
            select(func.avg(ExceptionModel.days_open)).where(
                ExceptionModel.status == "RESOLVED"
            )
        )
        avg_days = avg_result.scalar() or 0.0

        return ExceptionSummary(
            total_exceptions=total,
            red_count=red_count,
            amber_count=amber_count,
            avg_days_to_resolve=round(float(avg_days), 1),
        )

"""IFRS 13 Reporter for fair value hierarchy disclosures.

Generates fair value hierarchy reports including Level 3 reconciliation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import httpx

from app.core.config import settings
from app.models.postgres import (
    FairValueHierarchy,
    LevelTransfer,
    RegulatoryReport,
)
from app.models.schemas import (
    FairValueLevel,
    FairValueLevelSummary,
    IFRS13ReportOut,
    Level3Movement,
    ReportStatus,
    ReportType,
    ValuationTechnique,
)

log = structlog.get_logger()


class IFRS13Reporter:
    """Generate IFRS 13 fair value hierarchy reports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_fair_value_hierarchy(
        self, reporting_date: date
    ) -> IFRS13ReportOut:
        """Generate IFRS 13 fair value hierarchy report.

        IFRS 13 requires disclosure of:
        1. Total fair value by level (1, 2, 3)
        2. Transfers between levels
        3. Level 3 reconciliation
        4. Valuation techniques for Level 3

        Args:
            reporting_date: The reporting date.

        Returns:
            IFRS13ReportOut with hierarchy and reconciliation.
        """
        log.info("generating_ifrs13_report", reporting_date=str(reporting_date))

        # Get all positions classified by level
        positions = await self._get_positions(reporting_date)

        # Aggregate by level
        by_level = await self._aggregate_by_level(positions)

        # Level 3 reconciliation (required detail)
        level3_recon = await self._generate_level3_reconciliation(reporting_date)

        # Valuation techniques
        level3_techniques = self._generate_valuation_techniques()

        # Store report
        report = RegulatoryReport(
            report_type=ReportType.IFRS13.value,
            reporting_date=reporting_date,
            firm_reference=settings.firm_reference_eu,
            status=ReportStatus.DRAFT.value,
            content={
                "fair_value_hierarchy": [lvl.model_dump() for lvl in by_level],
                "level3_reconciliation": level3_recon.model_dump(),
                "valuation_techniques": [t.model_dump() for t in level3_techniques],
            },
        )
        self.db.add(report)
        await self.db.commit()
        await self.db.refresh(report)

        log.info(
            "ifrs13_report_generated",
            report_id=report.report_id,
            reporting_date=str(reporting_date),
        )

        return IFRS13ReportOut(
            report_id=report.report_id,
            reporting_date=reporting_date,
            status=ReportStatus(report.status),
            fair_value_hierarchy=by_level,
            level3_reconciliation=level3_recon,
            valuation_techniques=level3_techniques,
            generated_at=report.generated_at,
        )

    async def _get_positions(self, reporting_date: date) -> list[dict]:
        """Get all positions with fair value classifications.

        Args:
            reporting_date: The reporting date.

        Returns:
            List of position dictionaries with level and fair value.
        """
        # Try local fair value hierarchy table
        stmt = select(FairValueHierarchy).where(
            FairValueHierarchy.classification_date == reporting_date
        )
        result = await self.db.execute(stmt)
        hierarchies = result.scalars().all()

        if hierarchies:
            return [
                {
                    "position_id": h.position_id,
                    "classification": h.fair_value_level,
                    "vc_fair_value": h.fair_value,
                }
                for h in hierarchies
            ]

        # Fallback: Get positions from agent1
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.agent1_base_url}/positions",
                    params={"valuation_date": str(reporting_date)},
                    timeout=30.0,
                )
                if response.status_code == 200:
                    positions = response.json()
                    # Classify positions based on product type
                    return [
                        {
                            "position_id": p["position_id"],
                            "classification": self._classify_position(p),
                            "vc_fair_value": Decimal(str(p.get("vc_fair_value", 0))),
                        }
                        for p in positions
                    ]
        except Exception as e:
            log.error("agent1_position_fetch_failed", error=str(e))

        return []

    def _classify_position(self, position: dict) -> str:
        """Classify a position into fair value level.

        Args:
            position: Position dictionary.

        Returns:
            Fair value level string.
        """
        product_type = position.get("product_type", "").upper()
        asset_class = position.get("asset_class", "").upper()

        # Level 1: Quoted prices in active markets
        if product_type in ["EQUITY", "BOND", "ETF", "FUTURES"]:
            return FairValueLevel.LEVEL_1.value

        # Level 3: Unobservable inputs
        if product_type in ["EXOTIC_OPTION", "CLO", "ABS", "PRIVATE_EQUITY"]:
            return FairValueLevel.LEVEL_3.value

        # Level 2: Observable inputs (default for most derivatives)
        return FairValueLevel.LEVEL_2.value

    async def _aggregate_by_level(
        self, positions: list[dict]
    ) -> list[FairValueLevelSummary]:
        """Aggregate positions by fair value level.

        Args:
            positions: List of position dictionaries.

        Returns:
            List of FairValueLevelSummary for each level.
        """
        by_level: dict[str, dict] = {
            FairValueLevel.LEVEL_1.value: {"count": 0, "total_fv": Decimal("0")},
            FairValueLevel.LEVEL_2.value: {"count": 0, "total_fv": Decimal("0")},
            FairValueLevel.LEVEL_3.value: {"count": 0, "total_fv": Decimal("0")},
        }

        for p in positions:
            level = p["classification"]
            if level in by_level:
                by_level[level]["count"] += 1
                by_level[level]["total_fv"] += Decimal(str(p.get("vc_fair_value", 0)))

        total_fv = sum(lvl["total_fv"] for lvl in by_level.values())

        summaries = []
        for level, data in by_level.items():
            pct = (data["total_fv"] / total_fv * 100) if total_fv else Decimal("0")
            summaries.append(
                FairValueLevelSummary(
                    level=FairValueLevel(level),
                    count=data["count"],
                    total_fair_value=data["total_fv"],
                    percentage_of_total=pct,
                )
            )

        return summaries

    async def _generate_level3_reconciliation(
        self, reporting_date: date
    ) -> Level3Movement:
        """Generate Level 3 reconciliation (movement).

        Required: Movement in Level 3 positions:
        - Opening balance
        - + Purchases
        - + Issuances
        - + Transfers into Level 3
        - - Transfers out of Level 3
        - - Settlements
        - +/- Gains/losses in P&L
        - +/- Gains/losses in OCI
        - = Closing balance

        Args:
            reporting_date: The reporting date.

        Returns:
            Level3Movement with reconciliation.
        """
        prior_period = reporting_date - timedelta(days=90)  # Previous quarter

        opening = await self._get_level3_total(prior_period)
        purchases = await self._get_level3_purchases(prior_period, reporting_date)
        transfers_in = await self._get_transfers_to_level3(prior_period, reporting_date)
        transfers_out = await self._get_transfers_from_level3(prior_period, reporting_date)
        settlements = await self._get_level3_settlements(prior_period, reporting_date)
        pnl = await self._get_level3_pnl(prior_period, reporting_date)
        closing = await self._get_level3_total(reporting_date)

        expected_closing = opening + purchases + transfers_in - transfers_out - settlements + pnl
        check_passed = abs(closing - expected_closing) < Decimal("1")  # Allow rounding

        return Level3Movement(
            opening_balance=opening,
            purchases=purchases,
            issuances=Decimal("0"),
            transfers_in=transfers_in,
            transfers_out=transfers_out,
            settlements=settlements,
            pnl=pnl,
            oci=Decimal("0"),
            closing_balance=closing,
            check_passed=check_passed,
        )

    async def _get_level3_total(self, as_of_date: date) -> Decimal:
        """Get total Level 3 fair value.

        Args:
            as_of_date: The date to query.

        Returns:
            Total Level 3 fair value.
        """
        stmt = select(func.sum(FairValueHierarchy.fair_value)).where(
            and_(
                FairValueHierarchy.classification_date == as_of_date,
                FairValueHierarchy.fair_value_level == FairValueLevel.LEVEL_3.value,
            )
        )
        result = await self.db.execute(stmt)
        total = result.scalar_one_or_none()
        return Decimal(str(total)) if total else Decimal("0")

    async def _get_level3_purchases(
        self, start_date: date, end_date: date
    ) -> Decimal:
        """Get Level 3 purchases during period.

        Args:
            start_date: Period start.
            end_date: Period end.

        Returns:
            Total purchases.
        """
        # In production, would query a trades table
        # For now, return placeholder
        return Decimal("0")

    async def _get_transfers_to_level3(
        self, start_date: date, end_date: date
    ) -> Decimal:
        """Get transfers into Level 3 during period.

        Args:
            start_date: Period start.
            end_date: Period end.

        Returns:
            Total transfers in.
        """
        stmt = select(func.sum(LevelTransfer.fair_value)).where(
            and_(
                LevelTransfer.transfer_date.between(start_date, end_date),
                LevelTransfer.to_level == FairValueLevel.LEVEL_3.value,
            )
        )
        result = await self.db.execute(stmt)
        total = result.scalar_one_or_none()
        return Decimal(str(total)) if total else Decimal("0")

    async def _get_transfers_from_level3(
        self, start_date: date, end_date: date
    ) -> Decimal:
        """Get transfers out of Level 3 during period.

        Args:
            start_date: Period start.
            end_date: Period end.

        Returns:
            Total transfers out.
        """
        stmt = select(func.sum(LevelTransfer.fair_value)).where(
            and_(
                LevelTransfer.transfer_date.between(start_date, end_date),
                LevelTransfer.from_level == FairValueLevel.LEVEL_3.value,
            )
        )
        result = await self.db.execute(stmt)
        total = result.scalar_one_or_none()
        return Decimal(str(total)) if total else Decimal("0")

    async def _get_level3_settlements(
        self, start_date: date, end_date: date
    ) -> Decimal:
        """Get Level 3 settlements during period.

        Args:
            start_date: Period start.
            end_date: Period end.

        Returns:
            Total settlements.
        """
        # In production, would query settlements table
        return Decimal("0")

    async def _get_level3_pnl(
        self, start_date: date, end_date: date
    ) -> Decimal:
        """Get Level 3 P&L during period.

        Args:
            start_date: Period start.
            end_date: Period end.

        Returns:
            Total P&L.
        """
        # In production, would calculate from mark changes
        return Decimal("0")

    def _generate_valuation_techniques(self) -> list[ValuationTechnique]:
        """Generate valuation technique disclosures for Level 3.

        Returns:
            List of valuation techniques used.
        """
        return [
            ValuationTechnique(
                product_type="Exotic Options",
                technique="Monte Carlo Simulation",
                inputs=["Volatility surface", "Correlation matrix", "Barrier levels"],
                observable_inputs=False,
            ),
            ValuationTechnique(
                product_type="CLO/ABS",
                technique="Discounted Cash Flow",
                inputs=["Default rates", "Recovery rates", "Prepayment speeds", "Discount rates"],
                observable_inputs=False,
            ),
            ValuationTechnique(
                product_type="Private Equity",
                technique="Market Comparable / DCF",
                inputs=["Revenue multiples", "EBITDA multiples", "Discount rates"],
                observable_inputs=False,
            ),
            ValuationTechnique(
                product_type="Illiquid Bonds",
                technique="Dealer Quotes / Matrix Pricing",
                inputs=["Credit spreads", "Recovery assumptions"],
                observable_inputs=False,
            ),
        ]

    async def record_level_transfer(
        self,
        position_id: int,
        transfer_date: date,
        from_level: FairValueLevel,
        to_level: FairValueLevel,
        fair_value: Decimal,
        reason: str,
    ) -> LevelTransfer:
        """Record a transfer between fair value levels.

        Args:
            position_id: The position being transferred.
            transfer_date: Date of transfer.
            from_level: Original level.
            to_level: New level.
            fair_value: Fair value at transfer.
            reason: Reason for transfer.

        Returns:
            Created LevelTransfer record.
        """
        transfer = LevelTransfer(
            position_id=position_id,
            transfer_date=transfer_date,
            from_level=from_level.value,
            to_level=to_level.value,
            fair_value=float(fair_value),
            reason=reason,
        )
        self.db.add(transfer)
        await self.db.commit()
        await self.db.refresh(transfer)

        log.info(
            "level_transfer_recorded",
            position_id=position_id,
            from_level=from_level.value,
            to_level=to_level.value,
        )

        return transfer

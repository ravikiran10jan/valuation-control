"""Step 1: Gather Market Data.

Calls Agent 1 (Data Layer) to retrieve spot rates, forward points,
vol surfaces, and yield curves for each position being valued.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

import structlog

from app.models.schemas import MarketDataSnapshot, PositionInput
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class MarketDataGatherer:
    """Gathers market data from Agent 1 for all positions in the IPV run."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def gather_for_position(
        self,
        position: PositionInput,
        valuation_date: Optional[Any] = None,
    ) -> MarketDataSnapshot:
        """Gather all relevant market data for a single position.

        Depending on product type, fetches different market data:
          - Spot: spot rate only
          - Forward: spot rate + forward points + yield curves
          - Option/Barrier: spot rate + vol surface + yield curves
        """
        pt_lower = position.product_type.lower()
        currency_pair = position.currency_pair

        spot_rate: Optional[Decimal] = None
        forward_points: Optional[Decimal] = None
        forward_rate: Optional[Decimal] = None
        vol_surface: Optional[dict[str, Any]] = None
        yield_curve_dom: Optional[dict[str, Any]] = None
        yield_curve_for: Optional[dict[str, Any]] = None
        quality_score: float = 1.0

        try:
            # Always get spot rate
            spot_data = await self._client.get_spot_rate(currency_pair)
            spot_rate = Decimal(str(spot_data.get("value", spot_data.get("spot_rate", 0))))
            log.info("market_data_spot_fetched", pair=currency_pair, rate=str(spot_rate))
        except Exception as exc:
            log.warning("market_data_spot_failed", pair=currency_pair, error=str(exc))
            quality_score -= 0.3

        # Forward-specific data
        if any(kw in pt_lower for kw in ("forward", "fwd", "ndf")):
            try:
                fwd_data = await self._client.get_forward_points(currency_pair, "1Y")
                forward_points = Decimal(
                    str(fwd_data.get("forward_points", fwd_data.get("value", 0)))
                )
                if spot_rate and forward_points:
                    forward_rate = spot_rate + forward_points / Decimal("10000")
                log.info("market_data_fwd_fetched", pair=currency_pair, points=str(forward_points))
            except Exception as exc:
                log.warning("market_data_fwd_failed", pair=currency_pair, error=str(exc))
                quality_score -= 0.2

            # Yield curves for interest rate parity
            try:
                ccy_parts = currency_pair.upper().replace("-", "/").split("/")
                if len(ccy_parts) == 2:
                    dom_curve_name = f"{ccy_parts[0]}_SOFR" if ccy_parts[0] == "USD" else f"{ccy_parts[0]}_OIS"
                    for_curve_name = f"{ccy_parts[1]}_SOFR" if ccy_parts[1] == "USD" else f"{ccy_parts[1]}_OIS"
                    yc_dom, yc_for = await asyncio.gather(
                        self._client.get_yield_curve(dom_curve_name),
                        self._client.get_yield_curve(for_curve_name),
                        return_exceptions=True,
                    )
                    if not isinstance(yc_dom, Exception):
                        yield_curve_dom = yc_dom
                    if not isinstance(yc_for, Exception):
                        yield_curve_for = yc_for
            except Exception as exc:
                log.warning("market_data_yc_failed", pair=currency_pair, error=str(exc))
                quality_score -= 0.1

        # Option/Barrier-specific data
        if any(kw in pt_lower for kw in ("barrier", "option", "dnt", "vanilla")):
            try:
                vol_data = await self._client.get_vol_surface(currency_pair, "1Y")
                vol_surface = vol_data
                log.info("market_data_vol_fetched", pair=currency_pair)
            except Exception as exc:
                log.warning("market_data_vol_failed", pair=currency_pair, error=str(exc))
                quality_score -= 0.2

            # Yield curves for discounting
            try:
                ccy_parts = currency_pair.upper().replace("-", "/").split("/")
                if len(ccy_parts) == 2 and yield_curve_dom is None:
                    dom_curve_name = f"{ccy_parts[0]}_SOFR" if ccy_parts[0] == "USD" else f"{ccy_parts[0]}_OIS"
                    for_curve_name = f"{ccy_parts[1]}_SOFR" if ccy_parts[1] == "USD" else f"{ccy_parts[1]}_OIS"
                    yc_dom, yc_for = await asyncio.gather(
                        self._client.get_yield_curve(dom_curve_name),
                        self._client.get_yield_curve(for_curve_name),
                        return_exceptions=True,
                    )
                    if not isinstance(yc_dom, Exception):
                        yield_curve_dom = yc_dom
                    if not isinstance(yc_for, Exception):
                        yield_curve_for = yc_for
            except Exception as exc:
                log.warning("market_data_yc_option_failed", pair=currency_pair, error=str(exc))
                quality_score -= 0.1

        return MarketDataSnapshot(
            position_id=position.position_id,
            currency_pair=currency_pair,
            spot_rate=spot_rate,
            forward_points=forward_points,
            forward_rate=forward_rate,
            vol_surface=vol_surface,
            yield_curve_dom=yield_curve_dom,
            yield_curve_for=yield_curve_for,
            data_source="agent1",
            timestamp=datetime.utcnow(),
            quality_score=max(0.0, quality_score),
        )

    async def gather_all(
        self,
        positions: list[PositionInput],
        valuation_date: Optional[Any] = None,
    ) -> dict[str, MarketDataSnapshot]:
        """Gather market data for all positions concurrently.

        Returns a dict mapping position_id -> MarketDataSnapshot.
        """
        tasks = [
            self.gather_for_position(pos, valuation_date)
            for pos in positions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)
        snapshots: dict[str, MarketDataSnapshot] = {}

        for pos, result in zip(positions, results):
            if isinstance(result, Exception):
                log.error(
                    "market_data_gather_exception",
                    position_id=pos.position_id,
                    error=str(result),
                )
                # Create a minimal snapshot with no data
                snapshots[pos.position_id] = MarketDataSnapshot(
                    position_id=pos.position_id,
                    currency_pair=pos.currency_pair,
                    data_source="agent1",
                    timestamp=datetime.utcnow(),
                    quality_score=0.0,
                )
            else:
                snapshots[pos.position_id] = result

        log.info(
            "market_data_gather_complete",
            total=len(positions),
            successful=sum(1 for s in snapshots.values() if s.quality_score and s.quality_score > 0.5),
        )
        return snapshots

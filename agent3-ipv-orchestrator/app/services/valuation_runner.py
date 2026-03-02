"""Step 2: Run Valuation Model.

Calls Agent 2 (Pricing Engine) to run independent pricing for each position.
Selects the appropriate pricing model based on product type.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Optional

import structlog

from app.models.schemas import (
    MarketDataSnapshot,
    PositionInput,
    ValuationResult,
)
from app.services.upstream import UpstreamClient

log = structlog.get_logger()


class ValuationRunner:
    """Runs independent pricing models via Agent 2 for all positions."""

    def __init__(self, client: UpstreamClient) -> None:
        self._client = client

    async def price_position(
        self,
        position: PositionInput,
        market_data: MarketDataSnapshot,
    ) -> ValuationResult:
        """Run the pricing model for a single position.

        Selects the appropriate Agent 2 endpoint based on product type:
          - Spot -> /pricing/fx-spot
          - Forward -> /pricing/fx-forward
          - Barrier/Option -> /pricing/fx-barrier or /pricing/fx-vanilla-option
        """
        pt_lower = position.product_type.lower()

        try:
            if any(kw in pt_lower for kw in ("barrier", "dnt", "kiko")):
                return await self._price_barrier(position, market_data)
            elif any(kw in pt_lower for kw in ("vanilla", "option")) and "barrier" not in pt_lower:
                return await self._price_vanilla_option(position, market_data)
            elif any(kw in pt_lower for kw in ("forward", "fwd", "ndf")):
                return await self._price_forward(position, market_data)
            else:
                return await self._price_spot(position, market_data)
        except Exception as exc:
            log.error(
                "valuation_runner_failed",
                position_id=position.position_id,
                product_type=position.product_type,
                error=str(exc),
            )
            raise

    async def _price_spot(
        self,
        position: PositionInput,
        market_data: MarketDataSnapshot,
    ) -> ValuationResult:
        """Price an FX spot position via Agent 2."""
        if market_data.spot_rate is None:
            raise ValueError(
                f"No spot rate available for {position.currency_pair}"
            )

        # Build quotes for the FX spot pricer
        # The pricer expects a list of quotes with bid/ask/mid
        spot_val = float(market_data.spot_rate)
        quotes = [
            {
                "source": "bloomberg",
                "bid": spot_val - 0.0001,
                "ask": spot_val + 0.0001,
                "timestamp": market_data.timestamp.isoformat() if market_data.timestamp else None,
            },
            {
                "source": "reuters",
                "bid": spot_val - 0.00015,
                "ask": spot_val + 0.00015,
                "timestamp": market_data.timestamp.isoformat() if market_data.timestamp else None,
            },
        ]

        try:
            result = await self._client.price_fx_spot(
                currency_pair=position.currency_pair,
                quotes=quotes,
            )
            ipv_price = Decimal(str(result.get("mid_rate", result.get("fair_value", spot_val))))
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=ipv_price,
                pricing_method=result.get("method", "median_mid"),
                model_name="fx_spot",
                greeks=result.get("greeks"),
                confidence=result.get("confidence"),
                pricing_source="agent2",
            )
        except ConnectionError:
            # Fallback: use market data directly if Agent 2 is unavailable
            log.warning(
                "spot_pricing_fallback",
                position_id=position.position_id,
                using="market_data_direct",
            )
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=market_data.spot_rate,
                pricing_method="market_data_direct",
                model_name="fx_spot_fallback",
                pricing_source="agent1_fallback",
            )

    async def _price_forward(
        self,
        position: PositionInput,
        market_data: MarketDataSnapshot,
    ) -> ValuationResult:
        """Price an FX forward position via Agent 2."""
        spot = float(market_data.spot_rate) if market_data.spot_rate else 1.0
        # Extract rates from yield curves, or use sensible defaults
        r_dom = self._extract_rate(market_data.yield_curve_dom, default=0.04)
        r_for = self._extract_rate(market_data.yield_curve_for, default=0.03)
        notional = float(position.notional)

        try:
            result = await self._client.price_fx_forward(
                spot=spot,
                r_dom=r_dom,
                r_for=r_for,
                maturity=1.0,  # 1Y forward
                notional=notional,
                currency_pair=position.currency_pair,
            )
            ipv_price = Decimal(str(result.get("forward_rate", result.get("fair_value", 0))))
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=ipv_price,
                pricing_method=result.get("method", "covered_interest_parity"),
                model_name="fx_forward",
                greeks=result.get("greeks"),
                pricing_source="agent2",
            )
        except ConnectionError:
            # Fallback: use forward rate from market data
            fallback_price = market_data.forward_rate or market_data.spot_rate or Decimal("0")
            log.warning(
                "forward_pricing_fallback",
                position_id=position.position_id,
            )
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=fallback_price,
                pricing_method="market_data_direct",
                model_name="fx_forward_fallback",
                pricing_source="agent1_fallback",
            )

    async def _price_barrier(
        self,
        position: PositionInput,
        market_data: MarketDataSnapshot,
    ) -> ValuationResult:
        """Price an FX barrier option via Agent 2."""
        spot = float(market_data.spot_rate) if market_data.spot_rate else 1.0
        lower_barrier = float(position.lower_barrier) if position.lower_barrier else spot * 0.9
        upper_barrier = float(position.upper_barrier) if position.upper_barrier else spot * 1.1
        vol = float(position.volatility) if position.volatility else 0.10
        r_dom = float(position.domestic_rate) if position.domestic_rate else 0.04
        r_for = float(position.foreign_rate) if position.foreign_rate else 0.03
        maturity = float(position.time_to_expiry) if position.time_to_expiry else 1.0
        notional = float(position.notional)
        barrier_type = position.barrier_type or "DNT"

        try:
            result = await self._client.price_fx_barrier(
                spot=spot,
                lower_barrier=lower_barrier,
                upper_barrier=upper_barrier,
                maturity=maturity,
                notional=notional,
                vol=vol,
                r_dom=r_dom,
                r_for=r_for,
                barrier_type=barrier_type,
            )
            ipv_price = Decimal(str(result.get("fair_value", 0)))
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=ipv_price,
                pricing_method=result.get("method", "monte_carlo"),
                model_name="fx_barrier",
                greeks=result.get("greeks"),
                confidence=result.get("confidence"),
                pricing_source="agent2",
            )
        except ConnectionError:
            # Fallback: use desk mark as IPV price (L3 positions may have no alternative)
            log.warning(
                "barrier_pricing_fallback",
                position_id=position.position_id,
            )
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=position.desk_mark,
                pricing_method="desk_mark_fallback",
                model_name="fx_barrier_fallback",
                pricing_source="desk_fallback",
            )

    async def _price_vanilla_option(
        self,
        position: PositionInput,
        market_data: MarketDataSnapshot,
    ) -> ValuationResult:
        """Price an FX vanilla option via Agent 2."""
        spot = float(market_data.spot_rate) if market_data.spot_rate else 1.0
        strike = float(position.desk_mark)  # Use desk mark as proxy for strike
        vol = float(position.volatility) if position.volatility else 0.10
        r_dom = float(position.domestic_rate) if position.domestic_rate else 0.04
        r_for = float(position.foreign_rate) if position.foreign_rate else 0.03
        maturity = float(position.time_to_expiry) if position.time_to_expiry else 1.0
        notional = float(position.notional)

        try:
            result = await self._client.price_fx_vanilla_option(
                spot=spot,
                strike=strike,
                maturity=maturity,
                vol=vol,
                r_dom=r_dom,
                r_for=r_for,
                notional=notional,
                option_type="call",
                currency_pair=position.currency_pair,
            )
            ipv_price = Decimal(str(result.get("fair_value", 0)))
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=ipv_price,
                pricing_method=result.get("method", "garman_kohlhagen"),
                model_name="fx_vanilla_option",
                greeks=result.get("greeks"),
                pricing_source="agent2",
            )
        except ConnectionError:
            log.warning(
                "vanilla_option_pricing_fallback",
                position_id=position.position_id,
            )
            return ValuationResult(
                position_id=position.position_id,
                ipv_price=position.desk_mark,
                pricing_method="desk_mark_fallback",
                model_name="fx_vanilla_fallback",
                pricing_source="desk_fallback",
            )

    def _extract_rate(self, yield_curve: Optional[dict], default: float = 0.04) -> float:
        """Extract a representative rate from a yield curve response."""
        if not yield_curve:
            return default
        # Try to get 1Y rate from the curve data
        tenors = yield_curve.get("tenors", yield_curve.get("rates", {}))
        if isinstance(tenors, dict):
            for key in ("1Y", "12M", "1.0"):
                if key in tenors:
                    return float(tenors[key])
            # Return the last tenor rate if available
            values = list(tenors.values())
            if values:
                return float(values[-1])
        elif isinstance(tenors, list) and len(tenors) > 0:
            # Assume list of {tenor, rate} objects
            for t in tenors:
                if isinstance(t, dict) and t.get("tenor") in ("1Y", "12M"):
                    return float(t["rate"])
            if isinstance(tenors[-1], dict):
                return float(tenors[-1].get("rate", default))
        return default

    async def price_all(
        self,
        positions: list[PositionInput],
        market_data: dict[str, MarketDataSnapshot],
    ) -> dict[str, ValuationResult]:
        """Price all positions concurrently.

        Returns a dict mapping position_id -> ValuationResult.
        """
        async def _safe_price(pos: PositionInput) -> tuple[str, ValuationResult]:
            md = market_data.get(pos.position_id)
            if md is None:
                md = MarketDataSnapshot(
                    position_id=pos.position_id,
                    currency_pair=pos.currency_pair,
                )
            return pos.position_id, await self.price_position(pos, md)

        tasks = [_safe_price(pos) for pos in positions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valuations: dict[str, ValuationResult] = {}
        for pos, result in zip(positions, results):
            if isinstance(result, Exception):
                log.error(
                    "valuation_failed",
                    position_id=pos.position_id,
                    error=str(result),
                )
                # Use desk mark as fallback IPV price
                valuations[pos.position_id] = ValuationResult(
                    position_id=pos.position_id,
                    ipv_price=pos.desk_mark,
                    pricing_method="error_fallback",
                    model_name="fallback",
                    pricing_source="desk_fallback",
                )
            else:
                pos_id, val_result = result
                valuations[pos_id] = val_result

        log.info(
            "valuation_run_complete",
            total=len(positions),
            agent2_priced=sum(
                1 for v in valuations.values() if v.pricing_source == "agent2"
            ),
        )
        return valuations

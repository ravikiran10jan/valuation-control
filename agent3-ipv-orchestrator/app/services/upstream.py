"""HTTP client for calling all upstream agents."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger()


class UpstreamClient:
    """Async HTTP client to communicate with all other agents in the system."""

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(settings.upstream_timeout_seconds)
        self._max_retries = settings.upstream_max_retries
        self._retry_delay = settings.upstream_retry_delay_seconds

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        json: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict[str, Any]:
        """Execute an HTTP request with retry logic."""
        last_error: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._client() as client:
                    response = await client.request(
                        method, url, json=json, params=params,
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                log.warning(
                    "upstream_http_error",
                    url=url,
                    status=exc.response.status_code,
                    attempt=attempt,
                    body=exc.response.text[:500],
                )
                if exc.response.status_code < 500:
                    raise
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
                last_error = exc
                log.warning(
                    "upstream_connection_error",
                    url=url,
                    error=str(exc),
                    attempt=attempt,
                )
            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_delay * attempt)

        raise ConnectionError(
            f"Failed to reach {url} after {self._max_retries} attempts: {last_error}"
        )

    # ── Agent 1: Data Layer ─────────────────────────────────────
    async def get_positions(
        self,
        asset_class: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch positions from Agent 1."""
        params: dict[str, Any] = {"limit": limit}
        if asset_class:
            params["asset_class"] = asset_class
        return await self._request_with_retry(
            "GET",
            f"{settings.agent1_base_url}/positions/",
            params=params,
        )

    async def get_position(self, position_id: int) -> dict[str, Any]:
        """Fetch a single position from Agent 1."""
        return await self._request_with_retry(
            "GET",
            f"{settings.agent1_base_url}/positions/{position_id}",
        )

    async def get_spot_rate(
        self,
        currency_pair: str,
        as_of: Optional[date] = None,
    ) -> dict[str, Any]:
        """Fetch spot rate from Agent 1 market data."""
        params = {}
        if as_of:
            params["date"] = as_of.isoformat()
        return await self._request_with_retry(
            "GET",
            f"{settings.agent1_base_url}/market-data/spot/{currency_pair}",
            params=params,
        )

    async def get_forward_points(
        self,
        currency_pair: str,
        tenor: str = "1Y",
    ) -> dict[str, Any]:
        """Fetch forward points from Agent 1."""
        return await self._request_with_retry(
            "GET",
            f"{settings.agent1_base_url}/market-data/forward-points/{currency_pair}",
            params={"tenor": tenor},
        )

    async def get_vol_surface(
        self,
        currency_pair: str,
        tenor: str = "1Y",
    ) -> dict[str, Any]:
        """Fetch vol surface from Agent 1."""
        return await self._request_with_retry(
            "GET",
            f"{settings.agent1_base_url}/market-data/vol-surface/{currency_pair}",
            params={"tenor": tenor},
        )

    async def get_yield_curve(self, curve_name: str) -> dict[str, Any]:
        """Fetch yield curve from Agent 1."""
        return await self._request_with_retry(
            "GET",
            f"{settings.agent1_base_url}/market-data/yield-curve/{curve_name}",
        )

    async def create_comparison(
        self,
        position_id: int,
        desk_mark: Decimal,
        vc_fair_value: Decimal,
        comparison_date: date,
    ) -> dict[str, Any]:
        """Store valuation comparison in Agent 1."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent1_base_url}/comparisons/",
            json={
                "position_id": position_id,
                "desk_mark": str(desk_mark),
                "vc_fair_value": str(vc_fair_value),
                "comparison_date": comparison_date.isoformat(),
            },
        )

    async def create_exception(
        self,
        position_id: int,
        difference: Decimal,
        difference_pct: Decimal,
        severity: str,
    ) -> dict[str, Any]:
        """Create an exception record in Agent 1."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent1_base_url}/exceptions/",
            json={
                "position_id": position_id,
                "difference": str(difference),
                "difference_pct": str(difference_pct),
                "severity": severity,
            },
        )

    async def escalate_exception(
        self,
        exception_id: int,
        level: int,
    ) -> dict[str, Any]:
        """Escalate an exception in Agent 1."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent1_base_url}/escalations/",
            json={
                "exception_id": exception_id,
                "target_level": level,
            },
        )

    async def add_to_committee_agenda(
        self,
        exception_id: int,
        position_id: int,
        difference: Decimal,
        meeting_date: date,
    ) -> dict[str, Any]:
        """Add an item to the VC committee agenda in Agent 1."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent1_base_url}/committee/agenda",
            json={
                "exception_id": exception_id,
                "position_id": position_id,
                "difference": str(difference),
                "meeting_date": meeting_date.isoformat(),
            },
        )

    # ── Agent 2: Pricing Engine ─────────────────────────────────
    async def price_fx_spot(
        self,
        currency_pair: str,
        quotes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Call Agent 2 FX spot pricer."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent2_base_url}/pricing/fx-spot",
            json={
                "currency_pair": currency_pair,
                "quotes": quotes,
            },
        )

    async def price_fx_forward(
        self,
        spot: float,
        r_dom: float,
        r_for: float,
        maturity: float,
        notional: float,
        currency_pair: str,
        currency: str = "USD",
    ) -> dict[str, Any]:
        """Call Agent 2 FX forward pricer."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent2_base_url}/pricing/fx-forward",
            json={
                "spot": spot,
                "r_dom": r_dom,
                "r_for": r_for,
                "maturity": maturity,
                "notional": notional,
                "currency_pair": currency_pair,
                "currency": currency,
            },
        )

    async def price_fx_barrier(
        self,
        spot: float,
        lower_barrier: float,
        upper_barrier: float,
        maturity: float,
        notional: float,
        vol: float,
        r_dom: float,
        r_for: float,
        barrier_type: str = "DNT",
        currency: str = "USD",
    ) -> dict[str, Any]:
        """Call Agent 2 FX barrier pricer."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent2_base_url}/pricing/fx-barrier",
            json={
                "spot": spot,
                "lower_barrier": lower_barrier,
                "upper_barrier": upper_barrier,
                "maturity": maturity,
                "notional": notional,
                "vol": vol,
                "r_dom": r_dom,
                "r_for": r_for,
                "barrier_type": barrier_type,
                "currency": currency,
            },
        )

    async def price_fx_vanilla_option(
        self,
        spot: float,
        strike: float,
        maturity: float,
        vol: float,
        r_dom: float,
        r_for: float,
        notional: float,
        option_type: str = "call",
        currency_pair: str = "EUR/USD",
        currency: str = "USD",
    ) -> dict[str, Any]:
        """Call Agent 2 FX vanilla option pricer."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent2_base_url}/pricing/fx-vanilla-option",
            json={
                "spot": spot,
                "strike": strike,
                "maturity": maturity,
                "vol": vol,
                "r_dom": r_dom,
                "r_for": r_for,
                "notional": notional,
                "option_type": option_type,
                "currency_pair": currency_pair,
                "currency": currency,
            },
        )

    # ── Agent 4: Dispute Workflow ───────────────────────────────
    async def create_dispute(
        self,
        position_id: int,
        exception_id: int,
        vc_fair_value: Decimal,
        desk_mark: Decimal,
        difference: Decimal,
        difference_pct: Decimal,
        vc_analyst: str = "ipv_orchestrator",
    ) -> dict[str, Any]:
        """Create a dispute in Agent 4."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent4_base_url}/disputes/",
            json={
                "position_id": position_id,
                "exception_id": exception_id,
                "vc_fair_value": str(vc_fair_value),
                "desk_mark": str(desk_mark),
                "difference": str(difference),
                "difference_pct": str(difference_pct),
                "vc_analyst": vc_analyst,
                "vc_position": "IPV price is the fair market value",
            },
        )

    async def get_dispute_summary(self) -> dict[str, Any]:
        """Get dispute summary from Agent 4."""
        return await self._request_with_retry(
            "GET",
            f"{settings.agent4_base_url}/disputes/summary",
        )

    # ── Agent 5: Reserve Calculations ───────────────────────────
    async def calculate_reserves(
        self,
        position: dict[str, Any],
        dealer_quotes: Optional[list[dict]] = None,
        model_results: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """Calculate all reserves for a position via Agent 5."""
        payload: dict[str, Any] = {
            "position": position,
        }
        if dealer_quotes:
            payload["dealer_quotes"] = dealer_quotes
        if model_results:
            payload["model_results"] = model_results
        return await self._request_with_retry(
            "POST",
            f"{settings.agent5_base_url}/reserves/calculate-all",
            json=payload,
        )

    async def get_reserve_summary(
        self,
        calculation_date: Optional[date] = None,
    ) -> dict[str, Any]:
        """Get reserve summary from Agent 5."""
        params = {}
        if calculation_date:
            params["calculation_date"] = calculation_date.isoformat()
        return await self._request_with_retry(
            "GET",
            f"{settings.agent5_base_url}/reserves/summary",
            params=params,
        )

    # ── Agent 6: Regulatory Reporting ───────────────────────────
    async def generate_pillar3_report(
        self, reporting_date: date,
    ) -> dict[str, Any]:
        """Generate Pillar 3 report via Agent 6."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent6_base_url}/reports/pillar3",
            params={"reporting_date": reporting_date.isoformat()},
        )

    async def generate_ifrs13_report(
        self, reporting_date: date,
    ) -> dict[str, Any]:
        """Generate IFRS 13 report via Agent 6."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent6_base_url}/reports/ifrs13",
            params={"reporting_date": reporting_date.isoformat()},
        )

    async def generate_pra110_report(
        self, reporting_date: date,
    ) -> dict[str, Any]:
        """Generate PRA110 report via Agent 6."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent6_base_url}/reports/pra110",
            params={"reporting_date": reporting_date.isoformat()},
        )

    async def generate_fry14q_report(
        self, reporting_date: date,
    ) -> dict[str, Any]:
        """Generate FR Y-14Q report via Agent 6."""
        return await self._request_with_retry(
            "POST",
            f"{settings.agent6_base_url}/reports/fry14q",
            params={"reporting_date": reporting_date.isoformat()},
        )

    # ── Health checks ───────────────────────────────────────────
    async def check_agent_health(self, agent_name: str, base_url: str) -> dict[str, Any]:
        """Check health of an upstream agent."""
        try:
            result = await self._request_with_retry("GET", f"{base_url}/health")
            return {"agent": agent_name, "status": "healthy", "detail": result}
        except Exception as exc:
            return {"agent": agent_name, "status": "unhealthy", "error": str(exc)}

    async def check_all_agents(self) -> list[dict[str, Any]]:
        """Check health of all upstream agents."""
        checks = await asyncio.gather(
            self.check_agent_health("agent1-data-layer", settings.agent1_base_url),
            self.check_agent_health("agent2-pricing-engine", settings.agent2_base_url),
            self.check_agent_health("agent4-dispute-workflow", settings.agent4_base_url),
            self.check_agent_health("agent5-reserve-calculations", settings.agent5_base_url),
            self.check_agent_health("agent6-regulatory-reporting", settings.agent6_base_url),
            return_exceptions=True,
        )
        results = []
        for check in checks:
            if isinstance(check, Exception):
                results.append({"agent": "unknown", "status": "error", "error": str(check)})
            else:
                results.append(check)
        return results

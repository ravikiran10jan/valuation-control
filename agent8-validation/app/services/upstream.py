"""HTTP client for calling all upstream agents (1-7).

Provides a unified async client with retry logic, health checks,
and typed response helpers for each agent's API surface.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger()


class UpstreamClient:
    """Async HTTP client that communicates with all upstream agents."""

    def __init__(self) -> None:
        self._timeout = httpx.Timeout(
            timeout=settings.upstream_timeout_seconds,
            connect=10.0,
        )
        self._max_retries = settings.upstream_max_retries
        self._retry_delay = settings.upstream_retry_delay_seconds

    # ── Internal helpers ─────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        """Create a fresh async client (context-managed externally)."""
        return httpx.AsyncClient(timeout=self._timeout)

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[Any] | None:
        """Make an HTTP request with retries and structured logging."""
        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                async with self._client() as client:
                    response = await client.request(
                        method, url, json=json, params=params
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
                )
                if exc.response.status_code < 500:
                    # Client errors are not retryable
                    break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
                last_error = exc
                log.warning(
                    "upstream_connect_error",
                    url=url,
                    error=str(exc),
                    attempt=attempt,
                )
            except Exception as exc:
                last_error = exc
                log.error(
                    "upstream_unexpected_error",
                    url=url,
                    error=str(exc),
                    attempt=attempt,
                )

            if attempt < self._max_retries:
                await asyncio.sleep(self._retry_delay * attempt)

        log.error("upstream_all_retries_exhausted", url=url, error=str(last_error))
        return None

    async def _get(self, url: str, **kwargs: Any) -> Any:
        return await self._request_with_retry("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs: Any) -> Any:
        return await self._request_with_retry("POST", url, **kwargs)

    # ── Health checks ────────────────────────────────────────────

    async def check_health(self, agent_name: str, base_url: str) -> bool:
        """Return True if the agent's /health endpoint responds OK."""
        try:
            async with self._client() as client:
                resp = await client.get(f"{base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    async def check_all_health(self) -> dict[str, bool]:
        """Check health of all upstream agents in parallel."""
        agent_urls = {
            "agent1-data-layer": settings.agent1_base_url,
            "agent2-pricing-engine": settings.agent2_base_url,
            "agent3-ipv-orchestrator": settings.agent3_base_url,
            "agent4-dispute-workflow": settings.agent4_base_url,
            "agent5-reserve-calculations": settings.agent5_base_url,
            "agent6-regulatory-reporting": settings.agent6_base_url,
            "agent7-dashboard": settings.agent7_base_url,
        }
        tasks = {
            name: self.check_health(name, url)
            for name, url in agent_urls.items()
        }
        results: dict[str, bool] = {}
        for name, coro in tasks.items():
            results[name] = await coro
        return results

    # ── Agent 1: Data Layer ──────────────────────────────────────

    async def get_positions(self) -> list[dict[str, Any]] | None:
        """Fetch all positions from agent 1."""
        return await self._get(f"{settings.agent1_base_url}/positions/")

    async def get_position(self, position_id: str) -> dict[str, Any] | None:
        """Fetch a single position from agent 1."""
        return await self._get(f"{settings.agent1_base_url}/positions/{position_id}")

    async def get_market_data(self, currency_pair: str) -> dict[str, Any] | None:
        """Fetch market data for a currency pair from agent 1."""
        return await self._get(
            f"{settings.agent1_base_url}/market-data/{currency_pair}"
        )

    async def get_dealer_quotes(self, position_id: str) -> list[dict[str, Any]] | None:
        """Fetch dealer quotes for a position from agent 1."""
        return await self._get(
            f"{settings.agent1_base_url}/dealer-quotes/{position_id}"
        )

    # ── Agent 2: Pricing Engine ──────────────────────────────────

    async def price_fx_spot(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Call FX spot pricing on agent 2."""
        return await self._post(
            f"{settings.agent2_base_url}/pricing/fx-spot", json=payload
        )

    async def price_fx_forward(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Call FX forward pricing on agent 2."""
        return await self._post(
            f"{settings.agent2_base_url}/pricing/fx-forward", json=payload
        )

    async def price_fx_barrier(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Call FX barrier pricing on agent 2."""
        return await self._post(
            f"{settings.agent2_base_url}/pricing/fx-barrier", json=payload
        )

    async def get_tolerances(
        self, asset_class: str, product_type: str
    ) -> dict[str, Any] | None:
        """Fetch tolerance thresholds from agent 2."""
        return await self._post(
            f"{settings.agent2_base_url}/pricing/tolerances",
            json={"asset_class": asset_class, "product_type": product_type},
        )

    # ── Agent 3: IPV Orchestrator ────────────────────────────────

    async def get_ipv_results(self) -> list[dict[str, Any]] | None:
        """Fetch all IPV results from agent 3."""
        return await self._get(f"{settings.agent3_base_url}/ipv/results")

    async def get_ipv_summary(self) -> dict[str, Any] | None:
        """Fetch IPV summary dashboard data from agent 3."""
        return await self._get(f"{settings.agent3_base_url}/ipv/summary")

    async def run_ipv_pipeline(self) -> dict[str, Any] | None:
        """Trigger a full IPV pipeline run on agent 3."""
        return await self._post(f"{settings.agent3_base_url}/ipv/run")

    # ── Agent 5: Reserve Calculations ────────────────────────────

    async def get_fva(self, position_id: str) -> dict[str, Any] | None:
        """Fetch FVA calculation for a position from agent 5."""
        return await self._get(
            f"{settings.agent5_base_url}/fva/{position_id}"
        )

    async def get_fva_aggregate(self) -> dict[str, Any] | None:
        """Fetch aggregate FVA from agent 5."""
        return await self._get(f"{settings.agent5_base_url}/fva/aggregate")

    async def get_ava(self, position_id: str) -> dict[str, Any] | None:
        """Fetch AVA calculation for a position from agent 5."""
        return await self._get(
            f"{settings.agent5_base_url}/ava/{position_id}"
        )

    async def get_ava_detailed(self, position_id: str) -> dict[str, Any] | None:
        """Fetch detailed AVA with sub-calculations from agent 5."""
        return await self._get(
            f"{settings.agent5_base_url}/ava/{position_id}/detailed"
        )

    async def get_model_reserve(self, position_id: str) -> dict[str, Any] | None:
        """Fetch model reserve for a position from agent 5."""
        return await self._get(
            f"{settings.agent5_base_url}/model-reserve/{position_id}"
        )

    async def get_day1_pnl(self, position_id: str) -> dict[str, Any] | None:
        """Fetch Day 1 P&L for a position from agent 5."""
        return await self._get(
            f"{settings.agent5_base_url}/day1-pnl/{position_id}"
        )

    async def get_reserve_summary(self) -> dict[str, Any] | None:
        """Fetch overall reserve summary from agent 5."""
        return await self._get(f"{settings.agent5_base_url}/reserves/summary")

    # ── Agent 6: Regulatory Reporting ────────────────────────────

    async def get_ifrs13_report(self) -> dict[str, Any] | None:
        """Fetch IFRS 13 fair value hierarchy report from agent 6."""
        return await self._post(f"{settings.agent6_base_url}/reports/ifrs13")

    async def get_pillar3_report(self) -> dict[str, Any] | None:
        """Fetch Pillar 3 capital adequacy report from agent 6."""
        return await self._post(f"{settings.agent6_base_url}/reports/pillar3")

    async def get_capital_adequacy(self) -> dict[str, Any] | None:
        """Fetch capital adequacy data from agent 6."""
        return await self._post(f"{settings.agent6_base_url}/reports/pillar3")

    # ── Agent 7: Dashboard ───────────────────────────────────────

    async def get_dashboard_summary(self) -> dict[str, Any] | None:
        """Fetch dashboard summary from agent 7."""
        return await self._get(f"{settings.agent7_base_url}/api/summary")

    async def get_dashboard_positions(self) -> list[dict[str, Any]] | None:
        """Fetch position list from the dashboard agent."""
        return await self._get(f"{settings.agent7_base_url}/api/positions")

"""HTTP client for upstream microservices (Agent 1 & Agent 5)."""

from __future__ import annotations

import httpx
import structlog

from app.core.config import settings

log = structlog.get_logger()

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    """Get or create the shared httpx client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


async def close_client() -> None:
    """Close the shared httpx client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def agent1_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 1 (Data Layer).

    Args:
        path: API path (e.g., "/positions/").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent1_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent1_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent1_unreachable", url=url)
        raise


async def agent1_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 1."""
    client = await get_client()
    url = f"{settings.agent1_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent1_post_failed", path=path, status=exc.response.status_code)
        raise


async def agent5_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 5 (Reserve Calculations).

    Args:
        path: API path (e.g., "/reserves/summary").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent5_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent5_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent5_unreachable", url=url)
        raise


async def agent5_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 5."""
    client = await get_client()
    url = f"{settings.agent5_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent5_post_failed", path=path, status=exc.response.status_code)
        raise

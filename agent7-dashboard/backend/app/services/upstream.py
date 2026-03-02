"""HTTP client for upstream microservices (Agents 1–8)."""

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


# ── Agent 1 — Data Layer (port 8001) ────────────────────────────


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


# ── Agent 2 — Pricing Engine (port 8002) ────────────────────────


async def agent2_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 2 (Pricing Engine).

    Args:
        path: API path (e.g., "/pricing/greeks/7").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent2_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent2_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent2_unreachable", url=url)
        raise


async def agent2_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 2."""
    client = await get_client()
    url = f"{settings.agent2_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent2_post_failed", path=path, status=exc.response.status_code)
        raise


# ── Agent 3 — IPV Orchestrator (port 8003) ──────────────────────


async def agent3_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 3 (IPV Orchestrator).

    Args:
        path: API path (e.g., "/ipv/runs").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent3_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent3_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent3_unreachable", url=url)
        raise


async def agent3_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 3."""
    client = await get_client()
    url = f"{settings.agent3_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent3_post_failed", path=path, status=exc.response.status_code)
        raise


# ── Agent 4 — Dispute Workflow (port 8004) ──────────────────────


async def agent4_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 4 (Dispute Workflow).

    Args:
        path: API path (e.g., "/disputes/").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent4_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent4_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent4_unreachable", url=url)
        raise


async def agent4_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 4."""
    client = await get_client()
    url = f"{settings.agent4_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent4_post_failed", path=path, status=exc.response.status_code)
        raise


# ── Agent 5 — Reserve Calculations (port 8005) ─────────────────


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


# ── Agent 6 — Regulatory Reporting (port 8006) ─────────────────


async def agent6_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 6 (Regulatory Reporting).

    Args:
        path: API path (e.g., "/reports/capital-adequacy").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent6_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent6_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent6_unreachable", url=url)
        raise


async def agent6_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 6."""
    client = await get_client()
    url = f"{settings.agent6_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent6_post_failed", path=path, status=exc.response.status_code)
        raise


# ── Agent 8 — Validation (port 8008) ────────────────────────────


async def agent8_get(path: str, params: dict | None = None) -> dict | list:
    """GET request to Agent 8 (Validation).

    Args:
        path: API path (e.g., "/validation/report").
        params: Query parameters.

    Returns:
        Parsed JSON response.

    Raises:
        httpx.HTTPStatusError: On non-2xx response.
    """
    client = await get_client()
    url = f"{settings.agent8_url}{path}"
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent8_request_failed", path=path, status=exc.response.status_code)
        raise
    except httpx.ConnectError:
        log.error("agent8_unreachable", url=url)
        raise


async def agent8_post(path: str, json: dict | None = None) -> dict | list:
    """POST request to Agent 8."""
    client = await get_client()
    url = f"{settings.agent8_url}{path}"
    try:
        resp = await client.post(url, json=json)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as exc:
        log.error("agent8_post_failed", path=path, status=exc.response.status_code)
        raise

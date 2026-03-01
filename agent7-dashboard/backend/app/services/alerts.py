"""Alert service for real-time monitoring.

Polls Agent 1 for new RED exceptions and produces alerts
for the WebSocket broadcast.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

import structlog

from app.services.upstream import agent1_get

log = structlog.get_logger()


class AlertService:
    """Monitors upstream services and produces alerts."""

    def __init__(self) -> None:
        self._subscribers: list[Callable] = []
        self._last_check: datetime = datetime.now(timezone.utc)
        self._known_exception_ids: set[int] = set()

    def subscribe(self, callback: Callable) -> Callable:
        """Register a callback for new alerts. Returns unsubscribe function."""
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)

    async def check_for_alerts(self) -> list[dict]:
        """Poll upstream services for alert-worthy events.

        Returns:
            List of new alert dicts.
        """
        alerts: list[dict] = []

        # Check for new RED exceptions
        try:
            red_exceptions = await agent1_get(
                "/exceptions/",
                params={"severity": "RED", "status": "OPEN", "limit": 50},
            )
            for exc in red_exceptions:
                exc_id = exc.get("exception_id")
                if exc_id and exc_id not in self._known_exception_ids:
                    self._known_exception_ids.add(exc_id)
                    alerts.append({
                        "id": str(uuid4()),
                        "severity": "high",
                        "title": f"New RED exception: Position #{exc.get('position_id')}",
                        "message": f"Difference: {exc.get('difference_pct', 0):.1f}%",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "read": False,
                    })
        except Exception:
            log.warning("alert_check_red_exceptions_failed")

        # Check for aged exceptions (> 3 days open RED)
        try:
            all_open = await agent1_get(
                "/exceptions/",
                params={"severity": "RED", "limit": 50},
            )
            aged = [e for e in all_open if e.get("days_open", 0) > 3 and e.get("status") != "RESOLVED"]
            if len(aged) > 0:
                alerts.append({
                    "id": str(uuid4()),
                    "severity": "medium",
                    "title": f"{len(aged)} RED exceptions aged > 3 days",
                    "message": "Review required by VC Manager",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "read": False,
                })
        except Exception:
            log.warning("alert_check_aged_exceptions_failed")

        # Check Agent 1 health
        try:
            health = await agent1_get("/health")
            if health.get("status") != "ok":
                alerts.append({
                    "id": str(uuid4()),
                    "severity": "high",
                    "title": "Data Layer service degraded",
                    "message": f"Status: {health.get('status', 'unknown')}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "read": False,
                })
        except Exception:
            alerts.append({
                "id": str(uuid4()),
                "severity": "high",
                "title": "Data Layer service unreachable",
                "message": "Agent 1 is not responding",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "read": False,
            })

        # Notify subscribers
        for alert in alerts:
            for sub in self._subscribers:
                try:
                    await sub(alert)
                except Exception:
                    log.warning("alert_subscriber_error")

        self._last_check = datetime.now(timezone.utc)
        return alerts


# Singleton
alert_service = AlertService()

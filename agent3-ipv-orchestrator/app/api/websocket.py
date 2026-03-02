"""WebSocket handler for real-time IPV pipeline progress updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
import structlog

from app.models.schemas import ProgressUpdate

log = structlog.get_logger()


class ConnectionManager:
    """Manages WebSocket connections for real-time progress updates.

    Supports multiple concurrent connections and broadcasting updates
    to all connected clients or to clients subscribed to a specific run_id.
    """

    def __init__(self) -> None:
        # Maps run_id -> set of websocket connections
        self._subscriptions: dict[str, set[WebSocket]] = {}
        # All active connections (for broadcast)
        self._active_connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, run_id: str | None = None) -> None:
        """Accept a new WebSocket connection and optionally subscribe to a run."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
            if run_id:
                if run_id not in self._subscriptions:
                    self._subscriptions[run_id] = set()
                self._subscriptions[run_id].add(websocket)
        log.info("ws_connected", run_id=run_id, total_connections=len(self._active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a WebSocket connection from all subscriptions."""
        async with self._lock:
            self._active_connections.discard(websocket)
            # Remove from all run subscriptions
            for run_id in list(self._subscriptions.keys()):
                self._subscriptions[run_id].discard(websocket)
                if not self._subscriptions[run_id]:
                    del self._subscriptions[run_id]
        log.info("ws_disconnected", total_connections=len(self._active_connections))

    async def subscribe(self, websocket: WebSocket, run_id: str) -> None:
        """Subscribe a connected WebSocket to a specific run."""
        async with self._lock:
            if run_id not in self._subscriptions:
                self._subscriptions[run_id] = set()
            self._subscriptions[run_id].add(websocket)

    async def send_update(self, update: ProgressUpdate) -> None:
        """Send a progress update to all clients subscribed to the run."""
        message = update.model_dump_json()

        async with self._lock:
            subscribers = self._subscriptions.get(update.run_id, set()).copy()

        if not subscribers:
            # No specific subscribers — broadcast to all
            subscribers = self._active_connections.copy()

        disconnected: list[WebSocket] = []
        for ws in subscribers:
            try:
                await ws.send_text(message)
            except (WebSocketDisconnect, RuntimeError, Exception) as exc:
                log.warning("ws_send_failed", error=str(exc))
                disconnected.append(ws)

        # Clean up disconnected clients
        for ws in disconnected:
            await self.disconnect(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all connected clients."""
        text = json.dumps(message, default=str)
        async with self._lock:
            connections = self._active_connections.copy()

        disconnected: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_text(text)
            except (WebSocketDisconnect, RuntimeError, Exception):
                disconnected.append(ws)

        for ws in disconnected:
            await self.disconnect(ws)

    @property
    def active_count(self) -> int:
        """Return the number of active WebSocket connections."""
        return len(self._active_connections)

    @property
    def subscriptions(self) -> dict[str, int]:
        """Return a dict of run_id -> subscriber count."""
        return {rid: len(subs) for rid, subs in self._subscriptions.items()}


# Global connection manager instance
manager = ConnectionManager()


async def progress_callback(update: ProgressUpdate) -> None:
    """Callback function passed to IPVPipeline for sending progress updates."""
    await manager.send_update(update)

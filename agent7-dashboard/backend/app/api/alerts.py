"""Alert API routes with WebSocket broadcast."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import structlog

from app.services.alerts import alert_service

log = structlog.get_logger()
router = APIRouter(tags=["Alerts"])

# Track active WebSocket connections
_connections: set[WebSocket] = set()


@router.get("/api/alerts")
async def get_recent_alerts():
    """Trigger an alert check and return new alerts."""
    return await alert_service.check_for_alerts()


@router.websocket("/ws/alerts")
async def websocket_alerts(ws: WebSocket):
    """WebSocket endpoint for real-time alert streaming.

    Clients connect here to receive push notifications
    whenever a new alert is generated.
    """
    await ws.accept()
    _connections.add(ws)
    log.info("ws_client_connected", total=len(_connections))

    # Register a subscriber that pushes alerts to this connection
    async def push_alert(alert: dict) -> None:
        try:
            await ws.send_text(json.dumps(alert))
        except Exception:
            pass

    unsubscribe = alert_service.subscribe(push_alert)

    try:
        # Keep connection alive — read pings/pongs
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe()
        _connections.discard(ws)
        log.info("ws_client_disconnected", total=len(_connections))


async def broadcast_alert(alert: dict) -> None:
    """Broadcast an alert to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    for ws in _connections:
        try:
            await ws.send_text(json.dumps(alert))
        except Exception:
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)

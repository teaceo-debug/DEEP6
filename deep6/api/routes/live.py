"""Live WebSocket endpoint + test-broadcast HTTP helper + session status.

Per D-10: /ws/live is the single multiplexed WebSocket for all real-time streams.
Clients receive LiveBarMessage, LiveSignalMessage, LiveScoreMessage, LiveStatusMessage
discriminated by the 'type' field.

Per D-09: localhost-only, no auth middleware on this endpoint.

Per T-11-01: POST /api/live/test-broadcast validates the incoming payload against
the LiveMessage discriminated union before broadcasting, so a malformed push cannot
crash listeners. Invalid payloads are rejected with HTTP 422.

Phase 11.3-r3:
GET /api/session/status — HTTP snapshot of the same payload WSManager sends over WS.
Useful for monitoring scripts / curl health checks without opening a WS connection.
The initial LiveStatusMessage sent on WS connect is now delegated to WSManager so
active_clients and other counters are already populated.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter, ValidationError

from deep6.api.schemas import LiveMessage, LiveStatusMessage

router = APIRouter(tags=["live"])

# TypeAdapter for LiveMessage discriminated union — used by test-broadcast
# to validate arbitrary JSON against the known message shapes (T-11-01).
_live_message_adapter: TypeAdapter = TypeAdapter(LiveMessage)


@router.websocket("/ws/live")
async def live_ws(websocket: WebSocket) -> None:
    """Accept a WebSocket connection for the live data stream.

    On connect: WSManager.connect() accepts the handshake and schedules an
    initial status snapshot (with accurate active_clients count) within 50 ms.

    The connection is held open until the client disconnects. The server is
    push-only; any messages sent by the client are drained and discarded.
    The WSManager handles fan-out; callers push messages via broadcast().
    """
    manager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        # Drain client messages (server is push-only; client shouldn't send)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)


@router.post("/api/live/test-broadcast")
async def test_broadcast(request: Request, payload: dict) -> dict:
    """Broadcast an arbitrary message to all connected WS clients.

    Intended for: Python trading engine internal push + integration testing.

    Per T-11-01: validates payload against LiveMessage discriminated union
    before broadcasting. Invalid shape → 422 Unprocessable Entity.
    """
    try:
        _live_message_adapter.validate_python(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    manager = request.app.state.ws_manager
    await manager.broadcast(payload)
    return {"status": "broadcast", "subscribers": len(manager.active)}


@router.get("/api/session/status", response_model=LiveStatusMessage, tags=["session"])
async def session_status(request: Request) -> LiveStatusMessage:
    """Return the current session status as an HTTP response.

    Same payload shape as the LiveStatusMessage broadcast over WebSocket.
    Useful for operators who want to curl the backend without opening a WS
    connection, or for monitoring scripts / uptime checks.

    Example:
        curl http://localhost:8000/api/session/status
    """
    manager = request.app.state.ws_manager
    snapshot = manager.status_snapshot()
    return LiveStatusMessage(**snapshot)

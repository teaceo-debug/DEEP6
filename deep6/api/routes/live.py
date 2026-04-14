"""Live WebSocket endpoint + test-broadcast HTTP helper.

Per D-10: /ws/live is the single multiplexed WebSocket for all real-time streams.
Clients receive LiveBarMessage, LiveSignalMessage, LiveScoreMessage, LiveStatusMessage
discriminated by the 'type' field.

Per D-09: localhost-only, no auth middleware on this endpoint.

Per T-11-01: POST /api/live/test-broadcast validates the incoming payload against
the LiveMessage discriminated union before broadcasting, so a malformed push cannot
crash listeners. Invalid payloads are rejected with HTTP 422.
"""
from __future__ import annotations

import time

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

    On connect: sends an initial LiveStatusMessage(connected=True) so the
    client status dot can turn green immediately.

    The connection is held open until the client disconnects. The server is
    push-only; any messages sent by the client are drained and discarded.
    The WSManager handles fan-out; callers push messages via broadcast().
    """
    manager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        # Send initial connected status immediately
        await websocket.send_json(
            LiveStatusMessage(
                connected=True,
                pnl=0.0,
                circuit_breaker_active=False,
                feed_stale=False,
                ts=time.time(),
            ).model_dump()
        )
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

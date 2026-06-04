"""DepthRadar ingestion + query routes."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from deep6.api.routes.ws import ws_manager
from deep6.api.schemas import DepthradarEpisodeOut, LiveDepthradarMessage, WallSnapshotOut

router = APIRouter(tags=["depthradar"])


@router.post("/events/depthradar")
async def ingest_depthradar_snapshots(
    walls: list[WallSnapshotOut],
    request: Request,
) -> dict:
    """Persist DepthRadar wall snapshots and broadcast them to WebSocket clients."""
    store = request.app.state.event_store
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    for wall in walls:
        await store.insert_depthradar_snapshot(
            {
                "episode_id": wall.episode_id,
                "timestamp": timestamp,
                "features_json": wall.model_dump(),
                "intent_prediction": wall.intent,
                "intent_confidence": wall.intent_confidence,
                "state": wall.state,
            }
        )

    await ws_manager.broadcast(
        LiveDepthradarMessage(walls=walls, episode_count=len(walls)).model_dump()
    )
    return {"status": "stored", "count": len(walls)}


@router.get("/api/depthradar/episodes")
async def list_depthradar_episodes(
    request: Request,
    session_date: str | None = None,
    limit: int = 100,
) -> list[DepthradarEpisodeOut]:
    """List DepthRadar episodes."""
    store = request.app.state.event_store
    rows = await store.fetch_depthradar_episodes(session_date=session_date, limit=limit)
    return [DepthradarEpisodeOut.model_validate(row) for row in rows]


@router.get("/api/depthradar/touches")
async def list_depthradar_touches(
    request: Request,
    episode_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """List DepthRadar touch events."""
    store = request.app.state.event_store
    return await store.fetch_depthradar_touches(episode_id=episode_id, limit=limit)


@router.get("/api/depthradar/metrics")
async def get_depthradar_metrics(request: Request) -> dict:
    """Return DepthRadar model performance stats."""
    store = request.app.state.event_store
    return await store.fetch_depthradar_metrics()

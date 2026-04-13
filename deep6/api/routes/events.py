"""Event ingestion routes — POST /events/signal and POST /events/trade.

Per D-02: Events arrive from the internal trading engine (scorer and PaperTrader).
Per T-09-03: Callers in the hot loop should wrap these calls in asyncio.shield()
             so a slow DB never blocks the signal pipeline.
"""
from __future__ import annotations

from fastapi import APIRouter, Request

from deep6.api.schemas import SignalEventIn, TradeEventIn

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/signal")
async def ingest_signal_event(ev: SignalEventIn, request: Request) -> dict:
    """Persist a signal event from the scorer.

    Caller (hot loop at bar close) should wrap in asyncio.shield() per T-09-03.
    """
    store = request.app.state.event_store
    inserted_id = await store.insert_signal_event(ev)
    return {"id": inserted_id, "status": "stored"}


@router.post("/trade")
async def ingest_trade_event(ev: TradeEventIn, request: Request) -> dict:
    """Persist a trade event from PaperTrader / ExecutionEngine."""
    store = request.app.state.event_store
    inserted_id = await store.insert_trade_event(ev)
    return {"id": inserted_id, "status": "stored"}

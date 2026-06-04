"""PO3 Daily Bias Engine — FastAPI routes.

POST /api/bias/tv-webhook   Receive Pine Script TradingView alerts
GET  /api/bias/current      Latest synthesized bias
GET  /api/bias/history      Last N bias states (default 24)

Flow:
    TradingView Pine Alert → POST /api/bias/tv-webhook
        → background: NewsEngine.fetch_all() + ClaudeSynthesizer
        → cache in app.state.bias_state
        → broadcast LiveBiasMessage via WSManager (/ws/live)
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Request

from deep6.api.schemas import LiveBiasMessage
from deep6.bias_engine.claude_synth import ClaudeSynthesizer
from deep6.bias_engine.models import (
    BiasDirection,
    DailyBiasScore,
    JudasStatus,
    PO3BiasState,
    PO3Phase,
    TradingViewWebhookPayload,
)
from deep6.bias_engine.news_engine import (
    NewsEngine,
    aggregate_news_score,
    compute_macro_confidence_multiplier,
)
from deep6.bias_engine.po3_detector import score_from_snapshot

router = APIRouter(prefix="/api/bias", tags=["bias"])

_MAX_HISTORY = 48
_synth = ClaudeSynthesizer()


@router.post("/tv-webhook")
async def receive_tv_webhook(
    payload: TradingViewWebhookPayload,
    background_tasks: BackgroundTasks,
    request: Request,
) -> dict:
    """Receive Pine Script alert and trigger async bias synthesis.

    Returns immediately with ack; synthesis runs in background so the
    HTTP response isn't blocked by Claude API latency (~1-2s).
    """
    background_tasks.add_task(_synthesize_and_broadcast, payload, request)
    return {
        "status": "accepted",
        "event": payload.event,
        "bias": payload.bias,
        "bull_pts": payload.bull_pts,
        "bear_pts": payload.bear_pts,
        "phase": payload.phase,
        "judas": payload.judas_bull or payload.judas_bear,
    }


@router.get("/current")
async def get_current_bias(request: Request) -> dict:
    """Return the latest synthesized DailyBiasScore."""
    bias: DailyBiasScore | None = getattr(request.app.state, "bias_state", None)
    if bias is None:
        return {"status": "no_data", "message": "No bias yet — send a Pine Script webhook first."}
    return bias.model_dump(mode="json")


@router.get("/history")
async def get_bias_history(request: Request, n: int = 24) -> list[dict]:
    """Return last N synthesized bias states."""
    history: list[DailyBiasScore] = getattr(request.app.state, "bias_history", [])
    return [b.model_dump(mode="json") for b in history[-n:]]


# ──────────────────────────────────────────────────────────────────────────────
# Background synthesis task
# ──────────────────────────────────────────────────────────────────────────────

async def _synthesize_and_broadcast(
    payload: TradingViewWebhookPayload,
    request: Request,
) -> None:
    """Background: fetch news → synthesize → cache → broadcast."""
    try:
        po3_state = _payload_to_state(payload)

        async with NewsEngine() as eng:
            news_items, macro_events = await eng.fetch_all()

        macro_conf = compute_macro_confidence_multiplier(macro_events)
        news_score = aggregate_news_score(news_items)

        bias_score = await _synth.build_final_score(
            po3=po3_state,
            news=news_items,
            macro=macro_events,
            news_score=news_score,
            macro_conf=macro_conf,
        )

        # Store latest + history
        request.app.state.bias_state = bias_score
        history: list[DailyBiasScore] = getattr(request.app.state, "bias_history", [])
        history.append(bias_score)
        if len(history) > _MAX_HISTORY:
            history = history[-_MAX_HISTORY:]
        request.app.state.bias_history = history

        # Broadcast via live WebSocket
        ws = getattr(request.app.state, "ws_manager", None)
        if ws:
            msg = LiveBiasMessage(
                direction=bias_score.direction.value,
                score=bias_score.score,
                confidence=bias_score.confidence,
                bull_pts=po3_state.bull_pts,
                bear_pts=po3_state.bear_pts,
                phase=po3_state.phase.value,
                judas_status=po3_state.judas_status.value,
                technical_score=bias_score.technical_score,
                news_score=bias_score.news_score,
                ai_score=bias_score.ai_score,
                ai_reasoning=bias_score.ai_reasoning,
                ai_key_triggers=bias_score.ai_key_triggers,
                macro_blackout=bias_score.macro_blackout,
                divergence_warning=bias_score.divergence_warning or "",
                ts=bias_score.timestamp.timestamp(),
            )
            await ws.broadcast(msg.model_dump(mode="json"))

    except Exception:
        pass  # Synthesis errors are non-fatal — live trading must not crash


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _payload_to_state(p: TradingViewWebhookPayload) -> PO3BiasState:
    """Convert TradingView webhook JSON to a PO3BiasState for scoring."""
    bias_upper = (p.bias or "NEUTRAL").upper()
    direction_map = {
        "BULLISH": BiasDirection.BULL,
        "BEARISH": BiasDirection.BEAR,
        "NEUTRAL": BiasDirection.NEUTRAL,
    }
    direction = direction_map.get(bias_upper, BiasDirection.NEUTRAL)
    if p.bull_pts >= 5:
        direction = BiasDirection.STRONG_BULL
    elif p.bear_pts >= 5:
        direction = BiasDirection.STRONG_BEAR

    if p.judas_bull:
        judas = JudasStatus.BULL_CONFIRMED
    elif p.judas_bear:
        judas = JudasStatus.BEAR_CONFIRMED
    elif p.swept_lo:
        judas = JudasStatus.SWEPT_LO
    elif p.swept_hi:
        judas = JudasStatus.SWEPT_HI
    else:
        judas = JudasStatus.NONE

    phase_map = {
        "Accumulation": PO3Phase.ACCUMULATION,
        "Manipulation": PO3Phase.MANIPULATION,
        "Distribution":  PO3Phase.DISTRIBUTION,
    }
    phase = phase_map.get(p.phase, PO3Phase.BETWEEN)

    pd_eq = (p.pd_h + p.pd_l) / 2.0 if p.pd_h and p.pd_l else None
    asia_eq = (p.asia_hi + p.asia_lo) / 2.0 if p.asia_hi and p.asia_lo else None

    return PO3BiasState(
        bull_pts=p.bull_pts,
        bear_pts=p.bear_pts,
        direction=direction,
        phase=phase,
        above_midnight_open=p.above_mo,
        above_weekly_open=p.above_wo,
        in_discount=p.in_discount,
        judas_status=judas,
        midnight_open=p.mo_px,
        weekly_open=p.wo_px,
        pd_high=p.pd_h,
        pd_low=p.pd_l,
        pd_eq=pd_eq,
        asia_high=p.asia_hi,
        asia_low=p.asia_lo,
        asia_eq=asia_eq,
        current_close=p.close,
        timestamp=datetime.now(tz=timezone.utc),
    )

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from flashalpha import FlashAlpha, RateLimitError

from nq_atlas.flow import FlowEngine
from nq_atlas.massive_client import MassiveClient
from nq_atlas.nq_mapper import map_qqq_to_nq
from scripts.massive_gex_map_service_v2 import (
    CONFLUENCE_MERGE_WINDOW_PTS,
    OPEN_SPACE_THRESHOLD_PTS,
    compute_health_state,
    default_output_path as v2_default_output_path,
    detect_confluence_zones,
    detect_open_space_lanes,
    iso,
    load_env_files,
    now_utc,
    write_atomic,
)

LOG = logging.getLogger("options_decision_surface_v3")
SCHEMA_V3 = "deep6.options_decision_surface.v3"
SERVICE_NAME = "options_decision_surface_v3"
SERVICE_VERSION = "3.0.0"
_LAST_GOOD_PAYLOAD: dict[str, Any] | None = None


def default_output_path() -> Path:
    v2 = v2_default_output_path()
    return v2.with_name("options_decision_surface_v3.json")


def get_flashalpha_key(cli_key: str | None = None) -> str:
    load_env_files()
    key = cli_key or os.getenv("FLASHALPHA_API_KEY") or ""
    if not key:
        raise SystemExit("Missing FLASHALPHA_API_KEY. Put it in .env or pass --flashalpha-api-key.")
    return key


def get_massive_key(cli_key: str | None = None) -> str:
    load_env_files()
    key = cli_key or os.getenv("MASSIVE_API_KEY") or os.getenv("NQ_ATLAS_MASSIVE_API_KEY") or ""
    if not key:
        raise SystemExit("Missing MASSIVE_API_KEY (or NQ_ATLAS_MASSIVE_API_KEY).")
    return key


@dataclass(slots=True)
class StructuralLevel:
    level_id: str
    structural_source: str
    behavior_state: str
    qqq_price: float
    nq_price: float
    gex_value: float
    confidence_score: float
    tier: str
    action_hint: str
    selected_because: str
    is_pinned: bool
    metadata: dict[str, Any]


def classify_regime(summary: dict[str, Any], zero_dte: dict[str, Any]) -> dict[str, Any]:
    exposures = summary.get("exposures") or {}
    net_gex = float(exposures.get("net_gex", 0) or 0)
    net_dex = float(exposures.get("net_dex", 0) or 0)
    net_vex = float(exposures.get("net_vex", 0) or 0)
    net_chex = float(exposures.get("net_chex", 0) or 0)
    fa_regime = str(summary.get("regime", "") or "").lower()

    zte_regime = (zero_dte.get("regime") or {})
    zte_label = str(zte_regime.get("label", "") or "")
    pin_risk = float((zero_dte.get("pin_risk") or {}).get("pin_score", 0) or 0)
    hours_to_close = float(zero_dte.get("time_to_close_hours", 0) or 0)

    if pin_risk >= 70:
        regime_state = "PINNED"
    elif "pre" in zte_label.lower() or "event" in zte_label.lower():
        regime_state = "PRE_EVENT"
    elif abs(net_chex) > abs(net_vex) * 1.2 and hours_to_close <= 2.5 and abs(net_chex) > 0:
        regime_state = "CHARM_DOMINATED"
    elif abs(net_vex) > abs(net_chex) * 1.2 and abs(net_vex) > 0:
        regime_state = "VANNA_DOMINATED"
    elif "negative" in fa_regime or net_gex < 0:
        regime_state = "NEGATIVE_GAMMA_EXPANSION"
    elif "positive" in fa_regime or net_gex > 0:
        regime_state = "POSITIVE_GAMMA_RANGE"
    else:
        regime_state = "STRUCTURE_UNTRUSTED"

    confidence = 0.8
    if regime_state == "STRUCTURE_UNTRUSTED":
        confidence = 0.35
    elif regime_state == "PINNED":
        confidence = 0.9

    dealer_state = "LONG_GAMMA" if net_gex > 0 else "SHORT_GAMMA" if net_gex < 0 else "NEUTRAL"
    vanna_state = "UP" if net_vex > 0 else "DOWN" if net_vex < 0 else "NEUTRAL"
    charm_state = "UP" if net_chex > 0 else "DOWN" if net_chex < 0 else "NEUTRAL"

    return {
        "regime_state": regime_state,
        "regime_label": zte_label or fa_regime.upper() or regime_state,
        "dealer_state": dealer_state,
        "pin_risk": round(pin_risk, 2),
        "vanna_state": vanna_state,
        "charm_state": charm_state,
        "confidence_score": round(confidence, 4),
        "net_gex": round(net_gex, 2),
        "net_dex": round(net_dex, 2),
        "net_vex": round(net_vex, 2),
        "net_chex": round(net_chex, 2),
        "flip_price": float(summary.get("gamma_flip", 0) or 0),
        "magnet_price": float((zero_dte.get("pin_risk") or {}).get("magnet_strike", 0) or 0),
    }


def behavior_for_source(source: str) -> tuple[str, str]:
    if source == "put_wall":
        return "DEFEND", "HOLD"
    if source == "call_wall":
        return "REJECT", "FADE"
    if source == "gamma_flip":
        return "FLIP", "WATCH_FOR_FLIP"
    if source in ("hvl", "zero_dte_magnet"):
        return "ATTRACT", "TARGET"
    if source.startswith("pos_gex"):
        return "REJECT", "FADE"
    if source.startswith("neg_gex"):
        return "DEFEND", "HOLD"
    if source == "open_space":
        return "OPEN_SPACE", "ACCELERATION_IF_LOST"
    return "ATTRACT", "TARGET"


def selected_because(source: str) -> str:
    mapping = {
        "put_wall": "FlashAlpha put wall; primary support / defend zone from dealer positioning.",
        "call_wall": "FlashAlpha call wall; primary rejection / fade zone from dealer positioning.",
        "gamma_flip": "FlashAlpha gamma flip; regime fault line where market behavior can change.",
        "hvl": "Highest absolute FlashAlpha GEX strike near price; major attraction / magnet candidate.",
        "zero_dte_magnet": "Zero-DTE magnet from FlashAlpha pin-risk data; same-day attraction node.",
    }
    if source in mapping:
        return mapping[source]
    if source.startswith("pos_gex"):
        return "Secondary positive GEX node near price; supporting resistance / rejection context."
    if source.startswith("neg_gex"):
        return "Secondary negative GEX node near price; supporting defend / hold context."
    return "Provider-derived structural node."


def assign_tier(confidence_score: float) -> str:
    if confidence_score >= 0.78:
        return "T1"
    if confidence_score >= 0.52:
        return "T2"
    return "T3"


def score_level_confidence(*, abs_gex: float, max_abs_gex: float, distance_points: float, max_distance_points: float, flow_strength: float, is_pinned: bool, regime_state: str) -> float:
    gex_norm = abs_gex / max_abs_gex if max_abs_gex > 0 else 0.0
    dist_norm = max(0.0, 1.0 - (abs(distance_points) / max(max_distance_points, 1.0)))
    pinned_bonus = 0.10 if is_pinned else 0.0
    regime_bonus = 0.08 if regime_state in {"NEGATIVE_GAMMA_EXPANSION", "PINNED"} else 0.03
    flow_bonus = min(max(flow_strength, -1.0), 1.0) * 0.12
    score = 0.48 * gex_norm + 0.32 * dist_norm + pinned_bonus + regime_bonus + max(0.0, flow_bonus)
    return max(0.0, min(1.0, score))


def determine_flow_confirmation_state(behavior_state: str, distance_points: float, flow_summary: dict[str, Any]) -> str:
    net_dir = int(flow_summary.get("net_direction", 0) or 0)
    z_score = float(flow_summary.get("z_score", 0.0) or 0.0)
    near = abs(distance_points) <= 120
    if not near:
        return "STRUCTURE_ONLY"
    if abs(z_score) < 0.35 and net_dir == 0:
        return "FLOW_FADED"
    if behavior_state == "DEFEND":
        if net_dir > 0 and z_score >= 0.35:
            return "FLOW_CONFIRMED"
        if net_dir < 0 and abs(z_score) >= 0.75:
            return "FLOW_CONTRADICTED"
    if behavior_state == "REJECT":
        if net_dir < 0 and abs(z_score) >= 0.35:
            return "FLOW_CONFIRMED"
        if net_dir > 0 and z_score >= 0.75:
            return "FLOW_CONTRADICTED"
    if behavior_state in {"ATTRACT", "FLIP", "OPEN_SPACE"} and abs(z_score) >= 1.0:
        return "FLOW_ACCELERATING"
    return "STRUCTURE_ONLY"


def extract_flashalpha_context(fa: FlashAlpha, symbol: str) -> dict[str, Any]:
    # Keep FlashAlpha request count low enough for Growth tier.
    # Summary already carries net_dex/net_vex/net_chex, so we do not need
    # separate vex()/chex() calls on every cycle.
    summary = fa.exposure_summary(symbol)
    zero_dte = fa.zero_dte(symbol)
    levels = fa.exposure_levels(symbol)
    gex = fa.gex(symbol)
    return {
        "summary": summary,
        "zero_dte": zero_dte,
        "levels": levels,
        "gex": gex,
        "vex": {},
        "chex": {},
    }


def degrade_payload(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    degraded = json.loads(json.dumps(payload))
    degraded["generated_at_utc"] = iso(now_utc())
    degraded.setdefault("errors", []).append(reason)
    for asset in degraded.get("assets", []) or []:
        freshness = asset.get("freshness") or {}
        freshness["health_state"] = "degraded"
        freshness["last_successful_refresh_utc"] = freshness.get("last_successful_refresh_utc") or asset.get("as_of_utc") or degraded["generated_at_utc"]
        asset["freshness"] = freshness
        provider_health = asset.get("provider_health") or {}
        provider_health.setdefault("flashalpha", {})
        provider_health.setdefault("massive", {})
        provider_health["flashalpha"]["healthy"] = False
        provider_health["flashalpha"]["state"] = "degraded"
        provider_health["overall"] = "degraded"
        asset["provider_health"] = provider_health
        asset["stale"] = True
    return degraded


def load_last_payload(path: Path) -> dict[str, Any] | None:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


async def fetch_massive_context(api_key: str, underlying: str, min_oi: int) -> dict[str, Any]:
    client = MassiveClient(api_key=api_key, min_oi=min_oi)
    try:
        chain = await client.get_options_chain(underlying)
        nq_price = await client.get_nq_quote()
        flow_engine = FlowEngine()
        for contract in chain.contracts:
            if contract.last is not None and contract.volume:
                flow_engine.update({
                    "price": contract.last,
                    "bid": contract.bid or 0,
                    "ask": contract.ask or 0,
                    "volume": contract.volume,
                    "call_put": contract.call_put,
                })
        flow = flow_engine.compute()
        return {
            "chain": chain,
            "nq_price": nq_price,
            "qqq_price": chain.spot_price,
            "flow": {
                "signed_premium_5m": flow.signed_premium_5m,
                "signed_premium_15m": flow.signed_premium_15m,
                "net_direction": flow.net_direction,
                "z_score": flow.z_score,
            },
        }
    finally:
        await client.close()


def build_semantic_levels(fa_ctx: dict[str, Any], nq_price: float, qqq_price: float, max_distance_points: float, flow_summary: dict[str, Any], regime_summary: dict[str, Any]) -> list[dict[str, Any]]:
    summary = fa_ctx["summary"]
    levels_payload = (fa_ctx["levels"] or {}).get("levels", {})
    gex_payload = fa_ctx["gex"] or {}
    zero_dte = fa_ctx["zero_dte"] or {}

    pinned: list[tuple[str, str, float, float, bool, dict[str, Any]]] = []

    call_wall = float(levels_payload.get("call_wall", 0) or 0)
    put_wall = float(levels_payload.get("put_wall", 0) or 0)
    gamma_flip = float(levels_payload.get("gamma_flip", summary.get("gamma_flip", 0)) or 0)
    zte_magnet = float(levels_payload.get("zero_dte_magnet", 0) or (zero_dte.get("pin_risk") or {}).get("magnet_strike", 0) or 0)

    if put_wall > 0:
        pinned.append(("put_wall", "put_wall", put_wall, -abs(float((gex_payload.get("net_gex", 0) or 0))), True, {}))
    if call_wall > 0:
        pinned.append(("call_wall", "call_wall", call_wall, abs(float((gex_payload.get("net_gex", 0) or 0))), True, {}))
    if gamma_flip > 0:
        pinned.append(("gamma_flip", "gamma_flip", gamma_flip, 0.0, True, {}))
    if zte_magnet > 0:
        pinned.append(("zero_dte_magnet", "zero_dte_magnet", zte_magnet, 0.0, True, {"zero_dte": True}))

    strikes = list(gex_payload.get("strikes", []) or [])
    max_abs_gex = max((abs(float(s.get("net_gex", 0) or 0)) for s in strikes), default=1.0)
    used_qqq_prices = {round(p[2], 6) for p in pinned}

    # derive HVL + secondary nodes from per-strike FlashAlpha GEX
    if strikes:
        hvl = max(strikes, key=lambda s: abs(float(s.get("net_gex", 0) or 0)))
        hvl_strike = float(hvl.get("strike", 0) or 0)
        if hvl_strike > 0 and round(hvl_strike, 6) not in used_qqq_prices:
            pinned.append(("hvl", "hvl", hvl_strike, float(hvl.get("net_gex", 0) or 0), True, {}))
            used_qqq_prices.add(round(hvl_strike, 6))

    levels: list[dict[str, Any]] = []
    rank = 1

    def add_level(level_id: str, source: str, qqq_level: float, gex_value: float, is_pinned: bool, metadata: dict[str, Any]) -> None:
        nonlocal rank
        if qqq_level <= 0 or qqq_price <= 0:
            return
        nq_level = map_qqq_to_nq(qqq_level, qqq_price, nq_price)
        distance_points = nq_level - nq_price
        if max_distance_points > 0 and abs(distance_points) > max_distance_points and source not in {"gamma_flip", "zero_dte_magnet"}:
            return
        behavior_state, action_hint = behavior_for_source(source)
        flow_state = determine_flow_confirmation_state(behavior_state, distance_points, flow_summary)
        flow_strength = 1.0 if flow_state == "FLOW_CONFIRMED" else 0.85 if flow_state == "FLOW_ACCELERATING" else -0.6 if flow_state == "FLOW_CONTRADICTED" else 0.0
        confidence = score_level_confidence(
            abs_gex=abs(gex_value),
            max_abs_gex=max_abs_gex,
            distance_points=distance_points,
            max_distance_points=max_distance_points if max_distance_points > 0 else 350.0,
            flow_strength=flow_strength,
            is_pinned=is_pinned,
            regime_state=regime_summary["regime_state"],
        )
        levels.append({
            "id": level_id,
            "key": level_id,
            "role": level_id,
            "label": level_id.replace("_", " ").upper(),
            "symbol": "NQ",
            "source_underlying": "QQQ",
            "source_price": round(qqq_level, 4),
            "source_strike": round(qqq_level, 4),
            "mapped_price": round(nq_level, 2),
            "price": round(nq_level, 2),
            "gex": round(gex_value, 2),
            "value": round(gex_value, 2),
            "abs_gex_rank": rank,
            "distance_from_spot_source": round(qqq_level - qqq_price, 4),
            "distance_from_futures_spot": round(distance_points, 2),
            "distance_points": round(distance_points, 2),
            "is_pinned": is_pinned,
            "behavior_state": behavior_state,
            "structural_source": source,
            "confidence_score": round(confidence, 4),
            "confidence": round(confidence, 4),
            "tier": assign_tier(confidence),
            "lifecycle_state": "active",
            "action_hint": action_hint,
            "selected_because": selected_because(source),
            "contradicted_because": "Live Massive flow is opposing this structural read." if flow_state == "FLOW_CONTRADICTED" else "",
            "flow_confirmation_state": flow_state,
            "provider_sources": ["flashalpha", "massive"],
            "confluence_group": None,
            "acceleration_context": None,
            "metadata": metadata,
        })
        rank += 1

    for level_id, source, qqq_level, gex_value, is_pinned, metadata in pinned:
        add_level(level_id, source, qqq_level, gex_value, is_pinned, metadata)

    secondary = sorted(
        [s for s in strikes if round(float(s.get("strike", 0) or 0), 6) not in used_qqq_prices],
        key=lambda s: abs(float(s.get("net_gex", 0) or 0)),
        reverse=True,
    )
    for idx, strike in enumerate(secondary[:6], start=1):
        src = "pos_gex_%d" % idx if float(strike.get("net_gex", 0) or 0) >= 0 else "neg_gex_%d" % idx
        add_level(src, src, float(strike.get("strike", 0) or 0), float(strike.get("net_gex", 0) or 0), False, {
            "call_oi": strike.get("call_oi"),
            "put_oi": strike.get("put_oi"),
            "call_volume": strike.get("call_volume"),
            "put_volume": strike.get("put_volume"),
        })

    levels.sort(key=lambda x: x.get("confidence_score", 0.0), reverse=True)
    return levels


def build_provider_health(fa_ok: bool, massive_ok: bool, freshness_age: int) -> dict[str, Any]:
    state = compute_health_state(freshness_age)
    return {
        "flashalpha": {"healthy": fa_ok, "state": "healthy" if fa_ok else "degraded"},
        "massive": {"healthy": massive_ok, "state": "healthy" if massive_ok else "degraded"},
        "overall": state if fa_ok and massive_ok else "degraded",
    }


async def build_payload_async(args: argparse.Namespace, sequence: int) -> dict[str, Any]:
    generated = now_utc()
    compute_start = time.monotonic()
    fa_key = get_flashalpha_key(args.flashalpha_api_key)
    massive_key = get_massive_key(args.massive_api_key)

    fa = FlashAlpha(fa_key)
    fa_ctx = extract_flashalpha_context(fa, args.flashalpha_symbol.upper())
    massive_ctx = await fetch_massive_context(massive_key, args.massive_underlying.upper(), args.min_oi)

    qqq_price = float((fa_ctx["summary"] or {}).get("underlying_price", 0) or 0) or float(massive_ctx["qqq_price"] or 0)
    nq_price = float(massive_ctx["nq_price"] or 0)
    flow_summary = massive_ctx["flow"]
    regime_summary = classify_regime(fa_ctx["summary"], fa_ctx["zero_dte"])
    regime_summary["flow_state"] = "BULLISH" if flow_summary.get("net_direction", 0) > 0 else "BEARISH" if flow_summary.get("net_direction", 0) < 0 else "NEUTRAL"

    levels = build_semantic_levels(
        fa_ctx,
        nq_price=nq_price,
        qqq_price=qqq_price,
        max_distance_points=args.max_futures_distance_points,
        flow_summary=flow_summary,
        regime_summary=regime_summary,
    )
    confluence_zones = [z.to_dict() for z in detect_confluence_zones(levels, nq_price, merge_window_pts=args.confluence_merge_window_pts)]
    for zone in confluence_zones:
        for lvl in levels:
            if lvl["id"] in zone["member_level_ids"]:
                lvl["confluence_group"] = zone["zone_id"]

    lanes = detect_open_space_lanes(levels, nq_price)
    for lane in lanes:
        lane["label"] = "OPEN SPACE"
        lane["confidence_score"] = 0.7 if lane["width_pts"] >= OPEN_SPACE_THRESHOLD_PTS else 0.45
        lane["direction_bias"] = regime_summary["flow_state"]
        lane["trigger_condition"] = "Triggered when adjacent structural level fails with confirming flow."

    compute_duration_ms = int((time.monotonic() - compute_start) * 1000)
    freshness = {
        "payload_age_seconds": 0,
        "chain_snapshot_age_seconds": 0,
        "spot_age_seconds": 0,
        "futures_spot_age_seconds": 0,
        "websocket_age_seconds": -1,
        "compute_duration_ms": compute_duration_ms,
        "last_successful_refresh_utc": iso(generated),
        "health_state": compute_health_state(0),
    }

    asset = {
        "asset_id": f"NQ_{args.flashalpha_symbol.upper()}_V3",
        "futures_root": args.futures_root.upper(),
        "underlying": args.flashalpha_symbol.upper(),
        "underlying_spot": round(qqq_price, 4),
        "futures_symbol": args.futures_symbol,
        "futures_spot": round(nq_price, 4),
        "mapping": {
            "method": "spot_ratio",
            "ratio": round(nq_price / qqq_price, 8) if qqq_price > 0 else 0.0,
            "source": f"{args.flashalpha_symbol.upper()}_to_{args.futures_root.upper()}",
            "source_spot": round(qqq_price, 4),
            "target_spot": round(nq_price, 4),
            "computed_at_utc": iso(generated),
        },
        "freshness": freshness,
        "provider_health": build_provider_health(True, True, 0),
        "flow_summary": {
            **flow_summary,
            "state": regime_summary["flow_state"],
        },
        "regime_summary": regime_summary,
        "levels": levels,
        "levels_list": levels,
        "confluence_zones": confluence_zones,
        "lanes": lanes,
        "chain_error": "",
        "stale": False,
        "age_seconds": 0,
        "as_of_utc": iso(generated),
    }
    return {
        "schema": SCHEMA_V3,
        "service": SERVICE_NAME,
        "service_version": SERVICE_VERSION,
        "generated_at_utc": iso(generated),
        "sequence": sequence,
        "assets": [asset],
        "errors": [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="DEEP6 Options Decision Surface V3")
    ap.add_argument("--flashalpha-api-key", default=None)
    ap.add_argument("--massive-api-key", default=None)
    ap.add_argument("--output", type=Path, default=default_output_path())
    ap.add_argument("--flashalpha-symbol", default="QQQ")
    ap.add_argument("--massive-underlying", default="QQQ")
    ap.add_argument("--futures-root", default="NQ")
    ap.add_argument("--futures-symbol", default="NQ")
    ap.add_argument("--min-oi", type=int, default=100)
    ap.add_argument("--max-futures-distance-points", type=float, default=350.0)
    ap.add_argument("--confluence-merge-window-pts", type=float, default=CONFLUENCE_MERGE_WINDOW_PTS)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--log-level", default="INFO")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
    sequence = 1
    global _LAST_GOOD_PAYLOAD
    _LAST_GOOD_PAYLOAD = load_last_payload(args.output)
    while True:
        try:
            payload = asyncio.run(build_payload_async(args, sequence))
            _LAST_GOOD_PAYLOAD = payload
            write_atomic(args.output, payload)
            asset = payload["assets"][0]
            LOG.info(
                "wrote %s levels=%s regime=%s flow=%s",
                args.output,
                len(asset.get("levels", [])),
                (asset.get("regime_summary") or {}).get("regime_state"),
                (asset.get("flow_summary") or {}).get("state"),
            )
        except RateLimitError as exc:
            LOG.exception("refresh failed: %s", exc)
            if _LAST_GOOD_PAYLOAD is not None:
                write_atomic(args.output, degrade_payload(_LAST_GOOD_PAYLOAD, f"FlashAlpha quota exceeded: {exc}"))
        except Exception as exc:
            LOG.exception("refresh failed: %s", exc)
            if args.once or not args.loop:
                return 2
        if args.once or not args.loop:
            return 0
        sequence += 1
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())

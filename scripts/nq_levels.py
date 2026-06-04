#!/usr/bin/env python
"""
NQ ATLAS — Morning Session Card
Run at 09:35 ET. Prints today's NQ levels, regime, and playbook verdict.
Usage: python scripts/nq_levels.py [NQ_PRICE]
       NQ_PRICE: optional override (uses I:NDX prev if not provided)
"""
from __future__ import annotations
import sys, time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

def main():
    # ─── Config ───────────────────────────────────────────────
    try:
        from nq_atlas.config import Settings
        settings = Settings()
        fa_key = settings.flashalpha_api_key
        massive_key = settings.massive_api_key
    except Exception:
        fa_key = None
        massive_key = None

    nq_override = float(sys.argv[1]) if len(sys.argv) > 1 else None
    
    et = ZoneInfo("America/New_York")
    now_et = datetime.now(timezone.utc).astimezone(et)
    print(f"\n{'='*60}")
    print(f"  NQ ATLAS — Session Card  |  {now_et.strftime('%a %Y-%m-%d %H:%M ET')}")
    print(f"{'='*60}")

    # ─── FlashAlpha data ──────────────────────────────────────
    fa_data = {}
    if fa_key:
        try:
            from flashalpha import FlashAlpha
            fa = FlashAlpha(fa_key)
            summary = fa.exposure_summary("QQQ")
            levels_resp = fa.exposure_levels("QQQ")
            zte = fa.zero_dte("QQQ")
            quote = fa.stock_quote("QQQ")
            fa_data = {
                "summary": summary,
                "levels": levels_resp,
                "zte": zte,
                "quote": quote,
            }
            print(f"  FlashAlpha: connected")
        except Exception as e:
            print(f"  FlashAlpha: {e}")
    else:
        print("  FlashAlpha: no key (set NQ_ATLAS_FLASHALPHA_API_KEY)")

    # ─── QQQ spot + NQ price ──────────────────────────────────
    qqq_spot = fa_data.get("quote", {}).get("lastPrice", 0.0) if fa_data else 0.0
    
    nq_price = nq_override or 0.0
    if not nq_price and massive_key:
        try:
            import httpx, asyncio
            async def get_nq():
                async with httpx.AsyncClient(timeout=8) as h:
                    r = await h.get(
                        "https://api.polygon.io/v2/aggs/ticker/I%3ANDX/prev",
                        params={"apiKey": massive_key}
                    )
                    d = r.json()
                    results = d.get("results", [])
                    return float(results[0]["c"]) if results else 0.0
            nq_price = asyncio.run(get_nq())
        except:
            pass

    ratio = (nq_price / qqq_spot) if qqq_spot > 0 and nq_price > 0 else 41.6

    def to_nq(qqq_lvl):
        if not qqq_lvl or not ratio: return "N/A"
        return f"{qqq_lvl * ratio:,.0f}"

    print(f"\n  QQQ spot:  ${qqq_spot:.2f}")
    print(f"  NQ price:  {nq_price:,.0f}" + (" (prev close)" if not nq_override else " (manual)"))
    print(f"  Ratio:     {ratio:.2f}x\n")

    # ─── FlashAlpha levels ────────────────────────────────────
    if fa_data:
        s = fa_data["summary"]
        lvl = fa_data["levels"].get("levels", {})
        zte = fa_data["zte"]

        regime = s.get("regime", "unknown")
        flip_qqq = s.get("gamma_flip", 0)
        call_wall = lvl.get("call_wall", 0)
        put_wall = lvl.get("put_wall", 0)
        dte_magnet = lvl.get("zero_dte_magnet", 0)
        net_gex = s.get("exposures", {}).get("net_gex", 0)
        interp = s.get("interpretation", {})

        zte_regime = zte.get("regime", {}).get("label", "?")
        zte_flip = zte.get("regime", {}).get("gamma_flip", 0)
        pin_score = zte.get("pin_risk", {}).get("pin_score", 0)
        magnet = zte.get("pin_risk", {}).get("magnet_strike", 0)
        em_rem = zte.get("expected_move", {}).get("remaining_1sd_dollars", 0)
        em_upper = zte.get("expected_move", {}).get("upper_bound", 0)
        em_lower = zte.get("expected_move", {}).get("lower_bound", 0)

        regime_icon = "NEGATIVE" if regime == "negative_gamma" else "POSITIVE"
        dte_icon = "NEG" if zte_regime == "negative_gamma" else "POS"

        print(f"  {'─'*54}")
        print(f"  FULL CHAIN REGIME: {regime_icon} GAMMA")
        print(f"  {'─'*54}")
        print(f"  Gamma flip:  QQQ ${flip_qqq:.2f}  ->  NQ {to_nq(flip_qqq)}")
        print(f"  Call wall:   QQQ ${call_wall}     ->  NQ {to_nq(call_wall)}")
        print(f"  Put wall:    QQQ ${put_wall}      ->  NQ {to_nq(put_wall)}")
        print(f"  0DTE magnet: QQQ ${dte_magnet}    ->  NQ {to_nq(dte_magnet)}")
        print(f"  Net GEX:     ${net_gex/1e6:.0f}M")
        print()
        print(f"  Dealer gamma:  {interp.get('gamma','?')[:60]}")
        print(f"  Dealer vanna:  {interp.get('vanna','?')[:60]}")
        print(f"  Dealer charm:  {interp.get('charm','?')[:60]}")
        print()
        print(f"  {'─'*54}")
        print(f"  0DTE ANALYTICS — {now_et.strftime('%b %d')} expiry")
        print(f"  {'─'*54}")
        print(f"  0DTE regime: {dte_icon} {zte_regime.upper()}")
        print(f"  0DTE flip:   QQQ ${zte_flip:.2f}  ->  NQ {to_nq(zte_flip)}")
        print(f"  Pin risk:    {pin_score}/100 at QQQ ${magnet}  ->  NQ {to_nq(magnet)}")
        print(f"  Exp move:    +/-${em_rem:.2f}  ({to_nq(em_lower)} - {to_nq(em_upper)} NQ)")

        if regime != zte_regime:
            print(f"\n  REGIME DIVERGENCE: Full-chain {regime} vs 0DTE {zte_regime}")
            print(f"  -> Chop near current price until 0DTE gamma decays")

    # ─── Regime verdict ───────────────────────────────────────
    print(f"\n  {'─'*54}")
    print(f"  PLAYBOOK VERDICT")
    print(f"  {'─'*54}")
    if fa_data:
        regime = fa_data["summary"].get("regime", "")
        flip_dist = abs(qqq_spot - flip_qqq) / qqq_spot * 100 if flip_qqq else 99
        if flip_dist < 0.5:
            print(f"  STAND DOWN -- within {flip_dist:.1f}% of gamma flip. Transition zone.")
            print(f"  -> No full-size trades. MNQ only with tight stops.")
        elif regime == "negative_gamma":
            print(f"  TREND MODE -- Negative gamma. Moves amplified.")
            print(f"  -> Add at breakouts. Do not fade walls.")
            print(f"  -> Flip at NQ {to_nq(flip_qqq)} is the regime change level.")
        else:
            print(f"  RANGE MODE -- Positive gamma. Moves suppressed.")
            print(f"  -> Fade at walls. Buy put wall, sell call wall.")
            print(f"  -> Flip at NQ {to_nq(flip_qqq)} = regime change if broken.")

    print(f"\n  {'─'*54}")
    print(f"  APEX RISK -- $50K account | $1,250 max DD | 2-loss stop")
    print(f"  {'─'*54}")
    print(f"  - No trades before 09:35 ET (settling)")
    print(f"  - 2 losses = session stop regardless")
    print(f"  - Near flip (+/-0.5%): MNQ only")
    print(f"  - OPEX Friday PM: halve size")
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()

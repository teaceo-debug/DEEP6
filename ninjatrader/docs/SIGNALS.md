# DEEP6 Footprint — Signal Reference

Every absorption and exhaustion variant, with the Python source it was ported from, the thresholds that control it, and what you see on the chart when it fires.

**Port faithfulness:** all thresholds match `deep6/engines/signal_config.py` defaults. The C# implementation in `src/AbsorptionDetector.cs` and `src/ExhaustionDetector.cs` is a line-by-line translation — no logic changes. See `.planning/phases/16-*/PORT-SPEC.md` for the authoritative spec.

## Signal direction convention

- **+1 bullish** — reversal up from here (buyers winning / sellers exhausted)
- **−1 bearish** — reversal down from here
- **0 neutral** — acceptance / context only (FAT_PRINT)

## Visual glyphs

| Signal family | Bullish (+1) | Bearish (−1) | Neutral (0) |
|---|---|---|---|
| Absorption | cyan triangle-up, below low | magenta triangle-down, above high | — |
| Exhaustion | yellow arrow-up, below low | orange-red arrow-down, above high | slate-gray diamond on bar |

Markers render on the **closed** bar, one candle to the left of the current price.

## Absorption (4 variants + VA bonus)

Ported from `deep6/engines/absorption.py:1-244`. Output type: `AbsorptionSignal`.

### ABS-01 CLASSIC
- **What**: heavy single-sided wick volume at top or bottom, but balanced delta → buyers/sellers absorbed.
- **Trigger**: `wick_pct >= 30%` (× 1.2 if bar range > 1.5 × ATR), `delta_ratio < 0.12`, and bar-wide delta ratio < 0.18.
- **Strength**: `min(wick_pct/60, 1) × (1 − delta_ratio/0.12)`.
- **Direction**: upper wick → bearish (−1); lower wick → bullish (+1).

### ABS-02 PASSIVE
- **What**: >60% of volume sits within the top or bottom 20% of the bar range AND close held away from that extreme.
- **Trigger**: `upper_zone_vol / total_vol >= 0.60` and `close < high − 0.20 × range` (mirror for low).
- **Strength**: zone volume fraction clamped to 1.0.
- **Direction**: upper zone → bearish; lower zone → bullish.

### ABS-03 STOPPING VOLUME
- **What**: bar total volume is 2× vol-EMA AND POC falls in the wick (above body top or below body bottom).
- **Trigger**: `total_vol > 2 × vol_ema` and `POC` outside body.
- **Strength**: `min(total_vol / (2 × 2 × vol_ema), 1)`.
- **Direction**: POC in upper wick → bearish; POC in lower wick → bullish.

### ABS-04 EFFORT VS RESULT
- **What**: high volume, narrow bar range — someone pushed hard but price didn't move.
- **Trigger**: `total_vol > 1.5 × vol_ema` AND `range < 0.30 × ATR`.
- **Strength**: `min(total_vol / (1.5 × 2 × vol_ema), 1)`.
- **Direction**: bar delta < 0 → bullish (+1); else bearish (−1).
- **Why the inversion?** Strong negative delta in a narrow range means sellers pushed but couldn't move price — buyers absorbed, so we fade *up*.

### ABS-07 VA EXTREME BONUS (post-processing)
Applied to every signal after generation:
- **Trigger**: signal price within 2 ticks of VAH or VAL.
- **Effect**: `strength += 0.15` (clamped to 1.0), detail appended with `@VAH` or `@VAL`, `AtVaExtreme = true`.

## Exhaustion (6 variants + delta gate)

Ported from `deep6/engines/exhaustion.py:1-317`. Output type: `ExhaustionSignal`.

### Delta trajectory gate
Applies to EXH-02..06 (not ZERO_PRINT). Cumulative delta must be fading relative to bar direction:

- bullish bar (close > open) → gate passes only if bar delta < 0 (buyers fading)
- bearish bar (close < open) → gate passes only if bar delta > 0 (sellers fading)
- doji → always passes
- |delta|/total_vol < 0.10 → always passes (too small to be a signal)

### EXH-01 ZERO PRINT (gate-exempt)
- **What**: a price tick *inside* the bar body where both bid and ask vol are zero — price skipped over but must revisit.
- **Trigger**: `ask_vol == 0 AND bid_vol == 0` at a tick strictly between body top and body bottom.
- **Strength**: fixed 0.6.
- **Direction**: bar bullish → +1; bearish → −1.
- **Cooldown**: 5 bars. Only one zero print per bar (the first one found).

### EXH-02 EXHAUSTION PRINT
- **What**: single price level at bar top (or bottom) holds an outsized fraction of total volume.
- **Trigger**: `pct >= 35/3 ≈ 11.7%` (× 1.2 if range > 1.5 × ATR) at the highest tick's ask (upper) or lowest tick's bid (lower).
- **Strength**: `min(pct/20, 1)`.
- **Direction**: upper → bearish; lower → bullish.
- **Cooldown**: 5 bars.

### EXH-03 THIN PRINT
- **What**: 3+ levels inside the body where volume < 5% of max-level volume — price moved fast through them.
- **Trigger**: `thin_count >= 3`.
- **Strength**: `min(thin_count/7, 1)`.
- **Direction**: bullish bar → +1; bearish bar → −1 (continuation, then fail).
- **Cooldown**: 5 bars.

### EXH-04 FAT PRINT (neutral)
- **What**: single level with >2× the average per-level volume — an acceptance anchor.
- **Strength**: `min(vol / (2 × 2 × avg), 1)`.
- **Direction**: `0` (not a reversal — a magnet).
- **Cooldown**: 5 bars. Picks the *fattest* level in the bar.

### EXH-05 FADING MOMENTUM
- **What**: bar delta runs opposite to the bar direction, strongly.
- **Trigger**: `|bar_delta| > 0.15 × total_vol`.
- **Strength**: `min(|bar_delta|/total_vol, 1)`.
- **Direction**: bullish bar → **bearish** signal; bearish bar → bullish.
- **Cooldown**: 5 bars.

### EXH-06 BID/ASK FADE (vs prior bar)
- **What**: top-level ask volume collapsed vs prior bar's top-level ask (or bottom-level bid collapsed).
- **Trigger**: `curr_high_ask < 0.60 × prior_high_ask` (or mirror for lows).
- **Strength**: `1 − curr/prior`.
- **Direction**: ask fade at top → bearish; bid fade at bottom → bullish.
- **Cooldown**: 5 bars. Needs a prior bar; does not fire on bar 1 of session.

## Session boundaries

At the start of each new trading day, the detector resets its cooldown state so a full set of signals can fire again. The indicator detects the boundary by date change in `Bars.GetTime(prevIdx).Date`. This is a simplification — DEEP6 Python uses an explicit RTH gate at 9:30 ET. For NQ futures the practical difference is small (sessions span midnight UTC, not midnight local), so the date-change heuristic works for most chart types. If you run an ETH session that spans two dates, cooldowns will reset mid-session on date rollover; this is acceptable for a visual tool.

## Known divergences from the Python engine

These are documented up front so you know what might look different:

1. **ATR**: indicator uses a simple 20-bar rolling average of `(high − low)`; Python uses Wilder's ATR(20). Numerically very close; does not affect signal direction, only the 1.2× wick-min multiplier.
2. **Volume EMA**: indicator uses per-bar total-volume EMA with α = 2/21; Python uses the same formula but seeded from a pre-session warmup.
3. **GEX overlay**: indicator computes gamma-flip / call-wall / put-wall client-side from the massive.com options chain; Python consumes pre-classified levels from (a different provider in current config). GEX mapping QQQ → NQ uses spot-ratio scalar; this is visual-only.
4. **Aggressor classification**: indicator uses `price >= bestAsk` / `price <= bestBid` on NT8's Last tick. Python has a richer aggressor heuristic from Rithmic raw fields (DATA-02 verification). Expect ~1-2% classification divergence at fast moves.
5. **Session reset**: date-change heuristic vs explicit RTH gate. See above.

If you see a signal fire in one system but not the other, check the divergences above before filing a bug.

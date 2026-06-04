# V8 Parity Report: Python ↔ C# Signal Detection

**Date:** 2026-05-24
**Files compared:**
- Python v1: `deep6/engines/absorption.py`, `deep6/engines/exhaustion.py`, `deep6/engines/signal_config.py`
- Python v2: `deep6v2/signals/absorption.py`, `deep6v2/signals/exhaustion.py`
- C#: `ninjatrader/Custom/AddOns/DEEP6/Detectors/Absorption/AbsorptionDetector.cs`
- C#: `ninjatrader/Custom/AddOns/DEEP6/Detectors/Exhaustion/ExhaustionDetector.cs`
- PORT-SPEC: `.planning/phases/16-.../PORT-SPEC.md` (authoritative reference)

---

## VERDICT SUMMARY

| Variant | Signal | Python v1 ↔ C# | Python v2 ↔ C# | Notes |
|---------|--------|----------------|----------------|-------|
| ABS_01 | Classic | **MATCH** | MISMATCH | v2 uses different wick definition + no ATR scaling |
| ABS_02 | Passive | **MATCH** | MISMATCH | v2 uses vol_ema threshold, not fraction of total |
| ABS_03 | Stopping Vol | **MATCH** | MISMATCH | v2 uses 25% range zone, not body-based POC check |
| ABS_04 | Effort/Result | **MATCH** | MISMATCH | v2 direction uses price, not delta |
| EXH_01 | Zero Print | **MATCH** | MISMATCH | v2 checks extremes not body; no cooldown |
| EXH_02 | Exhaustion Print | **MATCH** | MISMATCH | v2 uses avg_row_vol threshold, not wick_min % |
| EXH_03 | Thin Print | **MATCH** | MISMATCH | v2 checks extremes not body; different strength |
| EXH_04 | Fat Print | **MATCH** | MISMATCH | v2 adds delta-neutrality check; directional not neutral |
| EXH_05 | Fading Momentum | **MATCH** | MISMATCH | v2 uses multi-bar divergence, not single-bar |
| EXH_06 | Bid/Ask Fade | **MATCH** | MISMATCH | v2 different price lookup + 0.75x strength multiplier |

### Declaration

**Python v1 (`deep6/engines/`) is authoritative for DEEP6FootprintV7.cs / V8.**

All 10 signal variants in C# match Python v1 exactly: same thresholds, same logic flow, same strength formulas, same direction conventions. The C# files explicitly cite Python v1 line numbers. PORT-SPEC.md cites Python v1 as the source.

**Python v2 (`deep6v2/signals/`) does NOT map to V7/V8.** It is a fundamentally different implementation with different algorithms, thresholds, config structures, and missing features (no ABS-07, no cooldown, no delta gate).

---

## NUMERICAL THRESHOLD COMPARISON

### Absorption Config

| Parameter | Python v1 (`signal_config.py`) | C# (`AbsorptionConfig`) | PORT-SPEC | Match? |
|-----------|-------------------------------|------------------------|-----------|--------|
| absorb_wick_min / AbsorbWickMin | 30.0 | 30.0 | 30.0 | ✅ |
| absorb_delta_max / AbsorbDeltaMax | 0.12 | 0.12 | 0.12 | ✅ |
| passive_extreme_pct / PassiveExtremePct | 0.20 | 0.20 | 0.20 | ✅ |
| passive_vol_pct / PassiveVolPct | 0.60 | 0.60 | 0.60 | ✅ |
| stop_vol_mult / StopVolMult | 2.0 | 2.0 | 2.0 | ✅ |
| evr_vol_mult / EvrVolMult | 1.5 | 1.5 | 1.5 | ✅ |
| evr_range_cap / EvrRangeCap | 0.30 | 0.30 | 0.30 | ✅ |
| va_extreme_ticks / VaExtremeTicks | 2 | 2.0 | 2.0 | ✅ |
| va_extreme_strength_bonus / VaExtremeStrengthBonus | 0.15 | 0.15 | 0.15 | ✅ |

### Exhaustion Config

| Parameter | Python v1 (`signal_config.py`) | C# (`ExhaustionConfig`) | PORT-SPEC | Match? |
|-----------|-------------------------------|------------------------|-----------|--------|
| thin_pct / ThinPct | 0.05 | 0.05 | 0.05 | ✅ |
| fat_mult / FatMult | 2.0 | 2.0 | 2.0 | ✅ |
| exhaust_wick_min / ExhaustWickMin | 35.0 | 35.0 | 35.0 | ✅ |
| fade_threshold / FadeThreshold | 0.60 | 0.60 | 0.60 | ✅ |
| cooldown_bars / CooldownBars | 5 | 5 | 5 | ✅ |
| delta_gate_enabled / DeltaGateEnabled | True | true | true | ✅ |
| delta_gate_min_ratio / DeltaGateMinRatio | 0.10 | 0.10 | 0.10 | ✅ |

### Derived Constants (hardcoded in both)

| Constant | Python v1 | C# | PORT-SPEC | Match? |
|----------|-----------|-----|-----------|--------|
| ATR scaling trigger | bar_range > atr * 1.5 | BarRange > atr * 1.5 | same | ✅ |
| ATR scaling factor | 1.2 | 1.2 | 1.2 | ✅ |
| ABS-01 strength denom | 60.0 | 60.0 | 60.0 | ✅ |
| ABS-01 bar_delta_ratio cap | delta_max * 1.5 | deltaMax * 1.5 | delta_max * 1.5 | ✅ |
| EXH-01 fixed strength | 0.6 | 0.6 | — | ✅ |
| EXH-02 threshold divisor | /3 (exhaust_wick_min/3) | /3.0 | /3 | ✅ |
| EXH-02 strength denom | 20.0 | 20.0 | 20 | ✅ |
| EXH-03 min thin count | 3 | 3 | 3 | ✅ |
| EXH-03 strength denom | 7.0 | 7.0 | 7 | ✅ |
| EXH-05 momentum threshold | 0.15 | 0.15 | 0.15 | ✅ |
| Tick size (NQ default) | 0.25 (hardcoded) | 0.25 (fallback) | — | ✅ |

---

## DETAILED VARIANT ANALYSIS

### ABS-01: Classic Absorption

**Algorithm:** Wick vol >= threshold AND wick delta ratio < max AND bar delta ratio < max * 1.5

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Wick definition | px > body_top (upper), px < body_bot (lower) | px > bodyTop, px < bodyBot | ✅ Identical |
| ATR-adaptive wick_min | `* 1.2 if bar_range > atr * 1.5` | `* (BarRange > atr * 1.5 ? 1.2 : 1.0)` | ✅ Identical |
| Wick delta ratio | `abs(wick_delta) / wick_vol` | `Math.Abs(wickDelta) / (double)wickVol` | ✅ Identical |
| Bar delta ratio gate | `bar_delta_ratio < absorb_delta_max * 1.5` | `barDeltaRatio < deltaMax * 1.5` | ✅ Identical |
| Strength formula | `min(wick_pct/60, 1) * (1 - delta_ratio/delta_max)` | `Min(wickPct/60.0, 1.0) * (1.0 - deltaRatio/deltaMax)` | ✅ Identical |
| Direction | upper=-1, lower=+1 | upper=-1, lower=+1 | ✅ Identical |

**v2 differences:** Uses 20%-from-extremes zones (not body-based), checks whole-bar delta neutrality (not per-wick ratio), no ATR scaling, simpler strength formula. **Structurally incompatible.**

### ABS-02: Passive Absorption

**Algorithm:** Volume in top/bottom 20% of range >= 60% total AND close rejects the zone.

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Zone definition | `bar.high - bar_range * 0.20` | `bar.High - extremeRange` (same) | ✅ Identical |
| Volume threshold | `top_zone_vol / total >= 0.60` | `upperZoneVol / (double)bar.TotalVol >= PassiveVolPct` | ✅ Identical |
| Close rejection | `bar.close < bar.high - extreme_range` | `bar.Close < bar.High - extremeRange` | ✅ Identical |
| Strength | `min(zone_vol / total, 1.0)` | `Math.Min(upperZoneVol / (double)bar.TotalVol, 1.0)` | ✅ Identical |

**v2 differences:** Uses vol_ema * 1.5 as absolute threshold; 15% zone; 30% close-away-from; completely different approach.

### ABS-03: Stopping Volume

**Algorithm:** Total vol > vol_ema * 2.0 AND POC is outside candle body.

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Volume gate | `total_vol > vol_ema * stop_vol_mult` | `TotalVol > volEma * StopVolMult` | ✅ Identical |
| POC location | `poc_price > body_top` or `< body_bot` | `PocPrice > bodyTop` or `< bodyBot` | ✅ Identical |
| Strength | `min(total_vol / (vol_ema * mult * 2), 1.0)` | `Min(TotalVol / (volEma * StopVolMult * 2.0), 1.0)` | ✅ Identical |

**v2 differences:** POC check uses 25%-from-low/high, not body-based. Strength uses poc_volume ratio.

### ABS-04: Effort vs Result

**Algorithm:** High volume + narrow range (< 30% ATR) → direction from delta sign.

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Volume gate | `total_vol > vol_ema * 1.5` | `TotalVol > volEma * EvrVolMult` | ✅ Identical |
| Range cap | `bar_range < atr * 0.30` | `BarRange < atr * EvrRangeCap` | ✅ Identical |
| Direction | `+1 if bar_delta < 0 else -1` | `BarDelta < 0 ? +1 : -1` | ✅ Identical |
| Strength | `min(total_vol / (vol_ema * mult * 2), 1.0)` | `Min(TotalVol / (volEma * EvrVolMult * 2.0), 1.0)` | ✅ Identical |

**v2 differences:** Direction based on close vs midpoint, not delta. Strength formula lacks *2 denominator.

### ABS-07: VA Extreme Bonus

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Proximity | `va_extreme_ticks * 0.25 = 0.50 pts` | `VaExtremeTicks * tickSz` (default 0.50) | ✅ Identical |
| Strength bump | `+0.15, capped at 1.0` | `+0.15, capped at 1.0` | ✅ Identical |
| Applies to | All ABS signals post-hoc | All results post-hoc | ✅ Identical |
| C# emits ABS-07 diagnostic result | — | Yes (FlagBit=0) | N/A (C# bonus) |

**v2:** Not implemented at all.

### EXH-01: Zero Print

**Algorithm:** Price level within body with 0 volume on both sides.

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Gate exempt | Yes — before delta gate | Yes — before delta gate | ✅ Identical |
| Zero check | `ask_vol == 0 and bid_vol == 0` | `AskVol == 0 && BidVol == 0` | ✅ Identical |
| Location | `body_bot < px < body_top` | `bodyBot < px && px < bodyTop` | ✅ Identical |
| Direction | `+1 if close > open else -1` | `Close > Open ? +1 : -1` | ✅ Identical |
| Strength | 0.6 fixed | 0.6 fixed | ✅ Identical |
| One per bar | break after first | break after first | ✅ Identical |
| Cooldown | 5 bars | 5 bars | ✅ Identical |

**v2 differences:** Checks extremes (top 30%, bottom 30%) not body interior; uses configurable zero threshold; direction by location not close-vs-open; no cooldown; no delta gate.

### EXH-02: Exhaustion Print

**Algorithm:** Heavy single-side vol at bar extreme level, threshold = exhaust_wick_min / 3.

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| ATR scaling | `eff_min = exhaust_wick_min * (1.2 if range > atr * 1.5 else 1.0)` | Same formula | ✅ Identical |
| High check | `high_level.ask_vol / total * 100 >= eff_min / 3` | `(double)hiLv.AskVol / TotalVol * 100 >= effMin / 3.0` | ✅ Identical |
| Low check | `low_level.bid_vol / total * 100 >= exhaust_wick_min / 3` | `(double)loLv.BidVol / TotalVol * 100 >= ExhaustWickMin / 3.0` | ✅ Identical |
| Strength | `min(pct / 20.0, 1.0)` | `Min(pct / 20.0, 1.0)` | ✅ Identical |

**Note:** Python v1 applies ATR scaling to the low check threshold only on eff_min, but doesn't re-check ATR for the low — actually it uses `cfg.exhaust_wick_min / 3` for the low check. The C# code has a subtlety: it re-checks cooldown before low and uses `cfg.ExhaustWickMin / 3.0` (without ATR scaling on low). Examining Python v1 more carefully: `eff_min` is computed once for the high check, but the low check uses `cfg.exhaust_wick_min / 3` (raw, no ATR scaling). The C# low check also uses raw `cfg.ExhaustWickMin / 3.0`. **Both behave identically.** ✅

### EXH-03: Thin Print

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Thin threshold | `vol < max_level_vol * 0.05` | `v < maxLevelVol * ThinPct` | ✅ Identical |
| Location filter | `body_bot <= px <= body_top` | `px < bodyBot or px > bodyTop → continue` | ✅ Identical |
| Min count | 3 | 3 | ✅ Identical |
| Strength | `min(thin_count / 7.0, 1.0)` | `Min(thinCount / 7.0, 1.0)` | ✅ Identical |
| Direction | `+1 if close > open else -1` | `Close > Open ? +1 : -1` | ✅ Identical |

### EXH-04: Fat Print

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Threshold | `vol > avg_level_vol * 2.0` | `v > avgLevelVol * FatMult` | ✅ Identical |
| Direction | 0 (neutral) | 0 | ✅ Identical |
| Strength | `min(vol / (avg * 2.0 * 2), 1.0)` | `Min(v / (avgLevelVol * FatMult * 2.0), 1.0)` | ✅ Identical |
| One per bar | break after first | break after first | ✅ Identical |

### EXH-05: Fading Momentum

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Prerequisite | `bar_range > 0` | `bar.BarRange > 0` | ✅ Identical |
| Trigger | `abs(bar_delta) > total_vol * 0.15` | `Math.Abs(BarDelta) > TotalVol * 0.15` | ✅ Identical |
| Direction | `-1 if bullish else +1` | `barBullish ? -1 : +1` | ✅ Identical |
| Strength | `min(abs(bar_delta) / total_vol, 1.0)` | `Min(Abs(BarDelta) / TotalVol, 1.0)` | ✅ Identical |

**v2 differences:** Multi-bar (3-bar) price/delta divergence instead of single-bar check. Fundamentally different detection approach.

### EXH-06: Bid/Ask Fade

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Threshold | `< prior * 0.60` | `< prior * FadeThreshold` | ✅ Identical |
| High comparison | curr high tick ask vs prior high tick ask | Same | ✅ Identical |
| Low comparison | curr low tick bid vs prior low tick bid | Same | ✅ Identical |
| Strength | `1.0 - (curr / prior)` | `1.0 - (curr / prior)` | ✅ Identical |

### Delta Gate (EXH-07)

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Enabled | True | true | ✅ Identical |
| Min ratio | 0.10 | 0.10 | ✅ Identical |
| Bullish bar gate | `bar_delta < 0` | `BarDelta < 0` | ✅ Identical |
| Bearish bar gate | `bar_delta > 0` | `BarDelta > 0` | ✅ Identical |
| Doji | allow | allow | ✅ Identical |
| Position | After EXH-01, before EXH-02..06 | After EXH-01, before EXH-02..06 | ✅ Identical |

**v2:** No delta gate. Uses crude `abs(delta) > total_vol * 0.5` filter for ALL signals.

### Cooldown System

| Aspect | Python v1 | C# | Parity |
|--------|-----------|-----|--------|
| Cooldown bars | 5 | 5 | ✅ Identical |
| Per-type tracking | Yes | Yes | ✅ Identical |
| Reset at session | `reset_cooldowns()` | `Reset()` | ✅ Identical |
| EXH-01 exempt from gate | Yes (separate) | Yes (separate) | ✅ Identical |

**v2:** No cooldown mechanism at all.

---

## OPTIMIZATION TRANSFER RISK

**Risk: LOW.** Since Python v1 matches C# exactly on all thresholds and logic, parameter optimization results from `deep6/backtest/` will transfer accurately to the C# detectors. The config objects are structurally identical:

- `AbsorptionConfig` (Python v1 frozen dataclass) ↔ `AbsorptionConfig` (C# sealed class): all 9 fields match
- `ExhaustionConfig` (Python v1 frozen dataclass) ↔ `ExhaustionConfig` (C# sealed class): all 7 fields match

Any optimized parameter set can be directly copy-pasted from Python v1 sweep results to C# config defaults.

**WARNING:** Do NOT use Python v2 (`deep6v2/signals/`) for parameter optimization targeting V7/V8 C#. The algorithms are incompatible — optimized v2 parameters would produce meaningfully different signals in C#.

---

## PYTHON v2 DISCREPANCY CATALOG

For completeness, the fundamental v2 differences that make it incompatible:

| Feature | Python v1 (authoritative) | Python v2 (incompatible) |
|---------|--------------------------|--------------------------|
| ABS-01 wick zones | Body-based (px > body_top) | Extreme-based (20% from high/low) |
| ABS-01 delta check | Per-wick ratio < 0.12 | Whole-bar neutrality threshold |
| ABS-02 threshold | Fraction of total vol (60%) | Absolute vs vol_ema (1.5x) |
| ABS-03 POC check | POC outside body | POC in bottom/top 25% of range |
| ABS-04 direction | Delta-based | Price-based (close vs midpoint) |
| ABS-07 VA bonus | Implemented | Missing entirely |
| EXH-01 location | Within body interior | At extremes (top/bottom 30%) |
| EXH-02 threshold | exhaust_wick_min / 3 (ATR-scaled) | avg_row_vol * 1.5 + one-sidedness check |
| EXH-03 detection | Count thin levels in body ≥ 3 | Single thin level at extreme |
| EXH-04 direction | Neutral (0) | Directional (bull/bear) |
| EXH-05 approach | Single-bar delta vs price | Multi-bar (3) price/delta divergence |
| EXH-06 comparison | Same tick position | Overlapping price lookup + 0.75x multiplier |
| Delta gate | Targeted EXH-07 (per PORT-SPEC) | Crude 50% delta filter on all signals |
| Cooldown | Per-type, 5 bars | None |
| Config source | `signal_config.py` (frozen dataclass) | `deep6v2/config/signals.py` (different structure) |

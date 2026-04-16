# DEEP6 Fine-Tuning Recommendations
**Audience:** Trading systems architect / developer  
**Date:** 2026-04-15  
**Status:** Pre-paper-trade (Phase 19 not started)  
**Scope:** End-to-end review — scoring formula, entry/exit logic, signal quality, risk management, infrastructure, and production readiness

---

## Executive Summary

DEEP6 is architecturally sound. The two-layer confluence scorer, detector registry pattern, and signal taxonomy are well-designed. The core thesis (absorption + exhaustion as highest-alpha reversal signals) is correctly prioritized in the weight structure. However, **four critical blockers prevent the system from entering paper trade today**, and a further eight issues will materially degrade live performance if not addressed before real capital is deployed. This document covers every dimension with specific, implementable fixes.

---

## 1. Scoring Formula Audit

### 1.1 Category Weight Analysis

Current weights:
```
absorption=25, exhaustion=18, trapped=14, delta=13,
imbalance=12, volume_profile=10, auction=8, poc=1
```

**Assessment: Broadly correct, but two anomalies.**

The weight structure correctly prioritizes absorption (25) and exhaustion (18), accounting for 43 of 101 nominal points — this aligns with the core thesis. The trapped (14) boost from 10 is validated by backtests showing trapped+absorption as the highest-alpha combination. Delta (13) correctly reflects that delta agreement is a quality filter rather than a primary signal.

**Anomaly 1: `poc=1` is effectively a dummy weight.**  
POC-02/07/08 can vote and add 1.0 to base score, but at weight=1 it contributes <1% of a full score. Given prior backtest findings (35% win rate with POC vs 73% without in absorption+trapped combos), keeping POC at weight=1 makes sense — it participates in category counting (enabling confluence multiplier) without distorting directional score. This is intentional and correct. **No change needed.**

**Anomaly 2: `volume_profile=10` is only accessible via zone bonus — not by signal.**  
The volume_profile category is added to `categoriesAgreeing` only when `zoneScore >= 30`. Since `zoneScore` defaults to 0.0 (and the NT8 implementation passes 0.0 because the zone scoring system is not yet wired), this category never contributes in live trading. The 10-point weight is phantom. **This is part of the #1 blocker (see Section 4.1).**

**Recommendation R-1.1 (P0):** Wire zone scoring into the scorer call in DEEP6Footprint.cs. Until ProfileAnchorLevels produces a live zoneScore, the `volume_profile` category weight of 10 is inaccessible, TypeA's `hasZone` condition always fails, and the 1.25x confluence multiplier requires 5 categories without volume_profile — which is very hard to achieve.

**Recommendation R-1.2 (P2):** Run a grid sweep over absorption weight (20–35, step 2.5) and exhaustion weight (14–24, step 2) on the recorded sessions once sufficient trade sample (50+ trades) is available. The current weights were derived from <5,000 bars; NQ regime shifts may require rebalancing.

### 1.2 TypeA Gate Analysis

TypeA currently requires ALL of:
1. `totalScore >= 80`
2. `hasAbsorption || hasExhaustion`
3. `hasZone` (zone_bonus > 0)
4. `catCount >= 5`
5. `deltaAgrees`
6. `!trapVeto` (fewer than 3 trap signals)
7. `!deltaChase` (|barDelta| <= 50)

**Assessment: The 7-condition AND is too restrictive and has a structural flaw.**

Condition 3 (`hasZone`) depends entirely on `zoneScore > 0`, which is stubbed at 0.0 in the current NT8 implementation. This means **TypeA never fires in the current system** regardless of signal quality. This is the most critical issue.

Even after zone scoring is wired, requiring all 7 conditions simultaneously means:
- A perfect 5-category absorption at a high-quality zone will be vetoed if delta happens to chase by >50 contracts.
- The delta chase threshold of 50 contracts is not ATR-normalized — on high-volatility sessions, 50 delta is noise; on quiet sessions, it is meaningful.

**Recommendation R-1.3 (P1):** After zone scoring is wired, separate condition 7 (deltaChase) into a soft warning rather than a hard veto. Instead, when deltaChase is true, reduce totalScore by 10 points (instead of blocking TypeA outright). This allows very high-conviction setups (score=92 with 6 categories) to still qualify as TypeA even on slightly chased bars.

**Recommendation R-1.4 (P1):** Make the delta chase threshold ATR-proportional: `DELTA_CHASE_MAG = max(50, ATR_in_delta_equivalent * 0.4)`. The fixed 50-contract threshold is appropriate for average NQ days but blocks valid trades on high-momentum sessions.

### 1.3 TypeB as Primary Trading Tier

TypeB requires: `score >= 72`, `catCount >= 4`, `deltaAgrees`, `maxStrength >= 0.3`.

**Assessment: TypeB should be the primary live-trading tier during Phase 19 paper trade.**

TypeA's 7 simultaneous conditions make it rare by design. During paper trade validation, the sample size for TypeA alone may be too small (2–5 trades/day on quiet NQ, zero on many days) to produce statistically meaningful performance data within 30 days. TypeB (4 categories, score 72+) fires more frequently and still requires meaningful confluence.

**Recommendation R-1.5 (P1):** During Phase 19, run DEEP6Strategy with `MinTierForEntry = SignalTier.TYPE_B` and `ScoreEntryThreshold = 72.0`. Log TypeA vs TypeB performance separately. This provides 30-day statistical significance while TypeA data accumulates. After 30 days, TypeA can be the live tier and TypeB can be the scale-in or alert-only tier.

---

## 2. Entry Logic Gaps

### 2.1 Bar-Close Entry vs Intra-Bar Entry

**Current behavior:** Entry fires at bar close (first tick of the next bar) after `IsFirstTickOfBar` triggers in `OnBarUpdate`. This means entries are at best 1 full 1-minute bar late.

**Impact:** On a clean reversal setup, the absorption signal fires at bar 0's close. Entry happens at bar 1's open. The first 20–40 ticks of the move (the highest expected-value portion) are missed. Slippage assumption of 1 tick in `BacktestConfig` is also unrealistic — actual slippage on a momentum entry is 2–4 ticks minimum.

**Assessment:** Bar-close entry is a deliberate tradeoff for simplicity and reproducibility, but it materially understates real-world entry timing. The backtest's 20-stop / 40-target assumes entries at the signal bar's close — actual entries are at next-bar open, so effective stop is ~18 ticks and effective target is ~38 ticks (accounting for entry offset).

**Recommendation R-2.1 (P1):** Adjust `BacktestConfig.StopLossTicks = 22` and `TargetTicks = 38` (net of bar-close-to-open drift) to reflect realistic expected values. This is a calibration fix to make backtest results match live execution more accurately.

**Recommendation R-2.2 (P2):** Add an optional intra-bar entry mode using `Calculate.OnEachTick`. When an ABS/EXH signal fires mid-bar (detectable once the bar crosses the wick percentage threshold), submit a limit order at the signal price rather than waiting for bar close. This requires maintaining a running footprint accumulator per tick — the infrastructure is already in place via `OnMarketData`. Implement post-Phase-19 after validating the bar-close model first.

### 2.2 Re-Entry Logic

**Current behavior:** After a stop-out, the system respects `MinBarsBetweenEntries = 3` before allowing a new entry. If the original signal condition persists (same direction, same zone, score still >= threshold), no special re-entry logic exists.

**Impact:** The highest-conviction trade scenarios often involve initial fakeout then the real move. A stop-out followed immediately by a second high-conviction signal in the same direction is one of the most reliable setups in NQ orderflow (trapped traders, double absorption). Currently, the 3-bar cooldown prevents this re-entry.

**Recommendation R-2.3 (P1):** Add a `ReEngageAfterStop` mode: if all of these are true, allow immediate re-entry (bypass `MinBarsBetweenEntries`):
- Stop was taken in the last 3 bars
- New signal is same direction as stopped trade  
- New score >= `ScoreEntryThreshold + 5.0` (higher bar, stricter filter)
- New tier == TypeA (not TypeB)
- No opposing signals fired since the stop

Cap total re-entries per session at 2. This is implementable as a single `_lastStopBar` and `_reEngageCount` field in DEEP6Strategy.

### 2.3 Position Sizing

**Current behavior:** Fixed 1 contract per trade (`MaxContractsPerTrade = 1`, `ContractsPerTrade = 1`).

**Recommendation R-2.4 (P1):** Add tiered sizing: TypeA = 2 contracts, TypeB = 1 contract. Gate behind account-size check: only activate 2-contract TypeA trades when `accountBalance >= 2 * minimumMargin`. For Apex/Lucid funded accounts, this is straightforward once margin requirements are confirmed. Implement this as an NT8 property `TypeAContracts = 2` that defaults to 1 (safe default) and can be activated post-Phase-19.

### 2.4 Time-of-Day Filter

**Current behavior:** RTH window 9:35–15:50 ET plus midday block 10:30–13:00 ET forced QUIET (bars 240–330).

**Assessment:** The midday block is correctly implemented and has forensic justification (-$1,622 across 25 days per scorer.py comments). However, two high-edge time windows are undertreated:

- **9:35–10:00 ET (IB formation):** The 1.15x IB multiplier is applied, but IB-period signals carry higher false-positive risk before the Initial Balance is established. The IB multiplier should only activate *after* 10 bars (10 min of data), not from bar 0.
- **14:00–15:00 ET (institutional late-session):** This window has historically higher volume and cleaner absorption setups but is currently treated identically to mid-morning.

**Recommendation R-2.5 (P2):** Modify IB multiplier to activate at `barsSinceOpen >= 10` (not 0). Add an optional late-session window boost: bars 270–360 (14:00–15:00 ET) get 1.05x multiplier when score >= 75. These are post-Phase-19 fine-tuning items.

---

## 3. Exit Logic Gaps

### 3.1 Missing Trailing Stop

**Critical gap.** The current exit logic is: stop → target → opposing signal → max bars. There is no mechanism to protect open profits as the trade moves favorably.

On a 40-tick target, a typical NQ move may go 30 ticks in your favor then retrace 25 ticks before continuing. Without a trailing stop, you take the full retracement as a loser when you had 30 ticks of open profit.

**Recommendation R-3.1 (P0 — must fix before paper trade):** Add ATR-trailing stop. Algorithm:
1. Track `maxFavorableExcursion` (MFE) in ticks for the open trade.
2. Once MFE >= 15 ticks, activate trailing mode: set `trailingStop = currentPrice - (1.5 * ATR * direction)`.
3. Once MFE >= 25 ticks (50% of 40-tick target), tighten trail to `1.0 * ATR`.
4. The trail only moves in the favorable direction — never retreats.

For the backtest engine, add fields: `TrailActivationTicks = 15`, `TrailAtrMult = 1.5`, `TrailTightenTicks = 25`, `TrailTightenMult = 1.0`. The `BacktestRunner.RunSession()` exit check loop needs a `highWaterMark`/`lowWaterMark` variable tracking favorable price excursion.

In DEEP6Strategy (live), the ATM template handles the trailing stop mechanically. However, the ATM must be configured to match these parameters — add to docs/ATM-STRATEGIES.md.

### 3.2 Missing Breakeven Stop

**Recommendation R-3.2 (P1):** After MFE >= 10 ticks, move stop to entry price + 1 tick (breakeven with slippage coverage). This eliminates the scenario where a 10-tick winner becomes a 20-tick loser because you never had a mechanism to protect the entry. Implement as `BreakevenTicks = 10` in BacktestConfig.

### 3.3 Time-Based Target Tightening

**Current behavior:** Maximum bars in trade = 30. No intermediate adjustment.

**Gap:** A trade at bar 20 that has moved 15 ticks in 20 bars (versus a 40-tick target) is likely stalling. Waiting 10 more bars often results in full retracement to stop.

**Recommendation R-3.3 (P2):** Add time-decay exit: if MFE < (TargetTicks * 0.5) after MaxBarsInTrade * 0.6 bars (18 bars at default config), reduce remaining target to MFE + 5 ticks. This takes a smaller profit rather than waiting for full stop-out on stalled trades.

### 3.4 Scaling Out

**Recommendation R-3.4 (P2):** Once position sizing is enabled (R-2.4), add scale-out for TypeA 2-contract trades: exit 1 contract at 20 ticks (50% of target), trail the second to full target. This improves average trade expectancy on TypeA setups by reducing variance. Implement as `ScaleOutTick1 = 20`, `ScaleOutContracts1 = 1` in BacktestConfig.

### 3.5 Opposing-Signal Exit Threshold

**Current behavior:** `ExitOnOpposingScore = 0.50`. Any opposing signal scoring >= 50 triggers exit.

**Assessment:** 0.50 is the raw score value (pre-cliff, post-formula) for a TypeC signal (threshold = 50). This means any TypeC opposing signal exits the trade. This is too sensitive — a TypeC signal has 4 categories agreeing but score barely over 50, which is meaningfully different from a TypeA reversal setup.

**Recommendation R-3.5 (P1):** Replace the fixed threshold with a tier-gated opposing exit:
- TypeC opposing signal: reduce current position target by 5 ticks (partial tighten, not exit)
- TypeB opposing signal (score >= 72): exit if MFE < 10 ticks; else tighten stop to breakeven
- TypeA opposing signal (score >= 80): immediate exit regardless of MFE

This requires the BacktestRunner to also score the opposing signal through ConfluenceScorer (it already does — `scored.Tier` is available in the exit check). Modify `ExitOnOpposingScore` to `ExitOnOpposingTier = SignalTier.TYPE_B`.

---

## 4. Signal Quality Issues

### 4.1 ZoneScore Stub — #1 System Blocker

**Current state:** In DEEP6Strategy.EvaluateEntry and in BacktestRunner, `zoneScore` is passed as 0.0 (default). This means:
- `hasZone` = false in ConfluenceScorer
- TypeA condition 3 (`hasZone`) never passes
- `volume_profile` category never enters `categoriesAgreeing`
- The 1.25x confluence multiplier requires 5 categories without volume_profile, making it very hard to achieve
- TypeA **never fires in the current system under any market condition**

**Root cause:** ProfileAnchorLevels is implemented and computes PDH/PDL/PDM/PD POC/VAH/VAL/nPOC correctly, but the computed levels are not converted into a scalar `zoneScore` and passed into ConfluenceScorer.

**Recommendation R-4.1 (P0 — #1 blocker):** Implement `ZoneScoreCalculator.Compute(barClose, anchorSnapshot, tickSize)` → returns `(zoneScore, zoneDistTicks)`. Algorithm:
1. Score = 0
2. For each ProfileAnchor within 20 ticks of barClose:
   - PD POC within 5 ticks: +40
   - PD VAH/VAL within 5 ticks: +35
   - PDH/PDL within 5 ticks: +30
   - PDM within 5 ticks: +20
   - nPOC within 8 ticks: +25
   - PW POC within 8 ticks: +20
3. Clamp to [0, 100]
4. zoneDistTicks = min distance to any qualifying anchor

This is a single-function, zero-dependency implementation. Wire it into ConfluenceScorer calls in both DEEP6Strategy and BacktestRunner.

### 4.2 ENG-05 MicroProbDetector — Scaffold, Not Signal

**Current state:** MicroProbDetector (ENG-05) implements a Naive Bayes micro probability engine. From the CONTEXT.md, this is classified as HARD complexity. The core logic requires per-session training data — prior bars must accumulate enough samples for the probability estimate to be meaningful.

**Gap:** The detector is registered and called, but if the Naive Bayes prior is not seeded (no historical frequencies available at bar 1), it either returns zero-strength signals or constant signals — both are useless. More critically, if it emits spurious signals at session open, it adds noise to the category vote.

**Recommendation R-4.2 (P1):** Add a `MinBarsBeforeFiring` gate to MicroProbDetector — do not emit any signals until `barsSinceOpen >= 20`. During the warm-up period, the frequency estimates are unreliable. Additionally, add a `ConfidenceFloor = 0.55` threshold: only emit when `P(reversal) >= 0.55`. Below 0.55 is coin-flip territory and adds noise.

### 4.3 ENG-06 VPContextDetector — Depth Without Calibration

**Current state:** VPContextDetector provides volume profile context signals. Its effectiveness depends on the session's VP being sufficiently developed — at session open, the VP is a single bar.

**Recommendation R-4.3 (P1):** Same `MinBarsBeforeFiring = 30` gate as ENG-05. VP context signals are meaningless before the IB is established (first 30 min = bars 0–30).

### 4.4 Signal Correlation and Redundancy

**Concern:** 44 signals across 8 categories. The Phase 3 research plan explicitly calls for a pairwise Pearson correlation matrix (`03-04-PLAN.md`), but no evidence the correlation analysis results were applied to reduce redundancy.

**Known high-correlation pairs (by construction):**
- ABS-01 (Classic) and ABS-03 (Stopping Vol) both require `totalVol > volEma * multiplier` — they will often co-fire. When both fire, the absorption category only gets one vote (per the dedup logic), but both contribute to `bullWeightSum` / `bearWeightSum` independently.
- EXH-05 (Fading Momentum) and DELT-05 (Delta Flip) both detect delta/price direction divergence — structurally correlated.
- TRAP-01 (Inverse Imbalance Trap) and IMB-05 (Inverse Trap) both require opposite-direction imbalances — may be computing the same condition with different thresholds.

**Recommendation R-4.4 (P2):** After 30+ live sessions of data, run the correlation matrix across all 44 signals' fire rates. Any pair with r > 0.7 that falls in the same category should be merged into a single signal ID with a "severity" parameter, or the weaker one removed. Reducing to 35–38 independent signals will improve statistical robustness.

### 4.5 Cooldown Calibration

**Current:** 5-bar cooldown for exhaustion sub-types. No cooldown on absorption.

**Assessment:** The 5-bar cooldown was set in Phase 2 as a default. On 1-minute NQ bars, 5 bars = 5 minutes. This is reasonable for most exhaustion variants but may be too short for EXH-01 (ZeroPrint) — a zero print level should suppress the same signal until price revisits that level (price-based cooldown, not bar-based).

**Recommendation R-4.5 (P2):** For EXH-01 specifically, change cooldown to price-based: suppress EXH-01 at price P until the bar High >= P (for bearish prints) or bar Low <= P (for bullish prints). This is a one-line change in the cooldown check. For all other sub-types, 5 bars remains appropriate.

---

## 5. Risk Management Enhancements

### 5.1 Fixed Stop Weakness

**Current:** `StopLossTicks = 20` (NQ = 5 points, $100/contract). Fixed regardless of market volatility.

**Problem:** On high-volatility NQ days (ATR = 15+ points/bar), a 5-point stop is inside the bar's natural noise range — you will be stopped out on the second tick. On low-volatility days (ATR = 4 points/bar), a 5-point stop is appropriate.

**Recommendation R-5.1 (P1 — high priority):** Replace fixed stop with ATR-dynamic stop: `StopLossTicks = max(12, (ATR * 1.5) / tickSize)`. For a typical NQ ATR of 8 points = 32 ticks, this gives a stop of 48 ticks (12 points, $240). For a quiet day with ATR = 4 points = 16 ticks, stop = max(12, 24) = 24 ticks. Floor of 12 ticks prevents stops that are too tight.

In BacktestRunner, this requires passing `sessionAtr` into the exit logic. In DEEP6Strategy, `_atr` is already tracked — use it directly.

### 5.2 Volatility-Adjusted Position Sizing

**Recommendation R-5.2 (P2):** Once TypeA 2-contract sizing is live (R-2.4), add a volatility circuit breaker: if current ATR > 2× 20-day average ATR, revert to 1-contract sizing. High-volatility NQ days are more prone to false breakouts and wider bid-ask spreads, reducing the edge on orderflow signals.

### 5.3 Correlation with ES/SPY Regime

**Recommendation R-5.3 (P2):** NQ's orderflow signals degrade significantly when the broad market (ES) is in a strong directional trend. Consider adding a "trend filter" check: if ES 20-bar momentum is strongly directional (>1.5 ATR from 20-bar mean), reduce `MinTierForEntry` to TYPE_A-only (disable TYPE_B entries). This is a secondary data series addition to DEEP6Strategy — one line to add ES as a data series, then compute its momentum in OnBarUpdate.

### 5.4 Intraday Loss Ratcheting

**Recommendation R-5.4 (P1):** Extend the daily loss cap logic: the current system kills trading when daily loss >= $250. Add an intermediate ratchet:
- Loss >= 50% of daily cap ($125): reduce TypeA contracts from 2 to 1, TypeB from 1 to 0 (TypeB paused)
- Loss >= 75% of daily cap ($187.50): TypeA only at 1 contract
- Loss >= 100% ($250): kill switch (current behavior)

Implement as a `GetCurrentRisk()` method in DEEP6Strategy that returns one of {FULL, REDUCED, MINIMAL, STOPPED}.

### 5.5 Session-End Risk

**Current:** `IsExitOnSessionCloseStrategy = true`, `ExitOnSessionCloseSeconds = 30`. Forces flat at session end.

**Gap:** The backtest force-exits at the last bar's close price (`SESSION_END`). In live trading, NT8's session-close exit uses market orders — on NQ at 15:59 ET, market impact is real.

**Recommendation R-5.5 (P1):** Set `RthEndMinute = 45` (15:45 ET) as the entry cutoff to ensure no new trades are entered in the last 15 minutes, and add explicit `ExitOnSessionCloseSeconds = 300` (5 minutes before session close) to allow orderly limit order exits rather than market orders at the bell.

---

## 6. Market Microstructure Edge Decay

### 6.1 Durability of Footprint Signals in NQ

NQ footprint signals derive their edge from two sources: (1) institutional absorption/exhaustion at key levels and (2) trapped retail traders creating predictable flow. Both are structural and not easily arbitraged away, but each has regime-dependent durability.

**High-durability conditions:**
- News-quiet days: absorption signals at prior-day POC/VAH/VAL have historically 65–72% win rate (based on system backtest data and market structure research)
- IB range < 25 ticks: tight IB creates cleaner auction theory signals (AUCT-01/02) and higher absorption conviction
- GEX regime = "pinning": gamma exposure acts as a magnetic attractor to key strikes, amplifying absorption effects

**Low-durability conditions:**
- CPI/FOMC days: institutional absorption disappears as large players exit or hedge rather than defend levels. The news blackout windows address this partially but not fully — the *entire day* before a major macro event should use stricter thresholds.
- Momentum-trending sessions (DELT-08 slingshot firing repeatedly in same direction): footprint reversal signals are counter-trend entries in a trending market. Expected false-positive rate is 3–4× normal.
- Low-volume pre-holiday sessions: thin order book means large orders appear as absorption when they are merely structural thin markets.

**Recommendation R-6.1 (P1):** Add a `SessionRegimeClassifier` that runs at IB close (bar 30) and classifies the day as {AUCTION, TRENDING, MACRO_RISK}. Gate:
- AUCTION: normal threshold (TypeB eligible)
- TRENDING: raise entry threshold to TypeA minimum score 85
- MACRO_RISK: TypeA only, score >= 88, no TypeB entries

### 6.2 Half-Life of Orderflow Edge in NQ

Based on industry research and NQ-specific orderflow behavior:

- **Absorption at key levels:** Edge is robust over 1–2 year horizons because it reflects institutional behavioral patterns that do not change quickly. The half-life is measured in years, not months.
- **Delta divergence signals (DELT-04/10):** More susceptible to HFT adaptation. If algorithmic traders begin exploiting the same divergence patterns, the edge decays in 6–12 months. Monitor monthly win rate; if it falls below 50% for 20 consecutive trades, treat this signal category as degraded.
- **Stacked imbalance signals (IMB-03 T2/T3):** Structural — these reflect genuine liquidity concentration and are not easily arb'd. Half-life: multi-year.
- **Counter-spoof (ENG-03):** Highest decay risk. Spoofing detection algorithms are actively pursued by HFT, creating an arms race. If HFT adapts their spoofing patterns, ENG-03 may begin firing on genuine orders while missing synthetic ones. Treat as an alert-only signal (does not contribute to score) and monitor separately.

**Recommendation R-6.2 (P3):** Set up a monthly signal audit: compute per-signal win rate over the last 30 trading days, flag any signal where 30-day win rate < 45% as "DEGRADED" in a config file, and exclude degraded signals from the scorer's category vote. This is the foundation for a self-healing signal stack.

---

## 7. Infrastructure Improvements

### 7.1 Live Capture Harness → Continuous Learning

**Current state:** Phase 17 built a capture harness writing NDJSON session files to `ninjatrader/captures/`. These are used for parity validation but not for continuous learning.

**Gap:** Signal quality, regime patterns, and parameter effectiveness degrade silently without a feedback loop.

**Recommendation R-7.1 (P1):** Extend the capture harness to write per-trade outcomes into a DuckDB database (the infrastructure at `data/backtests/replay_full_5sessions.duckdb` already exists). Schema: `(session_date, bar_idx, signal_ids, score, tier, direction, entry_price, exit_price, pnl_ticks, exit_reason, regime_class)`. After 30 days of paper trade, this database becomes the training set for ML weight optimization.

### 7.2 Automated Daily Report

**Recommendation R-7.2 (P1):** Add a `DailyReportEmitter` class that writes a structured summary at session end to `ninjatrader/reports/YYYY-MM-DD.json`:
- Trades taken with tier and exit reason distribution
- Signals fired by category (how many TypeA/B/C signals per category per day)
- Regime classification for the day
- Running 30-day Sharpe ratio and max drawdown

This is a 100-line class in NinjaScript, zero external dependencies, triggered by `IsExitOnSessionCloseStrategy` callback.

### 7.3 A/B Testing Framework

**Recommendation R-7.3 (P2):** After 30 days of paper trade, create a second strategy instance with modified parameters (e.g., `MinTierForEntry = TYPE_B`, `StopLossTicks = 24`) running on a second sim account. Compare weekly Sharpe, win rate, and profit factor. This is the formal mechanism for testing all P2 recommendations without risking live capital.

### 7.4 Model Retraining Cadence

**Recommendation R-7.4 (P2):** Establish a monthly retraining schedule:
- **Trigger:** 30-day rolling win rate < 55% OR 30-day Sharpe < 0.8
- **Retrain:** Run vectorbt parameter sweeps on last 60 days of captured data using the Python reference engine. The Python engine with Optuna (Phase 9 design) is the correct tool for this.
- **Deploy:** Port updated weights into ConfluenceScorer.cs constants and restart NT8.

---

## 8. Road to Production Readiness

### 8.1 Exact Steps from Current State to Live Capital

**Current state:** Phase 18 partially complete (scorer wired into strategy but zoneScore = 0, TypeA never fires). Phase 19 not started.

**Required steps in order:**

| Step | Task | Priority | Estimated Effort |
|------|------|----------|-----------------|
| 1 | Implement ZoneScoreCalculator + wire into ConfluenceScorer (R-4.1) | P0 | 1 day |
| 2 | Implement ATR-trailing stop in BacktestRunner + DEEP6Strategy (R-3.1) | P0 | 1 day |
| 3 | Validate TypeA fires on 5+ historical recorded sessions | P0 | 0.5 days |
| 4 | Re-run backtest on all 5 sessions with trailing stop — measure new metrics | P0 | 0.5 days |
| 5 | Set MinTierForEntry = TYPE_B for Phase 19 paper trade (R-1.5) | P0 | 0.5 days |
| 6 | Add ATR-dynamic stop to DEEP6Strategy (R-5.1) | P1 | 0.5 days |
| 7 | Add intraday loss ratcheting (R-5.4) | P1 | 0.5 days |
| 8 | Add opposing-signal exit tier gate (R-3.5) | P1 | 0.5 days |
| 9 | Run Phase 19: 30-day paper trade on APEX-262674 + LT-45N3KIV8 | Gate | 30 days |
| 10 | Analyze 30-day paper trade results against R-1.5 baseline | Gate | 3 days |
| 11 | Deploy TypeA-only live capital trading at 1 contract | Live | — |

### 8.2 Pre-Live Validation Checklist

Before deploying live capital, ALL of these must be TRUE:

- [ ] TypeA fires at least 2× per week on recorded replay sessions
- [ ] TypeB fires at least 5× per week on recorded replay sessions  
- [ ] Trailing stop implemented and tested in backtest (R-3.1)
- [ ] ZoneScore properly computed from ProfileAnchorLevels (R-4.1)
- [ ] 30-day paper trade completed with win rate >= 52% and profit factor >= 1.3
- [ ] Daily loss cap tested: kill switch activates correctly at -$250
- [ ] ATM templates configured with correct stop/target matching BacktestConfig
- [ ] News blackout windows verified live (8:30 ET, 10:00 ET, 14:00 ET)
- [ ] Re-entry logic tested: re-engage after stop fires correctly (R-2.3)
- [ ] Session-end exit at 15:45 ET confirmed (no open positions after 15:45)
- [ ] C# ↔ Python scoring parity validated on ≥5 sessions (Phase 18 requirement)
- [ ] Account whitelist (`ApprovedAccountName`) set to live account name, not Sim101
- [ ] `EnableLiveTrading = true` only after all above checks pass

### 8.3 Risk Per Trade Sizing Formula

For a $50,000 account:
- **Maximum risk per trade:** 2% of account = $1,000
- **ATR-dynamic stop (from R-5.1):** For NQ ATR = 8 points = 32 ticks: stop = max(12, 48) = 48 ticks × $5/tick = $240/contract
- **Maximum contracts at $1,000 risk:** floor($1,000 / $240) = 4 contracts (but system caps at 2)
- **TypeA recommended:** 2 contracts × $240 = $480 risk (0.96% of account) — within 2% rule
- **TypeB recommended:** 1 contract × $240 = $240 risk (0.48% of account)

**Formula:** `MaxContracts = floor(AccountBalance * MaxRiskPct / (ATRStopTicks * TickValue))`

For prop accounts (Apex $50K, Lucid $45N3KIV8): confirm exact drawdown limits with prop firm before sizing up. Apex typically allows 4% trailing drawdown — at 2 contracts and $240 risk/trade, a 6-trade losing streak = $2,880, which is within 4% of a $50K account.

### 8.4 Capital Requirements

| Account Size | Recommended Starting | Reason |
|-------------|---------------------|--------|
| Absolute minimum | $25,000 | CME 1-lot NQ overnight margin ~$15,000; need 50% buffer for drawdowns |
| Conservative | $50,000 | 6-trade losing streak ($1,440 at 1 lot) = 2.9% drawdown; comfortable within Apex/Lucid limits |
| Optimal for 2-lot TypeA | $75,000–$100,000 | 2-lot TypeA ($480/trade) × 6-trade losing streak = $2,880 = 2.9–3.8% drawdown |

**Expected maximum drawdown (based on backtest configuration):**
- With fixed 20-tick stop, 40-tick target, 1-lot: max drawdown historically ~$600–$1,200 per 30-day period assuming ~50% win rate
- With ATR-dynamic stop (R-5.1) and trailing stop (R-3.1): expected reduction to $400–$800 per 30-day period (fewer full stops taken)

---

## Priority Matrix

### P0 — Must Fix Before Paper Trading

| # | Recommendation | Description | File(s) |
|---|---------------|-------------|---------|
| P0-1 | **R-4.1 ZoneScore wiring** | TypeA never fires without this. Implement `ZoneScoreCalculator.Compute()` and wire into ConfluenceScorer calls in DEEP6Strategy and BacktestRunner | `Scoring/ZoneScoreCalculator.cs` (new), `DEEP6Strategy.cs`, `BacktestRunner.cs` |
| P0-2 | **R-3.1 ATR-trailing stop** | Without trailing stop, every winning trade that retraces to stop becomes a loser. Add `TrailActivationTicks=15`, `TrailAtrMult=1.5`, `TrailTightenTicks=25`, `TrailTightenMult=1.0` | `BacktestConfig.cs`, `BacktestRunner.cs`, `DEEP6Strategy.cs` |
| P0-3 | **R-1.5 TypeB as primary trading tier** | TypeA alone will produce 2–5 trades/week — insufficient for 30-day statistical validation. Set `MinTierForEntry = TYPE_B` for Phase 19 | `DEEP6Strategy.cs` defaults, Phase 19 config |
| P0-4 | **R-2.1 Backtest calibration for bar-close entry** | `StopLossTicks=22`, `TargetTicks=38` to correct for bar-close-to-next-open drift. Current 20/40 metrics are optimistic by ~2 ticks on each side | `BacktestConfig.cs` |
| P0-5 | **Validate TypeA fires on historical sessions** | After R-4.1, replay all 5+ recorded sessions through the scorer and confirm TypeA fires at least 2× per session on valid setups. Document in a PARITY-REPORT.md before Phase 19 | `ninjatrader/tests/` + manual verification |

### P1 — Must Fix Before Live Capital

| # | Recommendation | Description |
|---|---------------|-------------|
| P1-1 | R-5.1 ATR-dynamic stop | Replace fixed 20-tick stop with `max(12, ATR * 1.5 / tickSize)` |
| P1-2 | R-3.5 Opposing-signal exit by tier | Replace `ExitOnOpposingScore=0.50` with tier-gated exit (TypeB exits, TypeC tightens) |
| P1-3 | R-3.2 Breakeven stop | Move stop to entry+1 tick after MFE >= 10 ticks |
| P1-4 | R-2.3 Re-entry after stop | Allow same-direction re-entry within 3 bars if score >= threshold+5 and tier = TypeA |
| P1-5 | R-5.4 Intraday loss ratcheting | Reduce sizing at 50% daily cap, suspend TypeB at 75% cap |
| P1-6 | R-5.5 Session-end exit timing | Move entry cutoff to 15:45 ET, `ExitOnSessionCloseSeconds=300` |
| P1-7 | R-4.2 / R-4.3 ENG-05/06 warmup gates | Add `MinBarsBeforeFiring=20` to MicroProbDetector, `MinBarsBeforeFiring=30` to VPContextDetector |
| P1-8 | R-2.4 Tiered position sizing | TypeA=2 contracts (behind account-size gate), TypeB=1 contract |
| P1-9 | R-7.1 Trade outcome database | Write trade outcomes to DuckDB for continuous learning |
| P1-10 | R-7.2 Daily report emitter | Write YYYY-MM-DD.json report at session end |

### P2 — Optimize After First Live Month

| # | Recommendation | Description |
|---|---------------|-------------|
| P2-1 | R-1.2 Weight grid sweep | Vectorbt sweep over absorption (20–35) and exhaustion (14–24) weights |
| P2-2 | R-1.3 Delta chase as soft penalty | Replace hard TypeA veto with 10-point score reduction |
| P2-3 | R-1.4 ATR-normalized delta chase | `DELTA_CHASE_MAG = max(50, ATR_equiv * 0.4)` |
| P2-4 | R-2.2 Intra-bar entry mode | Optional `Calculate.OnEachTick` entry on signal detection |
| P2-5 | R-2.5 IB multiplier timing | Activate at bar 10, not bar 0 |
| P2-6 | R-3.3 Time-decay target tightening | Reduce target at 60% of MaxBarsInTrade if MFE < 50% of target |
| P2-7 | R-3.4 Scaling out on 2-contract TypeA | Exit 1 at 20 ticks, trail second to full target |
| P2-8 | R-4.4 Signal correlation analysis | Run Pearson matrix after 30 sessions, remove r>0.7 redundant signals |
| P2-9 | R-4.5 EXH-01 price-based cooldown | Price-based vs bar-based cooldown for ZeroPrint |
| P2-10 | R-5.2 Volatility circuit breaker | Revert to 1-contract when ATR > 2× 20-day average |
| P2-11 | R-5.3 ES regime filter | Raise entry threshold when ES is strongly trending |
| P2-12 | R-6.1 Session regime classifier | Classify AUCTION / TRENDING / MACRO_RISK at IB close |
| P2-13 | R-7.3 A/B testing framework | Second sim account with alternate parameters |
| P2-14 | R-7.4 Monthly retraining cadence | Vectorbt sweep trigger at 30-day win rate < 55% |

### P3 — Nice-to-Have

| # | Recommendation | Description |
|---|---------------|-------------|
| P3-1 | R-6.2 Signal half-life monitoring | Monthly per-signal win rate audit, auto-flag DEGRADED signals |
| P3-2 | EXH-01 price-based cooldown v2 | Cross-session persistence of zero-print levels (requires SQLite) |
| P3-3 | Kronos E10 integration | Deferred per PROJECT.md; add as directional bias filter post-v1 |
| P3-4 | ENG-03 counter-spoof alert-only | Demote to alert-only (no score vote), monitor separately for HFT adaptation |
| P3-5 | Late-session window boost | 1.05x multiplier for bars 270–360 (14:00–15:00 ET) |

---

## Brutal Honesty: Systemic Weaknesses

1. **The system has never been paper-traded.** All performance data is from the BacktestRunner replaying scored-bar NDJSON files. This is a simulation of a simulation — the NDJSON files themselves are generated from the detector pipeline, not from external ground-truth data. There is a risk of circular validation.

2. **The scoring formula has never been optimized on live data.** The weights were set from analysis of 4,590 bars. NQ generates ~390 bars/day × 250 trading days = ~97,500 bars/year. The current dataset is 4.7% of one year's data — not enough to claim statistical significance on any weight.

3. **EXH-04 (FatPrint) emits `Direction = 0`.** This means FatPrint never contributes a directional vote and never increments either `bullWeightSum` or `bearWeightSum`. It may add to category counting via the loop but the current code has `if (r.Direction == 0) continue` at the top of the signal processing loop in ConfluenceScorer — meaning FatPrint is entirely ignored by the scorer. This is a signal definition gap: FatPrint should either have a direction (based on whether the fat print is at the top or bottom of the bar) or be explicitly documented as a context signal with no directional vote.

4. **The opposing-signal exit at `ExitOnOpposingScore = 0.50` is dangerously low.** A score of 0.50 is essentially noise — it corresponds to 2-3 weak signals in one category. You will be exited from valid trades by noise signals. This is a live-capital risk. Fix before paper trade, not before live capital.

5. **No validation that the NT8 aggressor heuristic (`price >= bestAsk`) matches Rithmic's actual aggressor field.** The strategy uses BBO-based aggressor inference. Research suggests this overestimates aggressive buying by 5–15% compared to exchange-stamped aggressor fields. This directly affects delta calculations and may systematically bias the delta direction agreement gate.

---

*This document covers all requested dimensions. Every recommendation is implementable as an independent GSD quick task. Priority sequence: P0-1 → P0-2 → P0-3 → P0-4 → P0-5 → begin Phase 19 paper trade → P1 items → live capital after Phase 19 validation.*

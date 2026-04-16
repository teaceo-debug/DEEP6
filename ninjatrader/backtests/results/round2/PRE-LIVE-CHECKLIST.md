# DEEP6 Pre-Live Trading Checklist

**Instrument:** NQ front-month  
**Account:** APEX-262674 (Apex funded) — primary; LT-45N3KIV8 (Lucid funded) — secondary  
**Gate:** ALL items in Code Readiness, Configuration, Data Validation, Paper Trading Gate, and Risk Management must be checked before setting `EnableLiveTrading=true`.  
**Version:** Phase 19 — Apex/Lucid Paper-Trade Gate output  
**Date prepared:** 2026-04-15

---

## Group 1: Code Readiness

*NT8 must compile, load, and run without errors. Verify these before any live session.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 1 | [ ] DEEP6Strategy.cs compiles without errors in NT8 editor (Ctrl+F5 / Build All) | Open NinjaScript Editor, select DEEP6Strategy, press F5 — Output tab shows "Compilation succeeded" with zero errors and zero warnings on strategy-related files. | YES |
| 2 | [ ] DEEP6Footprint.cs (indicator) compiles without errors | Same as above for the indicator. Strategy references types from AddOns.DEEP6 — if indicator has compile errors, strategy will also fail. | YES |
| 3 | [ ] All DEEP6 AddOn files compile: DetectorRegistry, ScorerSharedState, all ISignalDetector implementors (ABS, EXH, IMB, DELT, AUCT, VOLP, TRAP, ENG-02..07) | Build All in NinjaScript Editor. Check for CS error codes. Any unresolved type reference in AddOns.DEEP6 namespace will cascade to the strategy. | YES |
| 4 | [ ] Strategy loads on a sim chart without error (attach to NQ 1-min chart in sim) | Add DEEP6Strategy to a NQ 1-min chart in Simulator mode. NT8 Output window must show "[DEEP6 Strategy] Initialized. EnableLiveTrading=False" and "[DEEP6 Strategy] DRY RUN — no orders will be submitted." | YES |
| 5 | [ ] No NullReferenceException in Output window during first 5 bar updates | Watch NT8 Output window for 5 minutes after strategy load. Any NullReferenceException indicates uninitialized state — stop and fix before proceeding. | YES |
| 6 | [ ] UseNewRegistry=true confirmed in strategy properties | Open strategy properties panel, verify UseNewRegistry=true. This enables the Phase 17 detector registry (all 44 signals). UseNewRegistry=false falls back to legacy ABS/EXH-only path — half the signals, unvalidated for Phase 18+ scorer. | YES |
| 7 | [ ] ScoreSharedState is published by indicator and readable by strategy | In NT8 Output, after indicator and strategy load on same chart, look for "[DEEP6 Strategy] scorer gate — score=X tier=Y" entries on bar updates. If score is always 0.0, ScorerSharedState wiring is broken. | YES |
| 8 | [ ] ATM templates exist: DEEP6_Absorption, DEEP6_Exhaustion, DEEP6_Confluence, DEEP6_Practice | Open NT8 Strategies → ATM Strategies. All four template names must be present. Missing ATM templates = no bracket orders can be submitted. | YES |
| 9 | [ ] ATM template DEEP6_Confluence has 2-contract quantity with T1=16t, T2=32t, SL=20t configured | Open DEEP6_Confluence ATM template in NT8 ATM editor. Verify: Quantity=2, Profit Target 1=16 ticks (50% = 1 contract), Profit Target 2=32 ticks (remaining 1 contract), Stop Loss=20 ticks. | YES |
| 10 | [ ] No memory leak: strategy runs for 60+ minutes without NT8 RAM growing unboundedly | After 60 min on live-sim session, check NT8 memory via Windows Task Manager. RAM growth >500MB/hr indicates the _bars Dictionary cleanup (cutoff = CurrentBar - 500) or _l2Bids/Asks is not purging. | YES |

---

## Group 2: Configuration

*All properties must be set per PRODUCTION-CONFIG.md before the first paper-trade session.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 11 | [ ] EnableLiveTrading=false | Open strategy properties. Confirm value is False. The "DRY RUN" message in NT8 Output window is the definitive confirmation — if it does not appear, assume live routing is active regardless of what the panel shows. | YES |
| 12 | [ ] ApprovedAccountName matches the exact sim account name | In NT8 Accounts window, note the exact name (e.g., "Sim101" or "APEX-262674-SIM"). Enter this exact string in ApprovedAccountName. Then load the strategy and verify "[DEEP6 Strategy] account whitelist OK" appears in Output. | YES |
| 13 | [ ] ScoreEntryThreshold=70.0 | Open strategy properties, confirm value. Do not accept 70 as integer — confirm as 70.0 (double). Some NT8 property panels round display. | YES |
| 14 | [ ] MinTierForEntry=TYPE_B | Confirm in properties panel dropdown. TYPE_A will produce zero trades (zone scoring not wired). | YES |
| 15 | [ ] StopLossTicks=20 confirmed in BacktestConfig (offline) AND in ATM template | BacktestConfig.cs default value=20. ATM template SL=20 ticks. Both must agree — if they differ, paper-trade results will not match offline backtest assumptions. | YES |
| 16 | [ ] ScaleOutEnabled=true AND ScaleOutTargetTicks=16 AND TargetTicks=32 | Confirm all three in strategy properties or BacktestConfig. If ScaleOutEnabled=false, the system trades all-in/all-out — valid but diverges from the backtested scale-out config. | YES |
| 17 | [ ] BreakevenEnabled=true, BreakevenActivationTicks=10, BreakevenOffsetTicks=2 | Confirm in strategy properties. If breakeven is disabled, the Sharpe estimate is ~8% lower than the 20.21 paper target. | NO — strongly recommended |
| 18 | [ ] MaxBarsInTrade=60 | Confirm in BacktestConfig and strategy properties. | YES |
| 19 | [ ] VolSurgeVetoEnabled=true | Confirm in properties panel. This is the single highest-value filter (+$2,685 recovered in backtest). If accidentally disabled, paper trade will trade volatile sessions — expect significant drawdown on event days. | YES |
| 20 | [ ] SlowGrindVetoEnabled=true AND SlowGrindAtrRatio=0.5 | Confirm both values. SlowGrindAtrRatio=0.5 is the validated default. Do not change during Phase 19. | YES |
| 21 | [ ] StrictDirectionEnabled=true | Confirm in properties. Delta Sharpe gain: +19.601 from strict mode. Without it, noisy entries degrade win rate from 79% to 69%. | YES |
| 22 | [ ] BlackoutWindowStart=1530 AND BlackoutWindowEnd=1600 | Confirm both values. Verify no trades in 15:30–16:00 window on the first paper session. | YES |
| 23 | [ ] DailyLossCapDollars=500.0 | Confirm in properties panel. This is the kill-switch threshold — do not set above $500 for Phase 19. | YES |
| 24 | [ ] MaxContractsPerTrade=2 AND MaxTradesPerSession=5 | Confirm both. MaxContractsPerTrade=2 is required for scale-out. MaxTradesPerSession=5 is a conservative cap for paper trade. | YES |
| 25 | [ ] RthStartHour=9 AND RthStartMinute=35 AND RthEndHour=15 AND RthEndMinute=50 | Confirm all four. These define the hard trading window. Entries outside this window should not fire even if signals are strong. | YES |
| 26 | [ ] RespectNewsBlackouts=true | Confirm in properties. The hard-coded blackouts (08:25, 10:00, 14:00) must be active for the first paper session. | YES |
| 27 | [ ] Slippage=0 in strategy properties (not BacktestConfig) | NT8 Strategy slippage field (not BacktestConfig) should be 0 — slippage is handled by the ATM template fill logic in live/sim mode. BacktestConfig.SlippageTicks=1.0 is for offline backtests only. | NO — important for P&L accuracy |
| 28 | [ ] ExitOnOpposingScore=0.3 | Confirm. Inconclusive in backtest but low risk at 0.3. Set and leave — revisit after 30 sessions. | NO |

---

## Group 3: Data Validation

*Verify that the live Rithmic feed is delivering correct data before trading any real session.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 29 | [ ] Rithmic live feed connected — NQ tick data streaming at expected volume | In NT8, open Connections. Rithmic connection should show green status. On a NQ 1-min chart, confirm ticks are printing in real time. Expected volume: >500 ticks/minute during RTH, >100/minute pre-market. | YES |
| 30 | [ ] Footprint bars are accumulating bid and ask volume correctly | In NT8 Output, strategy logs "[DEEP6 Strategy] ...finalized bar..." entries with non-zero bid/ask volumes. Manually compare one footprint bar's bid volume total to what you see in Bookmap or Sierra Chart for the same bar. They must match within 2–3 ticks (rounding from aggressor inference). | YES |
| 31 | [ ] Aggressor field is resolving correctly (not all-unknown) | In NT8 Output, look for "[DEEP6 Strategy] aggressor=1" (ask hit) and "aggressor=2" (bid hit) entries. If >80% of ticks show aggressor=0 (unknown), the BBO state is not updating — likely OnMarketData is not receiving Bid/Ask prior to Last tick. This will corrupt all delta signals. | YES |
| 32 | [ ] Signals are firing on live bars (at least one ABS or EXH signal per 30-minute RTH window) | Watch NT8 Output during the first RTH session. ABS-01 fires on 9.9% of bars (SIGNAL-ATTRIBUTION.md). On a 30-minute window (30 bars), expect 2–3 ABS-01 detections and 0–2 EXH-02 detections. Zero detections for 60+ bars = signal wiring failure. | YES |
| 33 | [ ] Scorer is producing non-zero scores on signal bars | In NT8 Output, look for "[DEEP6 Strategy] scorer gate — score=X tier=Y" on bars where signals fired. Score should be >0 and proportional to signal strength (expect 40–90 range for TYPE_B entries). Score=0 on every bar = scorer not wired. | YES |
| 34 | [ ] VOLP-03 fires at least once during a high-volume opening bar | VOLP-03 fires on 2.1% of bars (SIGNAL-ATTRIBUTION.md). During the first day's opening 15 minutes (high volume), it should fire at least once. If it never fires across 5 sessions, suspect VOLP-03 detector or the VolPatternDetector is not registered. | NO — but important for veto validation |
| 35 | [ ] GEX levels (if integrated via massive.com) loading without stale flag | If DEEP6Footprint is pulling GEX data from massive.com API, verify API key in .env and that the indicator is logging GEX levels. Stale GEX flag (>120s without update) should trigger a warning. GEX integration is optional for Phase 19 — if not wired, zone scoring will default to 0.0, which means TypeA never fires. Acceptable for TYPE_B paper trading. | NO |
| 36 | [ ] No data gaps or disconnections in first 5 consecutive sessions | Review NT8 logs for "connection reset" or "data gap" events. Any mid-session disconnect that occurs while a position is open is a critical risk — verify NT8 reconnection behavior (RealtimeErrorHandling=StopCancelClose should close open positions on disconnect). | YES |
| 37 | [ ] Bar timestamps are in Eastern time and match expected session structure | First bar of session should timestamp 09:30–09:31 ET. Last bar before mid-day block should be ~13:30 ET. Verify no bars are timestamped in UTC (off by 4–5 hours during EDT). Timestamp errors corrupt the BlackoutWindowStart comparison. | YES |

---

## Group 4: Paper Trading Gate

*30-session minimum paper-trade run with defined metric thresholds. Phase 19 gate per ROADMAP.md Phase 19 success criteria.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 38 | [ ] 30 consecutive RTH sessions completed without crash or stall on BOTH Apex sim and Lucid sim | Count sessions in daily log file. A "session" = at least one trade signal evaluation (even if vetoed). Strategy must remain loaded from market open (09:30) to ExitOnSessionClose (16:00) without NT8 freeze or restart. | YES |
| 39 | [ ] Paper-trade win rate >= 75% over all 30 sessions (combined) | Export trade history from NT8 Performance tab. Win rate = winners / (winners + losers). Target from backtest: 84.5% (RISK-MANAGEMENT.md). Accept >=75% as go-live threshold (1 standard deviation below backtest). If <75%, do not proceed — investigate signal or scorer wiring. | YES |
| 40 | [ ] Paper-trade profit factor >= 2.0 over 30 sessions | Profit factor = gross profit / gross loss. Backtest PF=16.35 on best walk-forward config. Live PF will be lower due to real slippage and fill quality. Accept PF>=2.0 as go-live minimum. PF=1.0 = break-even; PF<1.0 = losing system — stop immediately. | YES |
| 41 | [ ] Minimum 30 total trades over the 30 sessions (1+ trade per session average) | Low trade count = statistical insignificance. If <30 trades in 30 sessions, extend paper trade to 45 sessions before go/no-go. Common causes: ScoreEntryThreshold too high, TYPE_B signals not firing, session selection missing TYPE_B qualifying bars. | YES |
| 42 | [ ] 95th-percentile fill slippage <= 4 ticks per side on market entries | Record entry and exit prices vs signal-bar close price for each trade. Slippage = abs(actual fill - expected price). 95th pct slippage <=4t is the acceptable threshold. >4t means ATM template or order routing is degrading fill quality. | YES |
| 43 | [ ] All 5 risk gates verified firing at least once each during paper trade: account whitelist, news blackout, daily loss cap, max trades/session, RTH window | Review NT8 Output logs across 30 sessions. For each risk gate, confirm at least one log entry of the gate blocking an action. If daily loss cap never fires over 30 sessions, that is expected (clean sessions) — but trigger it manually in a dedicated test session by forcing 3 consecutive simulated losses. | YES |
| 44 | [ ] No stop-out in the first 3 bars of a session (opening trap) | Review trade entries. If any trade enters within bars 0–3 (09:30–09:33 ET) and stops out, the BarsRequiredToTrade=20 gate may not be enforcing correctly, or ATR has not primed. Entries in bars 0–20 are explicitly blocked by BarsRequiredToTrade. | NO — quality check |
| 45 | [ ] Per-signal attribution log shows ABS-01 as primary alpha driver (>50% of winning trades) | Export daily logs, group by signal ID at entry. ABS-01 should be present on >50% of winning entries per SIGNAL-ATTRIBUTION.md (SNR=9.46, highest of any signal). If IMB-03 or EXH-02 dominate without ABS-01, the signal weighting may be miscalibrated. | NO — quality check |
| 46 | [ ] Zero VOLP-03 veto override during the 30 sessions (veto respected on all volatile events) | Confirm no entry logged in sessions where VOLP-03 fired. Cross-reference against known news events (CPI, FOMC, NFP). Any trade that entered on a VOLP-03-active session requires investigation. | YES |
| 47 | [ ] TypeA tier fires at least 3 times during 30 sessions (confirms zone scoring is wired) | Review tier column in trade log. Even with zone scoring at 0.0, if a very high-quality setup scores >=80 with catCount>=5, it should classify TypeA. Three TypeA entries in 30 sessions is a minimal validation. Zero TypeA entries suggests zone scoring is still returning 0.0 — acceptable for Phase 19, but note for Phase 20 work. | NO |
| 48 | [ ] Written go/no-go decision document committed to .planning/ | Create .planning/GO-NOGO-PHASE19.md with: total sessions, total trades, win rate, PF, max drawdown, worst session P&L, VOLP-03 veto count, kill-switch activations, and binary go/no-go recommendation. Commit before flipping EnableLiveTrading=true on any funded account. | YES |

---

## Group 5: Risk Management

*Hard gates on position sizing, loss caps, and account protection. Non-negotiable.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 49 | [ ] DailyLossCapDollars confirmed at $500 (NOT higher) for first live session | Open strategy properties immediately before the first live session. Confirm 500.0. Do not accept verbal confirmation — read the value in the panel. | YES |
| 50 | [ ] Account whitelist verified: ApprovedAccountName matches the funded account name EXACTLY | In NT8 Accounts window, note the exact name of the Apex or Lucid funded account. It must match ApprovedAccountName character-for-character including case and hyphens. e.g., "APEX-262674" vs "Apex-262674" — these are different strings. Test: temporarily set to wrong name, confirm strategy logs "account rejected" and submits no orders. Then set correct name. | YES |
| 51 | [ ] EnableLiveTrading=true set only for the funded account session, with the human physically present at the screen | Do not enable live trading on any session where the trader is not physically monitoring the screen. This is not a technical check — it is an operational rule. Apex and Lucid both have trailing drawdown limits that can be breached in a single session. | YES |
| 52 | [ ] Apex trailing drawdown limit verified: funded account's maximum trailing drawdown limit documented | Log into Apex portal and note the funded account's specific trailing drawdown limit (typically $2,000–$3,000 for smaller accounts). This limit is account-specific. With $500/session daily loss cap and 95th-pct Monte Carlo MaxDD=$234.81, the strategy's expected drawdown is well within this limit. However, the funded account has its own rules — know them before going live. | YES |
| 53 | [ ] MaxContractsPerTrade=2 confirmed (scale-out architecture, not leverage increase) | Confirm in strategy properties. Two contracts = one contract equivalent risk (50% exits at T1=16t, 50% at T2=32t). This is NOT 2× leverage — it is the scale-out architecture. Document this distinction in the go/no-go decision doc. | YES |
| 54 | [ ] Scale-up path documented and agreed BEFORE first live session | RISK-MANAGEMENT.md: Phase 1 (0–100 live trades): 2 contracts (scale-out = 1 ct equivalent). Phase 2 (100–300 trades, Sharpe>=3.0 confirmed): 16 contracts. Phase 3 (300+ trades): 34 contracts (half-Kelly). Do not skip phases. Write this in the go/no-go doc and do not deviate. | NO — but critical for long-term risk |
| 55 | [ ] Weekly drawdown cap of $1,500 established as a personal rule (not in code) | RISK-MANAGEMENT.md Monte Carlo: weekly DD cap $1,500 triggers reduction to paper trading. This is not enforced by the code — it is a trader discipline rule. Write it in the go/no-go doc. If the account is down $1,500 in any rolling 5-day period, stop live trading and return to paper. | YES |
| 56 | [ ] Monthly drawdown cap of $1,000 established as account review trigger | RISK-MANAGEMENT.md: monthly DD cap maps to 95th-pct Monte Carlo MaxDD ($234.81) × 4 sessions buffer. If any calendar month closes with net P&L worse than -$1,000, a full signal attribution review is required before continuing. | NO — strong recommendation |
| 57 | [ ] News blackout manually extended to 30 minutes on FOMC announcement days | FINE-TUNING-RECOMMENDATIONS.md notes the 15-minute blackout may be too tight on FOMC days. Manually verify the FOMC calendar (https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm) and add a personal alert to avoid trading 13:30–14:30 ET on FOMC announcement days, regardless of strategy settings. | YES |
| 58 | [ ] NT8 RealtimeErrorHandling=StopCancelClose confirmed in strategy code | Verify in DEEP6Strategy.cs SetDefaults: `RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose`. This ensures NT8 closes all open positions if a real-time error occurs. Without it, a data disconnect with an open position could cause an unmonitored loss. | YES |

---

## Group 6: Operational

*Machine stability, connectivity, and monitoring requirements before any live session.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 59 | [ ] NT8 running on a stable machine: no recent crashes, NT8 version confirmed compatible with DEEP6 | Check NT8 application log for crashes in the last 7 days. NT8 version must support NinjaScript with the `[Display]` attribute syntax used in DEEP6 (NT8 8.0.23+ required). | YES |
| 60 | [ ] Primary internet connection stable: <20ms latency to Rithmic gateway, <0.1% packet loss | Run a latency test to the Rithmic gateway IP (rituz00100.rithmic.com for test; production gateway varies by broker). Use ping or MTR. Packet loss >0.1% during RTH will cause data gaps and missed signal bars. | YES |
| 61 | [ ] Backup internet connection available (mobile hotspot or secondary ISP) | Physical hotspot or secondary ISP confirmed available and tested. If primary internet drops during an open position, the backup must be activatable within 30 seconds. Apex/Lucid prop accounts have time-sensitive loss limits — a 5-minute internet outage with an open directional NQ position can breach a day's loss limit. | YES |
| 62 | [ ] NT8 Output window visible and being monitored during every live session | The Output window must be visible on screen (not hidden behind other windows) during all live sessions. Critical alerts (kill-switch, account whitelist failure, news blackout) are logged here. There is no email/SMS alert system in the current DEEP6Strategy implementation. | YES |
| 63 | [ ] Strategy log file being written to disk (NT8 log export configured) | In NT8, enable log export to file. This creates a persistent record of every Output line. Without this, post-session attribution analysis depends on NT8 Output window history, which clears on strategy reload. | NO — strongly recommended |
| 64 | [ ] No other strategies or automated systems running on the same account simultaneously | Confirm in NT8 Strategy Monitor that only DEEP6Strategy is active on the funded account. Conflicting orders from other strategies (or the legacy Python execution path, if running) will confuse the Position state tracking in DEEP6Strategy, potentially doubling position size. | YES |
| 65 | [ ] Machine has not been restarted with pending NT8 state (close NT8 cleanly after every session) | After each session: confirm Position=Flat, then use NT8 "Unload Strategy" before closing NT8. Do not close NT8 while positions are open — RealtimeErrorHandling=StopCancelClose handles data errors, but a hard machine shutdown may not trigger NT8's close-on-disconnect logic. | YES |
| 66 | [ ] Time synchronization: machine clock synced to NTP time source within ±1 second | Verify Windows time sync (Control Panel → Date and Time → Internet Time). The BlackoutWindowStart comparison uses DateTime.Now — if machine clock is drifted by >5 minutes, entries may fire during a blackout window. | YES |
| 67 | [ ] Session start checklist: review prior session P&L and attribution before opening a new live session | Before each live session, spend 5 minutes reviewing: yesterday's trades, signals fired, any anomalies in Output log. A degrading win rate over 3 sessions warrants pausing and investigating before continuing. | NO — discipline requirement |

---

## Group 7: Mental / Trader Readiness

*These items cannot be verified by code. They are trader decisions. Skip at your own risk.*

| # | Item | How to Verify | Blocker? |
|---|---|---|---|
| 68 | [ ] You have read and understood the go/no-go decision document | The go/no-go doc in .planning/ must be committed and re-read the morning of the first live session. Not skimmed — read in full. | YES |
| 69 | [ ] Position size (2 contracts, $10 per tick for the position) is emotionally comfortable | 2 contracts on NQ = $10/tick. A full stop-out at 20 ticks = -$200 + commissions. Confirm you can watch a $200 loss without making manual overrides, increasing size, or disabling the system mid-trade. If $200 is uncomfortable, reduce MaxContractsPerTrade to 1 until emotional calibration is established. | YES |
| 70 | [ ] You are not revenge-trading: no significant losses in prior 48 hours driving the urgency to go live | If you experienced a large loss (discretionary or other system) in the prior 48 hours, do not go live with DEEP6 today. Revenge-trading produces override behavior — disabling the kill-switch, raising size, ignoring news blackouts. Wait 48 hours after any emotionally significant loss before going live. | YES |
| 71 | [ ] You understand that the first 100 live trades are data collection, not expected P&L | The first 100 live trades validate that the backtest edge transfers to live execution. Even if the system is profitable in paper trade, live performance will differ due to real slippage, partial fills, and NQ regime changes. Treat the first 100 trades as the "confirmation run," not income. | YES |
| 72 | [ ] You have a hard stop-loss of one full month's drawdown cap before abandoning the system | If the system loses more than $1,000 in the first calendar month of live trading (Group 5, item 56), the plan is: stop live trading, return to paper, run attribution analysis, and decide within 2 weeks whether to re-enter or redesign. The plan for this scenario is agreed and written before the first live trade. | YES |
| 73 | [ ] No manual override of ATM bracket orders during live sessions | Once an ATM bracket is submitted, do not manually move the stop, cancel the bracket, or add to the position mid-trade. Manual overrides invalidate the backtested edge — the system was built on fixed stop/target geometry. If you override more than 3 times in 30 sessions, the live performance data is no longer comparable to the backtest. | YES |

---

## Final Gate Summary

All items marked **Blocker=YES** (49 items total) must be checked before flipping `EnableLiveTrading=true`.

Items marked **Blocker=NO** are strongly recommended but do not block go-live if genuinely impractical for the first session. Address all NO items within 5 live sessions.

**Three Most Critical Checklist Items:**

1. **Item 11: EnableLiveTrading=false** (Group 2) — The only protection against accidental live order submission during the paper-trade validation period. The strategy's DRY RUN log line is the final confirmation. If this line does not appear at session start, kill the strategy immediately. No exception.

2. **Item 39: Paper-trade win rate >= 75% over 30 sessions** (Group 4) — This is the empirical validation gate. The backtest win rate is 84.5%; accepting <75% would mean the live edge is materially degraded vs backtest, indicating a signal wiring problem, regime change, or data quality issue. Skipping this gate and going live with an unvalidated win rate is the single highest-probability path to account breach.

3. **Item 49: DailyLossCapDollars confirmed at $500** (Group 5) — On NQ, a single runaway session (bad news event, data feed error, system freeze with open position) can easily produce a $500–$1,000 loss before the trader can intervene. The $500 kill-switch is the last automated line of defense before the prop firm's trailing drawdown limit triggers account breach.

---

*Sources: ROADMAP.md Phase 19 success criteria, RISK-MANAGEMENT.md, DEEP6Strategy.cs SetDefaults, FINE-TUNING-RECOMMENDATIONS.md, META-OPTIMIZATION.md, PRODUCTION-CONFIG.md*
*Generated: 2026-04-15 — Round 2 Pre-Live Checklist*

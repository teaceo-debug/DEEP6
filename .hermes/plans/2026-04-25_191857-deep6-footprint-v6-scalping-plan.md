# DEEP6 Footprint V6 Scalping Plan

> For Hermes: use subagent-driven-development if/when executing this. This document is planning only.

Goal
- Create a new side-by-side NinjaTrader indicator, `DEEP6FootprintV6`, as a five-minute scalping variant of `DEEP6FootprintV5`.
- Keep the existing V5 intact.
- Reuse the strongest tools already built: footprint cell shading, absorption, exhaustion, scorer tiers/HUD, profile anchors, and optional liquidity/GEX context.
- Optimize for fast scalp execution clarity: setup, direction, armed state, trigger.
- Do not center the workflow on stop/target overlays.

Current context
- Baseline file exists: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV5.cs`
- Relevant lifecycle/state contracts already exist:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/TradeSetupState.cs`
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerResult.cs`
- The current `TradeSetupState` semantics already match the desired workflow:
  - `Setup` = context only
  - `Armed` = watch state
  - `Triggered` = actionable
  - `Invalid` / `Expired` preserve history while disabling actionability
- Prior constraints still apply:
  - new version must coexist side-by-side
  - keep long/short instantly obvious
  - avoid stop/target overlays in the newer workflow
  - preserve the gray setup marker concept

Key findings from the multi-agent review
1. Best tools to keep for a 5-minute scalp build
- Absorption: primary reversal/defense signal
- Exhaustion: confirmation, not standalone trigger
- Stacked imbalance / trap / auction context: trigger-quality confirmation tools
- Profile anchors: strong structural map for 5m scalps
- Score HUD / scorer shell: useful summary layer
- Liquidity walls: optional gate/context, not always-on default display

2. Best tools to demote or hide by default
- Mission Control panel
- Chart Trader toolbar
- Tier-3 dots
- Full-width stop/target overlays and labels
- Excess on-chart narrative text
- Liquidity wall labels unless explicitly enabled

3. Important code-level risks already present in V5
- `BarsSinceOpen` appears to be using absolute bar index rather than session-relative bar count in `OnBarUpdate`
- `PriorBar` sequencing in the scorer path may be off by one bar
- `_armedSignalBarIndex` / overlay timing may point at the current bar while marker drawing is for the previous closed bar
- Simulator/local csproj coverage does not currently include V5/V6, so NT8 compile is the real validation path unless project files are extended

Recommended product definition
- New file/class:
  - `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV6.cs`
  - `public class DEEP6FootprintV6 : Indicator`
- Purpose:
  - 5-minute execution-focused scalp view
  - signal-first, context-second
  - setup -> armed -> trigger lifecycle
  - minimal clutter
- Default visual grammar:
  - Setup = small gray marker
  - Armed = colored directional outline/marker
  - Triggered = strongest directional arrow
  - Long = one consistent green family
  - Short = one consistent red family

Recommended default V6 profile
- `ShowFootprintCells = true`
- `ShowPoc = true`
- `ShowValueArea = false`
- `ShowAbsorptionMarkers = true`
- `ShowExhaustionMarkers = true`
- `ShowProfileAnchors = true`
- `ShowPriorDayLevels = true`
- `ShowNakedPocs = false`
- `ShowCompositeVA = false`
- `ShowLiquidityWalls = false`
- `ShowChartTrader = false`
- `ShowMissionControl = false`
- `ShowScoreHud = true`
- `ShowTier1Overlay = true`, but only after simplifying it to direction/trigger emphasis
- `ShowTier3Dots = false`
- `ArmedSignalValidBars = 2` or `3`

Design logic for the five-minute scalp workflow

A. Setup families
1. Reversal scalp
- Must occur near a structural level:
  - prior-day POC / VAH / VAL / PDH / PDL / prior-week POC / fresh nPOC
  - optional liquidity wall
  - optional mapped GEX wall/flip when available
- Must show rejection evidence:
  - absorption
  - exhaustion
  - auction completion/rejection
  - trap/false breakout evidence

2. Pullback continuation scalp
- Must align with local trend context
- Must occur on pullback/retest into structure
- Confirmation stack should prefer:
  - stacked imbalance
  - delta continuation / sweep / reclaim
  - auction / POC migration behavior

B. Setup -> Armed -> Triggered rules
1. Setup
- Context only
- Draw gray setup marker
- Requires at least one meaningful order-flow event near a structural level

2. Armed
- Promote only if all are true:
  - level proximity is acceptable
  - direction is clear
  - no immediate opposing level/wall directly overhead/underfoot
  - bar quality is acceptable for a scalp
- `SetupState = Armed`
- Use colored directional marker, not stop/target rails

3. Triggered
- Trigger on confirmation bar rather than immediate signal-bar assumption
- Example trigger model:
  - long: next bar confirms reclaim / close above trigger threshold
  - short: mirror logic
- Draw strongest directional arrow here
- Keep chart focused on entry state, not plan rails

C. 5-minute-specific filters to add
- Time-of-day windows based on clock, not raw bar counts
  - emphasize open drive and later afternoon opportunity windows
  - suppress midday chop by actual time, not 1m-specific bar assumptions
- Trend filter
  - simple 5m trend slope or equivalent higher-order bias gate
- Distance-to-level gate
  - reward signals near structural levels
  - reject “mid-air” triggers
- Cooldown
  - per-direction and per-level cooldown to avoid churn
- Bar-quality filter
  - reject too-wide chase bars
  - reject dead/no-range bars
  - reject triggers already extended away from level

Implementation order

Phase 1: clean side-by-side fork
Files
- Create: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV6.cs`

Steps
1. Copy V5 to V6 as a full fork.
2. Rename class/file/display name together.
3. Do not touch V5.
4. Do not create an inheritance wrapper; V5 is too monolithic/private for that to be the clean path.

Phase 2: deliver the first useful scalp version with minimal risk
Primary hotspots in `DEEP6FootprintV6.cs`
- `OnStateChange()` defaults: around V5 lines 200-273
- `OnRender()`: around V5 lines 827-959
- `RenderMissionControl()`: around V5 lines 1182-1248
- `IsArmedSignalValid()`: around V5 lines 1510-1515
- `RenderTier1Overlay()`: around V5 lines 1517-1622
- `DrawScorerTierMarker()`: around V5 lines 1980-2097
- properties block: around V5 lines 2145-2376

Minimal first slice
1. V6 identity + defaults
2. Mission Control off by default
3. Chart Trader off by default
4. Tier-3 dots off
5. Shorten active-signal lifetime
6. Simplify Tier-1 overlay so it no longer centers stop/target lines
7. Preserve/strengthen directional marker clarity

Phase 3: explicit scalp lifecycle behavior
Files
- Modify: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV6.cs`
- Reference existing contracts in:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/TradeSetupState.cs`
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ScorerResult.cs`

Steps
1. Use `TradeSetupState` directly in the V6 chart behavior.
2. Restore a clear lifecycle:
  - gray setup marker
  - directional armed marker
  - trigger arrow
3. Keep invalid/expired states visually downgraded rather than removed.
4. Avoid reintroducing stop/target overlays as default chart grammar.

Phase 4: five-minute-specific signal quality upgrades
Files
- Modify: `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV6.cs`
- Review / optionally modify:
  - `ninjatrader/Custom/AddOns/DEEP6/Scoring/ConfluenceScorer.cs`
  - `ninjatrader/Custom/AddOns/DEEP6/Registry/SessionContext.cs`

Steps
1. Fix session-relative timing inputs before relying on 5m windows.
2. Replace bar-count assumptions with actual session/time logic where needed.
3. Add distance-to-level and cooldown logic in V6 before rewriting scorer math.
4. Only after V6 behavior is stable, decide whether `ConfluenceScorer` needs a dedicated scalp profile.

Phase 5: optional structural-context upgrades
Possible files
- `ninjatrader/Custom/AddOns/DEEP6/Bridge/GexSharedState.cs`
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6GexLevels.cs`
- `ninjatrader/Custom/Indicators/DEEP6/DEEP6FootprintV6.cs`

Use
- GEX as structural map / context only
- Liquidity walls as optional context/gate only
- Do not let either become a noisy always-on execution overlay by default

Validation plan

NT8 compile / smoke test
1. Deploy V6 to NinjaTrader side-by-side with V5.
2. Compile in NT8.
3. Confirm both V5 and V6 appear separately in the indicator list.
4. Add V6 to a 5-minute NQ chart.
5. Verify:
- no compile collision with V5
- no render exceptions
- setup/armed/trigger visuals are clear
- no unwanted stop/target overlays by default
- score HUD still updates
- profile anchors still render correctly

Behavioral checks
- active signals do not linger too long
- long/short direction is obvious without reading text
- midpoint/mid-air signals are visually de-emphasized or filtered
- reversal and continuation setups both still show cleanly

Risks / tradeoffs
- A pure visual cleanup is easy and high-value, but it will not fully solve scalp quality without timing/filter fixes.
- Touching shared scorer internals too early risks strategy drift.
- The fastest safe path is:
  1. fork V6
  2. simplify display and lifecycle visuals
  3. then fix 5m timing/session semantics
  4. then add level-distance/cooldown filters

Open questions before execution
- Should V6 be explicitly named “Scalp” in the class/file, or should the UI label carry the scalp designation while keeping the class as `DEEP6FootprintV6`?
- For triggers, should confirmation be next-bar close based, intrabar reclaim based, or configurable?
- Should liquidity walls be completely off by default, or shown only when within a close distance of current price?
- Should GEX context be wired into V6 immediately, or deferred until the 5m lifecycle is stable?

Execution recommendation
- Start with a clean `DEEP6FootprintV6` fork focused on display/lifecycle simplification and 5-minute defaults.
- Do not rewrite the whole scorer in slice one.
- First make the chart feel like a real scalp tool.
- Then tighten the signal engine with session-correct timing, distance-to-level gating, and cooldown behavior.

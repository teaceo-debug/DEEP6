# DEEP6 At-a-Glance Bias Engine Design

Status: revised after user correction.

This document supersedes the earlier LVN-centric bias draft.
The user confirmed the LVN Pine script was the wrong input for the bias engine.
The replacement source concept is the provided `SPX Bias Unified v3 -- Clear Directional Bias Rewrite` script.

Core decision:
- Remove the LVN/POC script as a primary bias-engine source.
- Replace it with the SPX Bias Unified model as the top-down directional bias layer.
- Keep TradeGEX as the options-map layer.
- Keep DEEP6 footprint/order-flow as the setup/trigger layer.

So the stack becomes:
1. TradeGEX = map
2. SPX Bias Unified model = directional bias state
3. DEEP6 footprint/order flow = trigger confirmation
4. NT8/TV = rendering surfaces

---

## 1. Product goal

Let the trader glance at the chart and immediately know:
- likely long/short bias for NQ
- whether that bias is strong, weak, or neutral
- where the important options levels are
- whether a live setup aligns with the bias
- whether the engine says trade, caution, or no-trade

This engine must separate:
- bias from signal
- map from trigger
- directional lean from execution permission

That separation is one of the strongest ideas in the replacement Pine script and should be preserved.

---

## 2. New system hierarchy

Use this hierarchy everywhere in DEEP6:

### Layer A: Map
Question: where is price relative to dealer/options structure?

Owned by:
- TradeGEX observer/adapter
- existing GEX structures in DEEP6 as fallback

Inputs:
- call wall
- put wall
- gamma flip / zero gamma
- HVL / magnet / key gamma nodes
- nearest above / below levels
- current price location versus those levels
- NQ / ES / QQQ / SPY alignment around those structures

Output:
- structural posture
- nearest important support
- nearest important resistance
- regime framing for the day/session

### Layer B: Bias
Question: does the broader tape favor long or short continuation right now?

Owned by:
- new SPX-Bias-style engine

Inputs derived from the replacement script:
- signed bias score (-9 to +9)
- hysteresis bias state machine
- setup quality (0 to 5)
- confidence percentage
- flow direction score
- kill switch / caution state
- session quality / time-of-day posture
- macro/intermarket/internals alignment

Output:
- STRONG BULL
- LEAN BULL
- NEUTRAL
- LEAN BEAR
- STRONG BEAR

And separately:
- GO
- CAUTION
- STOP

### Layer C: Setup
Question: is price doing something useful at structure?

Owned by:
- DEEP6 footprint / setup state machine

Inputs:
- absorption near mapped support/resistance
- exhaustion into mapped support/resistance
- retest-hold / reject-under / reclaim behavior
- imbalance / delta agreement
- bar-close confirmation around the level

Output:
- long candidate
- short candidate
- no setup

### Layer D: Trigger
Question: is there an executable confirmation right now?

Owned by:
- DEEP6 execution-side setup/trigger state machine

Inputs:
- break of setup bar high/low
- reclaim hold / failed retest / rejection close
- delta/order-flow agreement
- setup still aligned with Bias + Map

Output:
- triggered long
- triggered short
- armed but not triggered
- invalidated

### Layer E: Management / No-Trade
Question: should we hold, scale, avoid, or shut off entries?

Owned by:
- confluence / risk layer

Inputs:
- kill switch from Bias layer
- map proximity to wall/flip/HVL
- session window
- event day state
- trend vs chop state

Output:
- GO
- CAUTION
- STOP
- long only
- short only
- no-trade

---

## 3. How the replacement Pine script should be interpreted

The replacement script is not just another signal.
It is a full directional-bias dashboard with explicit state separation.
That makes it ideal for the DEEP6 bias layer.

The most important concepts to preserve are:

### 3.1 Signed bias score
The Pine script uses a signed score from -9 to +9.
That is much better than a simple bullish-count / bearish-count display.

Recommended DEEP6 mapping:
- +7 to +9 = extreme bullish pressure
- +5 to +6 = strong bullish bias
- +3 to +4 = lean bullish
- -2 to +2 = neutral / mixed
- -3 to -4 = lean bearish
- -5 to -6 = strong bearish bias
- -7 to -9 = extreme bearish pressure

### 3.2 Hysteresis state machine
This is critical.
The bias display should not flip every bar just because the raw score wiggles.

Recommended preserved states:
- +2 = STRONG BULL
- +1 = LEAN BULL
-  0 = NEUTRAL
- -1 = LEAN BEAR
- -2 = STRONG BEAR

Use the same concept:
- a stronger threshold to enter a bias state
- a softer threshold to degrade or neutralize it

This avoids visual noise and keeps the trader from chasing tiny flips.

### 3.3 Setup quality separate from bias direction
Also critical.
The script explicitly separates:
- directional bias
from
- trade quality / size quality

That should remain intact in DEEP6.

Recommended interpretation:
- bias direction answers: which side has the edge?
- setup quality answers: is this a high-quality place to trade it?

### 3.4 Kill switch affects entries, not bias display
This is one of the best ideas in the script.

The system should still tell the trader:
- "LEAN BULL"
or
- "STRONG BEAR"

Even when the entry state is:
- STOP
- EVENT DAY
- CHOP DETECTED
- PAST CUTOFF

That way the user still understands market posture even when the system says not to trade.

---

## 4. Replace the prior LVN-centric bias inputs with these bias domains

The corrected bias engine should be built from these major domains:

### 4.1 ICT / session-structure direction
From the script:
- manipulation window
- flux anchor
- reversal bands
- X / A / M / D phase
- true day open
- prior-day-close strength
- NQ/ES divergence / alignment

Interpretation:
This is the session-structure and intraday narrative layer.
It helps answer whether the session favors continuation, reversal, or caution.

### 4.2 Macro / intermarket direction
From the script:
- ZN direction
- DXY direction
- VIX term structure
- RTY participation
- NQ vs ES spread

Interpretation:
This is the external confirmation layer.
It helps answer whether the risk complex is supporting or fighting the move.

### 4.3 Flow direction
From the script:
- CVD slope
- TICK thrust
- price vs VWAP

Interpretation:
This is the intraday directional pressure layer.
It is not the final trigger, but it should heavily influence directional confidence.

### 4.4 MA / HTF alignment
From the script:
- weekly / daily / intraday alignment
- stacked MA bias counts
- HTF bias summary

Interpretation:
This acts as a higher-timeframe trend filter and prevents shorting strong trend days too casually or buying into multi-timeframe weakness too casually.

### 4.5 Market internals
From the script:
- VOLD
- A/D
- TICK
- MFI
- RVOL

Interpretation:
This provides breadth/participation confirmation and helps determine whether a directional bias deserves size.

### 4.6 Session quality / kill-switch context
From the script:
- lunch / avoid windows
- prime windows
- event days
- chop detection
- cutoff windows
- high-volatility mixed-state shutdowns

Interpretation:
This is the permission layer.
It should not erase bias, but it should reduce or block entries.

---

## 5. Recommended DEEP6 bias formula

Keep the Pine model structure.

### 5.1 Raw components
Build three directional sub-scores:

1. ICT / session direction
Range target: -4 to +4

2. Macro / intermarket direction
Range target: -3 to +3

3. Flow direction
Range target: -2 to +2

Then sum them:
- BiasScore = ICT + Macro + Flow
- clamp to [-9, +9]

This is strong because it preserves:
- top-down session narrative
- external market confirmation
- live intraday directional pressure

### 5.2 Confidence
Bias confidence should be derived from absolute score magnitude, but not only that.
Recommended:
- base confidence from abs(BiasScore) / 9
- then reduce confidence if:
  - components disagree sharply
  - price is pinned near gamma flip
  - kill switch is active
  - session is in avoid window

### 5.3 Setup quality
Use a separate 0-5 scale, just like the script.
Recommended components:
- component agreement
- RVOL / participation
- session quality
- proximity to mapped level
- order-flow cleanliness

Interpretation:
- 0-1 = poor
- 2 = weak
- 3 = tradeable
- 4 = strong
- 5 = excellent

### 5.4 Entry permission state
Use a separate traffic-light state:
- GO
- CAUTION
- STOP

Recommended trigger for STOP:
- event day + strict mode
- hard chop detection
- past cutoff
- severe intermarket divergence
- mixed high-vol regime with low directional conviction

---

## 6. How this should combine with TradeGEX

TradeGEX remains the map.
The replacement Pine model becomes the bias/risk posture engine.

So:

TradeGEX tells us:
- where dealer structure matters
- whether we are near walls or flip
- whether the map is pinned, balanced, or expansion-prone

SPX-Bias-style engine tells us:
- whether the session/tape/macro context favors long or short
- whether the bias is strong enough to trust
- whether entries are permitted right now

DEEP6 footprint tells us:
- whether there is an actual executable setup at the mapped level

This is the exact separation you want.

---

## 7. Revised chart output model

The chart should now show these at a glance:

### 7.1 Bias banner
Top-left panel:
- BIAS: STRONG BULL / LEAN BULL / NEUTRAL / LEAN BEAR / STRONG BEAR
- SCORE: signed score
- CONF: 0-100%
- MODE: GO / CAUTION / STOP
- SESSION: A+ OPEN / MID-AM / LUNCH / POWER / AVOID

### 7.2 Map lines
Still show:
- call wall
- put wall
- gamma flip
- HVL / magnet
- maybe next above / below level

### 7.3 Setup markers
Still preserve:
- legacy gray marker for setup candidate

### 7.4 Trigger markers
Show only when setup aligns with both:
- map
- bias state

### 7.5 Warning state
Show separately when:
- EVENT DAY
- CHOP DETECTED
- PAST CUTOFF
- BIAS INVALIDATED

Again: warning affects entry, not whether bias is shown.

---

## 8. Remove LVN as a core bias-engine dependency

Because the user corrected the Pine source, LVN should no longer be a primary bias-engine pillar.

New rule:
- LVN/POC logic is optional or secondary context in the setup/trigger layer.
- It should not be one of the primary top-level bias domains.

That means:
- remove LVN/POC from the core bias-score computation
- do not make directional bias depend on LVN acceptance/rejection
- if LVN remains in DEEP6, keep it as a lower-level setup enhancer only

In plain English:
- the old draft used LVN to help decide market bias
- the corrected draft should use session/macro/flow/intermarket structure instead

---

## 9. Suggested Python module layout

Add a dedicated bias engine modeled on the replacement script.

Suggested files:
- `deep6/engines/session_bias.py`
- `deep6/engines/intermarket_bias.py`
- `deep6/engines/flow_bias.py`
- `deep6/engines/kill_switch.py`
- `deep6/engines/market_bias_engine.py`

Suggested dataclasses:

```python
@dataclass(slots=True)
class BiasComponentState:
    ict_score: int
    macro_score: int
    flow_score: int
    total_score: int
    confidence: float
    setup_quality: int
    bias_state: int   # -2..+2
    mode: str         # GO / CAUTION / STOP
    reason: str
```

```python
@dataclass(slots=True)
class MarketBiasSnapshot:
    symbol: str
    asof_ts: float
    bias_label: str
    bias_state: int
    bias_score: int
    confidence: float
    setup_quality: int
    mode: str
    mode_reason: str
    session_label: str
    xamd_phase: str
    intermarket_alignment: str
    tradegex_regime: str | None
    nearest_support: float | None
    nearest_resistance: float | None
    meta: dict = field(default_factory=dict)
```

Then combine this snapshot with TradeGEX map output before publishing to NT8.

---

## 10. Recommended implementation order

1. Replace the old LVN-centric design assumption in planning and scoring docs.
2. Implement the signed-bias engine first.
3. Implement hysteresis state machine second.
4. Implement kill-switch / caution-state logic third.
5. Connect TradeGEX map levels into the bias snapshot.
6. Only then reconnect footprint setup/trigger logic.
7. Publish the merged chart payload to NT8.

This order matters because:
- the trader first needs to know the directional posture
- then where the important levels are
- then whether a setup/trigger exists at those levels

---

## 11. Final design rule

The corrected DEEP6 bias engine should answer these questions in order:

1. Which side has the edge?  -> SPX-Bias-style signed bias engine
2. Where does that edge matter? -> TradeGEX map
3. Is price actually reacting there? -> DEEP6 setup logic
4. Is the trade currently allowed? -> kill switch / caution logic
5. Is there a real trigger? -> DEEP6 trigger logic

That is the correct replacement for the earlier LVN-first draft.

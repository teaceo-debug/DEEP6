# Step 7: Output — Output Format

## Overview

Every decision cycle produces a structured output. The output is the system's complete state at a point in time: regime, bias score, component breakdown, level map, active setup, conviction, risk gate status, trade recommendation, narrative, and alerts. Nothing is omitted. Nothing is implied.

The output serves two consumers simultaneously: the human trader reading the dashboard and the Python FastAPI backend processing it programmatically. The format must satisfy both.

Decision cycles run every 5-15 minutes during active market hours. Significant event triggers (wall shift, regime transition, new sweep cascade, iceberg detection) produce immediate outputs outside the scheduled cycle.

---

## Full Output Template

```
=== OPTIONS BIAS ENGINE OUTPUT ===
timestamp: 2026-05-15T10:47:23.441Z
session_time: 10:47 AM ET  [MORNING SESSION]
cycle_type: SCHEDULED  [or: EVENT_TRIGGERED: iceberg_detected]
cycle_number: 8  [8th output of the session]

--- REGIME ---
regime: C
regime_name: POSITIVE GAMMA — AT PUT WALL
total_gex: +$3.2B
gamma_flip: 20,840
spot: 20,847
flip_distance: +7 pts  [spot is 7 pts ABOVE flip — positive gamma confirmed]
call_wall: 21,200  [GEX: +$1.8B]
put_wall: 20,850  [GEX: -$2.1B]
hvl: 21,020  [High Volume Level — gravitational center]
expected_move_high: 21,150
expected_move_low: 20,720
0dte_expiry: 21,000 call / 20,900 put  [dominant 0DTE strikes]
regime_stability: STABLE  [no flip crossings in last 30 min, walls unchanged]

--- BIAS ---
directional_score: +68
bias_label: BULLISH
score_components:
  structural:  +72  [positive gamma, at put wall, call wall 353 pts away]
  flow:        +61  [net call premium $4.2M last 15 min, 2 call sweeps]
  dark:        +45  [dark pool net buying $12M last 2 hours, neutral-bullish]
  dom:         +80  [iceberg bids at 20,850, defense score 87/100]
  derived:     +58  [vanna tailwind active, VIX -0.8 pts, charm neutral]

--- LEVEL MAP ---
[levels above spot]
  21,200  ****  CALL WALL  [GEX: +$1.8B, defense: 34/100 — moderate]
  21,150  ***   EXPECTED MOVE HIGH  [statistical boundary]
  21,100  **    0DTE call cluster  [OI: 12,400 contracts]
  21,020  ****  HVL  [gravitational center, high OI concentration]
  20,950  **    minor call cluster  [OI: 4,200 contracts]

  >>> SPOT: 20,847 <<<

[levels below spot]
  20,850  *****  PUT WALL  [GEX: -$2.1B, defense: 87/100 — FORTRESS]
  20,840  ----   GAMMA FLIP  [7 pts below spot]
  20,720  ***    EXPECTED MOVE LOW  [statistical boundary]
  20,700  **     put cluster  [OI: 8,100 contracts]
  20,600  ***    major put wall secondary  [GEX: -$800M]

--- ACTIVE SETUP ---
setup: SETUP 1 — WALL BOUNCE (PUT WALL)
status: ENTRY CONDITIONS MET
conditions_met:
  [x] Regime C confirmed (positive gamma, at put wall)
  [x] Defense score 87/100 (threshold: 60)
  [x] Iceberg bids detected at 20,850 (active 4 min 12 sec)
  [x] Aggression imbalance +52 (buyers aggressive at the wall)
  [x] Flow bullish (call sweeps, net call premium positive)
conditions_pending:
  [ ] none — all conditions met
entry_zone: 20,847-20,855
stop: 20,825  [15 pts below put wall, below gamma flip]
target_1: 21,020  [HVL, +173 pts]
target_2: 21,150  [expected move high, +303 pts]
r_r_to_target_1: 7.9:1
r_r_to_target_2: 13.8:1

--- CONVICTION ---
dimension_votes:
  structural:  BULLISH  [Regime C, put wall defense]
  flow:        BULLISH  [call sweeps, net call premium]
  dark:        BULLISH  [net buying, neutral-bullish]
  dom:         BULLISH  [iceberg at put wall, high defense]
  derived:     BULLISH  [vanna tailwind]
conviction: 5/5
multipliers: ICEBERG (+1 already included in 5/5 count)
conviction_label: MAXIMUM

--- RISK GATES ---
GATE 1: REGIME CLARITY          [PASS]  Regime C stable, no flip crossings
GATE 2: MINIMUM CONVICTION      [PASS]  5/5 dimensions aligned
GATE 3: FLOW IS ALIVE           [PASS]  net_premium=$4.2M, sweeps=2 (15 min)
GATE 4: NO EVENT WITHIN 30 MIN  [PASS]  next_event=CPI tomorrow 8:30 AM
GATE 5: NOT IN FIRST 5 MIN      [PASS]  10:47 AM ET
GATE 6: NOT FIGHTING REGIME     [PASS]  long at put wall in Regime C — optimal
GATE 7: DATA FRESHNESS          [PASS]  all sources fresh (FA:47s, MA:23s, UW:112s, RIT:0.3s)
GATE 8: CONSECUTIVE LOSS LIMIT  [PASS]  consecutive_losses=0, session_pnl=+18.5 pts

OVERALL: TRADE ALLOWED

--- TRADE RECOMMENDATION ---
action: LONG
instrument: NQ (front month)
entry: 20,847-20,855  [current price or limit at 20,850]
stop: 20,825  [22-25 pts risk]
target_1: 21,020  [take 50% here]
target_2: 21,150  [trail remaining 50%]
size: 1.5x base  [conviction 5/5 × regime C 1.10x × setup 1 1.00x = 1.10x, rounded to nearest]
size_note: Apply 2% account risk rule. At 25 pt stop, max 2 NQ per $50K account.
scaling: Take 50% at 21,020. Move stop to breakeven. Trail remaining to 21,150.

--- NARRATIVE ---
Regime C established with spot at 20,847, sitting 7 points above the gamma flip and directly at the put wall (20,850). The put wall is a fortress — defense score 87/100, iceberg bids active for over 4 minutes, and buyer aggression at +52 confirms the wall is being tested and held. All five dimensions are bullish: structural (positive gamma, put wall mechanics), flow (two call sweeps, $4.2M net call premium), dark (net buying), DOM (iceberg + absorption), and derived (vanna tailwind from VIX declining 0.8 points). This is a 5/5 conviction Setup 1 — the highest quality trade the system can identify. The path of least resistance is toward HVL at 21,020 (+173 pts) and potentially the expected move high at 21,150. Key risk: if the put wall breaks (spot closes below 20,840 for 2+ minutes), the gamma flip is immediately below and Regime E cascade begins. Stop at 20,825 captures this risk.

--- ALERTS ---
[NEW] Iceberg bids detected at 20,850 — active 4 min 12 sec, estimated 340 contracts absorbed
[NEW] Defense score upgraded from 71 to 87 since last cycle (reload rate increased)
[ONGOING] Vanna tailwind active since 10:15 AM (VIX -0.8 pts from open)
[CLEARED] Previous alert: "call wall at 21,200 showing thin defense" — defense score now 34 (moderate, not thin)

=== END OUTPUT ===
```

---

## Field Definitions

### Header fields

**timestamp:** ISO 8601 UTC timestamp of output generation.

**session_time:** Human-readable ET time with session context label (OPENING NOISE / MORNING SESSION / MIDDAY / AFTERNOON SESSION / CLOSING).

**cycle_type:** SCHEDULED (routine 5-15 min cycle) or EVENT_TRIGGERED with the triggering event name.

**cycle_number:** Count of outputs this session. Useful for tracking how many times the system has evaluated conditions today.

### Regime fields

**regime:** Single letter A-G.

**regime_name:** Full descriptive name.

**total_gex:** Net GEX across all strikes and expirations. Sign determines positive/negative gamma. Magnitude indicates strength.

**gamma_flip:** The price level where total GEX changes sign. The most important single number in the system.

**spot:** Current NQ price.

**flip_distance:** Spot minus flip level. Positive = above flip (positive gamma). Negative = below flip (negative gamma). The sign and magnitude both matter.

**call_wall / put_wall:** The strike with the highest magnitude positive/negative GEX. The primary structural levels.

**hvl:** High Volume Level. The price with the highest total OI concentration. Acts as a gravitational center.

**expected_move_high / expected_move_low:** The statistical expected move boundaries derived from ATM implied volatility. Computed as: spot ± (ATM_IV × spot × sqrt(DTE/365)).

**0dte_expiry:** The dominant 0DTE strikes (highest OI). These are the most active gamma levels on expiration days.

**regime_stability:** STABLE (no flip crossings in 30 min, walls unchanged) / TRANSITIONING (1-2 crossings) / UNSTABLE (3+ crossings or walls shifting rapidly).

### Bias fields

**directional_score:** -100 to +100. The weighted average of the five component scores.

**bias_label:** Text label for the score range:
- +80 to +100: STRONG BULLISH
- +50 to +79: BULLISH
- +20 to +49: LEAN BULLISH
- -19 to +19: NEUTRAL
- -49 to -20: LEAN BEARISH
- -79 to -50: BEARISH
- -100 to -80: STRONG BEARISH

**score_components:** Each of the five dimensions scored -100 to +100. The structural component is the anchor. The other four confirm or contradict it.

### Level map fields

**Star ratings (1-5):**
- 5 stars: Primary wall (call wall or put wall) with high defense score (>70)
- 4 stars: HVL, gamma flip, or primary wall with moderate defense (40-70)
- 3 stars: Expected move boundaries, secondary walls, major OI clusters
- 2 stars: Minor OI clusters, 0DTE strikes
- 1 star: Weak levels, low OI, low defense

**Defense score:** Shown for levels where DOM data is available. Computed per order-book/level-defense-scoring.md.

**GEX:** Dollar GEX at the level. Positive = call gamma (ceiling). Negative = put gamma (floor).

### Active setup fields

**setup:** The setup number and name from step2-setups/.

**status:** ENTRY CONDITIONS MET / PENDING (list pending conditions) / MONITORING (watching for setup to develop).

**conditions_met / conditions_pending:** Explicit checklist. Every condition is listed. Nothing is assumed.

**entry_zone:** Price range for entry. Not a single price — a zone, because the market doesn't always give you the exact price.

**stop:** The logical stop level. Always at a structural level (below put wall, above call wall, at gamma flip).

**target_1 / target_2:** First and second profit targets. Target 1 is always the closer, more reliable level. Target 2 is the extended target if the move continues.

**r_r:** Risk-to-reward ratio. Calculated as (target - entry) / (entry - stop). Must be > 2:1 for any trade.

### Conviction fields

**dimension_votes:** Each dimension's directional vote. BULLISH / BEARISH / NEUTRAL.

**conviction:** X/5 count.

**multipliers:** Any special multipliers applied (iceberg, absorption). If the iceberg exception from kill-switches.md Gate 2 was applied, note it here.

**conviction_label:** MAXIMUM (5/5) / HIGH (4/5) / MODERATE (3/5) / LOW (2/5, no trade) / NONE.

### Risk gate fields

All eight gates listed with PASS/FAIL and a brief reason. The reason is critical for post-session review — it tells you WHY a gate passed or failed, not just that it did.

**OVERALL:** TRADE ALLOWED (all 8 pass) or TRADE BLOCKED (any fail, with the failing gate identified).

### Trade recommendation fields

Only present when OVERALL = TRADE ALLOWED and an active setup has all conditions met.

**action:** LONG / SHORT / CLOSE (for closing an existing position) / NONE (no trade recommended despite gates passing — e.g., no active setup).

**instrument:** NQ (front month) or MNQ for smaller accounts.

**entry:** Price or zone. If a limit order, specify the limit price. If market, say "market."

**stop / target_1 / target_2:** Specific NQ prices, not vague descriptions.

**size:** The output of the position-sizing.md calculation, expressed as a multiplier of base AND as a specific contract count if base is configured.

**size_note:** Any relevant sizing context (2% rule application, midday reduction, etc.).

**scaling:** The scaling-in/out protocol for this specific trade.

### Narrative

3-5 sentences. See narrative-guidelines.md for full guidance on how to write this section.

### Alerts

Changes since the last output cycle. Three categories:
- [NEW]: Something that wasn't present in the last output
- [ONGOING]: Something that was present and continues
- [CLEARED]: Something that was present and is now resolved

Alerts are the most time-sensitive part of the output. They tell the trader what changed, not what the current state is (the rest of the output covers current state).

---

## Output Frequency

### Scheduled cycles

Every 5 minutes during active market hours (9:35 AM - 3:45 PM ET). The 5-minute interval balances freshness with noise — shorter intervals produce too many outputs with minimal changes, longer intervals miss important state changes.

During midday (11:30 AM - 1:30 PM ET), the interval can extend to 10-15 minutes if no significant changes are occurring. Low-flow periods don't require frequent updates.

### Event-triggered outputs

Produce an immediate output (outside the scheduled cycle) when any of the following occur:

- Regime change (spot crosses gamma flip, or regime letter changes)
- Wall shift > 25 NQ points (call wall or put wall moves significantly)
- New iceberg detected at a GEX level
- Sweep cascade triggered (3+ sweeps in same direction within 10 minutes)
- Dark pool print > $50M in a single transaction
- Conviction changes by 2+ levels (e.g., 3/5 → 5/5 or 5/5 → 2/5)
- Any kill switch gate changes from PASS to FAIL or FAIL to PASS
- VIX moves > 1.0 point in 15 minutes (vanna flow trigger)

Event-triggered outputs include `cycle_type: EVENT_TRIGGERED: [event_name]` in the header.

### Compact vs full output

**Full output:** Used for regime changes, new setups, and the first output of the session. Contains all fields as shown in the template above.

**Compact output:** Used for routine scheduled cycles when no significant changes have occurred. Contains:
- Header (timestamp, session_time, cycle_type, cycle_number)
- Bias score and label (just the number and label, no component breakdown)
- Changes since last cycle (delta only)
- Risk gate summary (PASS/FAIL count, any changes)
- Alerts section

Compact output is approximately 20% the size of a full output. Use it when the state is stable and the trader needs a quick status check, not a full re-evaluation.

---

## JSON Schema

For programmatic consumption by the FastAPI backend:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["timestamp", "regime", "bias", "conviction", "gates", "recommendation"],
  "properties": {
    "timestamp": {"type": "string", "format": "date-time"},
    "session_time_et": {"type": "string"},
    "cycle_type": {"type": "string", "enum": ["SCHEDULED", "EVENT_TRIGGERED"]},
    "cycle_number": {"type": "integer"},
    "regime": {
      "type": "object",
      "properties": {
        "letter": {"type": "string", "enum": ["A","B","C","D","E","F","G"]},
        "name": {"type": "string"},
        "total_gex_billions": {"type": "number"},
        "gamma_flip": {"type": "number"},
        "spot": {"type": "number"},
        "flip_distance_pts": {"type": "number"},
        "call_wall": {"type": "number"},
        "put_wall": {"type": "number"},
        "hvl": {"type": "number"},
        "em_high": {"type": "number"},
        "em_low": {"type": "number"},
        "stability": {"type": "string", "enum": ["STABLE","TRANSITIONING","UNSTABLE"]}
      }
    },
    "bias": {
      "type": "object",
      "properties": {
        "score": {"type": "number", "minimum": -100, "maximum": 100},
        "label": {"type": "string"},
        "components": {
          "type": "object",
          "properties": {
            "structural": {"type": "number"},
            "flow": {"type": "number"},
            "dark": {"type": "number"},
            "dom": {"type": "number"},
            "derived": {"type": "number"}
          }
        }
      }
    },
    "levels": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "price": {"type": "number"},
          "type": {"type": "string"},
          "stars": {"type": "integer", "minimum": 1, "maximum": 5},
          "gex_billions": {"type": "number"},
          "defense_score": {"type": "number"},
          "side": {"type": "string", "enum": ["above", "below", "spot"]}
        }
      }
    },
    "active_setup": {
      "type": ["object", "null"],
      "properties": {
        "number": {"type": "integer"},
        "name": {"type": "string"},
        "status": {"type": "string"},
        "entry_low": {"type": "number"},
        "entry_high": {"type": "number"},
        "stop": {"type": "number"},
        "target_1": {"type": "number"},
        "target_2": {"type": "number"},
        "rr_to_t1": {"type": "number"},
        "rr_to_t2": {"type": "number"}
      }
    },
    "conviction": {
      "type": "object",
      "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 5},
        "label": {"type": "string"},
        "votes": {
          "type": "object",
          "properties": {
            "structural": {"type": "string"},
            "flow": {"type": "string"},
            "dark": {"type": "string"},
            "dom": {"type": "string"},
            "derived": {"type": "string"}
          }
        }
      }
    },
    "gates": {
      "type": "object",
      "properties": {
        "regime_clarity": {"type": "boolean"},
        "minimum_conviction": {"type": "boolean"},
        "flow_alive": {"type": "boolean"},
        "no_event_30min": {"type": "boolean"},
        "not_first_5min": {"type": "boolean"},
        "not_fighting_regime": {"type": "boolean"},
        "data_freshness": {"type": "boolean"},
        "consecutive_loss_limit": {"type": "boolean"},
        "overall": {"type": "boolean"}
      }
    },
    "recommendation": {
      "type": "object",
      "properties": {
        "action": {"type": "string", "enum": ["LONG","SHORT","CLOSE","NONE"]},
        "entry": {"type": "number"},
        "stop": {"type": "number"},
        "target_1": {"type": "number"},
        "target_2": {"type": "number"},
        "size_multiplier": {"type": "number"},
        "size_contracts": {"type": "number"}
      }
    },
    "narrative": {"type": "string"},
    "alerts": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "status": {"type": "string", "enum": ["NEW","ONGOING","CLEARED"]},
          "message": {"type": "string"},
          "timestamp": {"type": "string", "format": "date-time"}
        }
      }
    }
  }
}
```

---

## Historical Logging

Every output is logged to a session file with the following structure:

```
logs/sessions/YYYY-MM-DD/
  session_log.jsonl          # One JSON object per output, newline-delimited
  trades.jsonl               # One JSON object per trade taken
  regime_transitions.jsonl   # One JSON object per regime change
  alerts.jsonl               # One JSON object per alert (new/cleared)
```

The session log is the primary data source for the weekly review (session-limits.md). It enables:
- Replay of the session's state at any point in time
- Correlation analysis between bias scores and subsequent price moves
- Win rate calculation by regime, setup, time of day
- Identification of which signals were most predictive on a given day

Retention: Keep 90 days of session logs. Archive older logs to cold storage.

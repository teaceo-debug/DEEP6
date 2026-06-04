# A+ Setup — Triple Confluence for Maximum Conviction

Most LVN trades are B or C grade. They have a structural level and maybe one confirming signal. They work sometimes. The A+ setup is different. It requires all three signal layers to align at the same price level, at the same time. When that happens, you have the highest signal-to-noise ratio available from order flow data.

Documented across 50+ NQ trades: 62% win rate, 2.4 average R:R. No other single-layer or two-layer configuration comes close.

---

## Definition

An A+ setup requires ALL THREE pillars to align at the same price level. Not two of three. Not "close enough." All three.

The three pillars are:
1. A Volume Profile level (the WHERE)
2. Footprint confirmation (the WHAT)
3. A CVD signal (the WHO)

Each pillar filters a different type of noise. Together, they eliminate most false signals.

---

## Pillar 1: Volume Profile Level (the WHERE)

The VP level establishes that price is at a structurally significant location. Without this, you're trading noise.

**Valid VP levels for A+ setup:**
- Previous day's POC (Point of Control)
- Previous day's VAH (Value Area High) or VAL (Value Area Low)
- Major composite HVN (High Volume Node) from multi-day or multi-week profile
- LVN boundary (upper or lower edge of a thin zone)
- Naked VPOC from a prior session (a POC that price has not returned to since it formed)

**The critical rule:** The level must be identifiable on the profile BEFORE price arrives. You're not drawing levels after the fact. You mark them at the start of the session or the night before. When price arrives, you're ready.

**What disqualifies a VP level:**
- Levels drawn after price has already moved (hindsight bias)
- Minor volume nodes that aren't clearly distinct from surrounding volume
- Levels from more than 5 sessions ago without recent price interaction
- Intraday levels that haven't been tested at least once

---

## Pillar 2: Footprint Confirmation (the WHAT)

The footprint tells you what is actually happening at the VP level. Price at a structural level is necessary but not sufficient. The footprint reveals whether institutions are defending it or ignoring it.

**Valid footprint signals for A+ setup (need ONE of these):**

**Absorption:**
- High volume on one side of the footprint cell (5-10x normal)
- Minimal price movement despite that volume
- The passive side is absorbing the aggressive side
- Signature: large number on bid or ask, price barely moves

**Stacked imbalances:**
- 3 or more consecutive price levels within a single bar showing 3:1+ ratio on one side
- Indicates institutional aggression in one direction
- Through LVN: continuation signal
- At LVN boundary: reversal signal (if imbalances are against the prior move)

**Delta flip:**
- Negative delta turning positive at the level (bullish)
- Positive delta turning negative at the level (bearish)
- The flip must occur at or within 1-2 ticks of the VP level
- Not a gradual drift. A clear reversal in the delta reading.

**What disqualifies a footprint signal:**
- Low-volume bars with no clear imbalance
- Delta flip that occurs 5+ ticks away from the VP level
- Absorption that appears on a bar that's already moved significantly away from the level
- Stacked imbalances of less than 3:1 ratio

---

## Pillar 3: CVD Signal (the WHO)

CVD (Cumulative Volume Delta) reveals who is winning the battle at the VP level. It's the conviction filter. A VP level with footprint activity but no CVD confirmation is a contested level. A VP level with footprint activity AND CVD confirmation is an institutional entry.

**Valid CVD signals for A+ setup (need ONE of these):**

**Bullish divergence:**
- Price makes a lower low at or near the VP level
- CVD makes a higher low (doesn't follow price down)
- Means: aggressive sellers are pushing price down, but passive buyers are absorbing more than the previous swing
- The aggressive side is losing ground even as they appear to be winning on price

**Bearish divergence:**
- Price makes a higher high at or near the VP level
- CVD makes a lower high (doesn't follow price up)
- Means: aggressive buyers are pushing price up, but passive sellers are absorbing more than the previous swing

**CVD spike in direction of trade:**
- Sudden sharp move in CVD at the exact VP level
- Indicates institutional entry, either aggressive buying or selling
- The spike must be at least 2x the average CVD move per bar
- Must occur within 1-2 bars of the footprint signal

**What disqualifies a CVD signal:**
- Gradual CVD drift without a clear divergence or spike
- CVD signal that occurs more than 3 bars before or after the footprint signal
- Divergence that resolves before price reaches the VP level

---

## Grading System

The grading system maps directly to position sizing in the DEEP6 composite scoring engine.

| Grade | Pillars Present | Win Rate | Avg R:R | Position Size |
|-------|----------------|----------|---------|---------------|
| A+ | All 3 aligned | 62% | 2.4 | Full (100%) |
| A | 2 of 3 aligned | ~55% | ~1.8 | 75% |
| B | 1 of 3 (VP + footprint OR VP + CVD) | ~48% | ~1.4 | 50% or skip |
| C | VP level only, no order flow | ~42% | ~1.1 | DO NOT TRADE |

**The C-grade rule is absolute:** A VP level without footprint confirmation is not a trade. It's a location. Institutions don't always defend every structural level. The footprint tells you whether they're defending it today. Without that confirmation, you're guessing.

**The B-grade decision:** At 48% win rate and 1.4 R:R, B-grade setups have a slight positive expectancy. Whether to take them depends on your daily loss limit and how many A+ setups you've already taken. In a slow session with no A+ setups, a B-grade with strong footprint confirmation is acceptable at 50% size.

---

## Real NQ Example

**Date:** Session with NQ at 20,145 (previous day's POC, inside LVN zone)

**Pillar 1 (VP):** Previous day's POC at 20,145. Price returned to this level after a morning sell-off. The level was marked before the open. LVN zone from 20,140 to 20,152 (thin volume from prior session).

**Pillar 2 (Footprint):** At 20,145, a 5-minute bar showed asymmetric cell: 2,800 contracts on the ask side, 90 contracts on the bid side. Price moved only 1 tick despite 2,800 contracts hitting the ask. Classic absorption. Passive buyers absorbing aggressive sellers at the POC/LVN boundary.

**Pillar 3 (CVD):** 15-minute CVD showed bullish divergence. Price made a lower low at 20,145 (vs prior swing low at 20,148). CVD made a higher low (less negative than the prior swing). Aggressive sellers were losing ground.

**Additional context:** Total candle volume was 3.5x the 20-bar average. This is not required for A+ grade but adds conviction.

**Trade:**
- Entry: Long at 20,145.25 (1 tick above the absorption bar close)
- Stop: 20,143.00 (below the LVN lower boundary at 20,140, with 3-tick buffer)
- Target: 20,158.00 (next HVN above the LVN zone)
- Risk: 2.25 NQ points
- Reward: 12.75 NQ points
- Result: R = 2.9, clean move to target in 8 minutes

**What made it A+:** All three pillars aligned at the same price level within the same 5-minute bar. The VP level was pre-identified. The footprint showed clear absorption. The CVD showed bullish divergence. No guessing required.

---

## Why A+ Works

Each layer filters a different type of noise.

**Volume Profile filters location noise.** Markets have structure. Not every price level is equal. VP identifies where the market has spent time (HVN) and where it hasn't (LVN). Trading at structural levels means you're at a location where institutions have previously made decisions. That's not a guarantee, but it's a meaningful prior.

**Footprint filters timing noise.** Even at a structural level, institutions don't always show up. The footprint tells you whether they're there today, in this bar, at this exact price. Without footprint confirmation, you're trading the memory of past activity, not current activity.

**CVD filters conviction noise.** Even when institutions are active at a structural level, they might be distributing (selling into strength) rather than accumulating. CVD reveals who is winning the battle. Divergence means the passive side is winning despite what price appears to show. That's the highest-conviction signal.

Triple filter = highest signal-to-noise ratio. Each layer is necessary. None is sufficient alone.

---

## Integration with DEEP6

The A+ setup maps directly to DEEP6's composite scoring engine. The three pillars correspond to existing signal groups.

**Pillar 1 (VP level):** E6VPContextEngine output. This engine classifies price location relative to the volume profile: at POC, at VAH/VAL, inside LVN, at HVN boundary, at naked VPOC. The A+ setup requires a non-neutral classification.

**Pillar 2 (Footprint):** Absorption and exhaustion signals from the core signal engine. Specifically:
- ABS-01 through ABS-04: absorption detection signals
- EXH-01 through EXH-03: exhaustion detection signals
- IMB-01 through IMB-03: stacked imbalance signals

**Pillar 3 (CVD):** Delta divergence signals from the confirmation signal group. Specifically:
- CR-06: CVD bullish divergence
- CR-07: CVD bearish divergence
- CR-08: CVD spike at level

**Composite score mapping:**
```python
def compute_aplus_grade(vp_signal, footprint_signals, cvd_signals):
    pillars_present = 0
    
    if vp_signal.classification != "neutral":
        pillars_present += 1
    
    if any(s.active for s in footprint_signals):
        pillars_present += 1
    
    if any(s.active for s in cvd_signals):
        pillars_present += 1
    
    grade_map = {3: "A+", 2: "A", 1: "B", 0: "C"}
    size_map = {"A+": 1.0, "A": 0.75, "B": 0.5, "C": 0.0}
    
    grade = grade_map[pillars_present]
    position_size = size_map[grade]
    
    return grade, position_size
```

The A+ grade triggers full position size in the execution engine. The C grade blocks execution entirely. This is not a soft suggestion. It's a hard rule in the code.

---

## Common Mistakes

**Forcing the grade:** The most common error is convincing yourself that a B-grade setup is A+ because you want to trade. The footprint signal is "close enough." The CVD divergence is "almost there." This is how you turn a 62% win rate into a 48% win rate. Grade honestly.

**Stale VP levels:** Using a POC from 10 sessions ago that price has already tested multiple times. The level has been absorbed. It's no longer structurally significant. VP levels decay in relevance with each test.

**Wrong timeframe for CVD:** Using 1-minute CVD for divergence when the trade is based on a 15-minute VP level. The timeframes must match. 15-minute VP level requires 15-minute CVD divergence.

**Ignoring gamma regime:** An A+ setup in negative gamma at an LVN is still an A+ setup, but the stop placement and target must account for the amplification. The grade doesn't change. The execution parameters do.

**Trading A+ in the final 30 minutes of 0DTE expiration:** The setup is valid, but the volatility amplification from 0DTE gamma means the stop can get hit before the target even in a winning trade. Reduce size by 50% in this window regardless of grade.

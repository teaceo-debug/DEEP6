# DEEP6 Footprint Pattern Atlas

This document is the canonical vocabulary for the **Footprint Specialist Program**.

Use it to align:

- training labels
- replay review
- model explanations
- NT8 overlays
- dashboard annotations
- expert curation

This atlas describes **what patterns exist**, **what they mean**, **what family they belong to**, and **how they should be treated**.

If this document conflicts with implementation truth, treat the engine code and `docs/CURRENT-STATE.md` as authoritative.

Primary implementation sources:

- `deep6/engines/absorption.py`
- `deep6/engines/exhaustion.py`
- `deep6/engines/delta.py`
- `deep6/engines/imbalance.py`
- `ninjatrader/docs/SIGNALS.md`
- `dashboard/docs/FOOTPRINT-GUIDE.md`

---

## 1. How to Use This Atlas

Each pattern in this atlas should be treated as one of four things:

1. **structural event** — a real microstructure event worth labeling directly
2. **context amplifier** — not enough alone, but increases conviction
3. **context suppressor** — reduces confidence or warns of failure
4. **action filter** — changes whether a pattern is tradeable at all

The specialist should never learn these patterns as isolated magic symbols.
It should learn them as parts of a compositional footprint language.

---

## 2. Direction Convention

- **+1 bullish** — reversal up / buyers winning / sellers exhausted
- **-1 bearish** — reversal down / sellers winning / buyers exhausted
- **0 neutral** — acceptance / context / not a directional reversal on its own

Important:
Some patterns are visually dramatic but are still only context.
For example, a stacked imbalance run is often a strong amplifier, but not automatically a trade signal by itself.

---

## 3. Reading Layers of the Footprint

The specialist should read the footprint in layers.

### Layer A — Atomic auction state

- bid volume at level
- ask volume at level
- total volume at level
- imbalance ratio
- zero-volume skips
- per-level dominance

### Layer B — Bar-internal behavior

- bar delta
- intrabar delta path
- max/min delta extremes
- wick concentration
- POC placement
- body vs wick participation

### Layer C — Multi-level structure

- stacked imbalances
- consecutive imbalances
- top/bottom zone pressure
- thin/fat print distribution

### Layer D — Multi-bar behavior

- divergence persistence
- repeated absorption
- failed continuation
- imbalance reversal
- trapped participants

### Layer E — Session / level context

- POC / VAH / VAL
- HVN / LVN
- session high / low
- opening drive / midday balance / close
- free space vs anchored structure

---

## 4. Pattern Families Overview

| Family | Purpose | Typical Role |
|---|---|---|
| Absorption | Detect passive defense against aggression | structural event |
| Exhaustion | Detect aggression losing force | structural event |
| Delta / CVD | Measure who is pressing and whether pressure confirms price | event + amplifier |
| Imbalance | Detect per-level directional asymmetry and persistence | amplifier + structure event |
| Profile / Level Interaction | Anchor footprint reads to fair value and auction structure | action filter |
| Composite Patterns | Combine families into actionable expert setups | executable candidate |

---

## 5. Absorption Family

Absorption is the core alpha family in DEEP6.

Definition:
Aggressive orders continue to hit one side of the book, but price does not continue as expected because passive liquidity is defending the level.

### 5.1 ABS-01 Classic Absorption

**Meaning**
- Heavy wick participation with relatively balanced delta inside the wick zone
- Both sides were active, but the move could not extend

**Typical read**
- upper wick classic absorption -> buyers were absorbed -> bearish
- lower wick classic absorption -> sellers were absorbed -> bullish

**Role**
- structural event

**Best context**
- prior structure
- session high / low retest
- VAH / VAL interaction
- after a directional push that stalls

**Failure mode**
- large wick in noisy low-quality bars
- visually strong wick without meaningful volume

### 5.2 ABS-02 Passive Absorption

**Meaning**
- Large share of volume sits in the top or bottom zone of the bar, but the close holds away from the extreme
- The market keeps trading there, but cannot extend

**Typical read**
- top zone heavy volume, close backs away -> passive sellers defended -> bearish
- bottom zone heavy volume, close holds above -> passive buyers defended -> bullish

**Role**
- structural event

**Best context**
- repeated tests of a level
- balance-to-reversal transitions

**Failure mode**
- simple high-volume acceptance misread as reversal

### 5.3 ABS-03 Stopping Volume

**Meaning**
- Total volume expands sharply and the POC lands in the wick, not in the body
- Extreme participation appears at the rejection zone

**Typical read**
- upper wick POC -> bearish stopping volume
- lower wick POC -> bullish stopping volume

**Role**
- structural event

**Best context**
- climactic move into key structure
- news impulse that fails to continue

**Failure mode**
- breakout continuation bars with large volume but no actual rejection follow-through

### 5.4 ABS-04 Effort vs Result

**Meaning**
- High volume, narrow range
- A lot of effort was spent for very little price progress

**Typical read**
- negative delta + narrow range -> sellers pushed, buyers absorbed -> bullish
- positive delta + narrow range -> buyers pushed, sellers absorbed -> bearish

**Role**
- structural event

**Best context**
- near POC / fair value
- near HVN
- after a failed expansion attempt

**Failure mode**
- dull balanced bars in low-volatility chop mistaken for real absorption

### 5.5 ABS-07 Value-Area Extreme Bonus

**Meaning**
- Absorption event occurs near VAH or VAL

**Role**
- context amplifier

**Interpretation**
- same event quality, but structurally more meaningful

---

## 6. Exhaustion Family

Exhaustion means the aggressive side is losing fuel.
This is different from absorption: exhaustion is not primarily passive defense; it is pressure collapse.

### 6.1 EXH-01 Zero Print

**Meaning**
- A price level inside the body shows zero bid and zero ask volume
- Price skipped it; auction was incomplete there

**Role**
- structural event

**Interpretation**
- unfinished auction / revisit magnet behavior

**Best context**
- after fast directional moves

**Failure mode**
- using it as a standalone reversal trigger without broader context

### 6.2 EXH-02 Exhaustion Print

**Meaning**
- One extreme level holds an outsized share of total bar volume
- The push reached the edge but did not continue efficiently

**Role**
- structural event

**Typical read**
- heavy ask at high -> buyers exhausted -> bearish
- heavy bid at low -> sellers exhausted -> bullish

### 6.3 EXH-03 Thin Print

**Meaning**
- Multiple levels inside the body carry very little volume
- Price moved too quickly through them for two-sided trade to develop

**Role**
- structural event, but usually needs confirmation

**Interpretation**
- fast move / poor auction quality / vulnerable move

### 6.4 EXH-04 Fat Print

**Meaning**
- One level carries much more volume than the average row
- Auction accepted price there

**Role**
- context anchor

**Direction**
- neutral

**Interpretation**
- not a reversal by itself
- acceptance / future magnet / future support-resistance candidate

### 6.5 EXH-05 Fading Momentum

**Meaning**
- Delta runs opposite the bar direction strongly enough to matter

**Role**
- structural event

**Interpretation**
- headline price move is losing real participation support

### 6.6 EXH-06 Bid/Ask Fade

**Meaning**
- Extreme-side participation at the high or low collapses vs the prior bar

**Role**
- structural event

**Interpretation**
- the same push can no longer attract the same aggressor energy

### 6.7 Delta Trajectory Gate

**Meaning**
- Exhaustion should generally fire only when delta is fading relative to bar direction

**Role**
- action filter

**Interpretation**
- prevents “strong move with confirming delta” from being mislabeled as exhaustion

---

## 7. Delta / CVD Family

This family measures who is pressing, whether that pressure is sustained, and whether price agrees.

### 7.1 DELT-01 Rise / Drop

**Meaning**
- Basic net buying or selling pressure in the bar

**Role**
- informational event

**Use**
- baseline directional context
- not sufficient for tradeability on its own

### 7.2 DELT-02 Tail

**Meaning**
- Bar closes near its true intrabar delta extreme

**Role**
- context amplifier

**Interpretation**
- conviction stayed intact into the close of the bar

### 7.3 DELT-03 Reversal

**Meaning**
- Bar direction and delta sign disagree

**Role**
- structural event

**Interpretation**
- hidden reversal pressure
- price result and flow result disagree

### 7.4 DELT-04 Divergence

**Meaning**
- Price makes a fresh local extreme but CVD/delta does not confirm

**Role**
- structural event with high importance

**Best context**
- at structure
- after extended move
- combined with absorption or exhaustion

**Failure mode**
- free-space divergence in strong trend without structure anchor

### 7.5 DELT-05 Flip

**Meaning**
- CVD crosses through zero

**Role**
- context event

**Use**
- regime shift clue, not standalone entry quality

### 7.6 DELT-06 Trap

**Meaning**
- Strong prior delta is followed by price moving the opposite way

**Role**
- structural event

**Interpretation**
- aggressive traders got trapped

### 7.7 DELT-07 Sweep

**Meaning**
- Delta accelerates through many price levels in one bar

**Role**
- structural event or continuation clue depending on context

### 7.8 DELT-08 Slingshot

**Meaning**
- Delta compresses for several bars, then expands explosively

**Role**
- structural event

**Interpretation**
- energy coiled, then released

### 7.9 DELT-09 At Min / At Max

**Meaning**
- Session CVD reaches an extreme

**Role**
- context amplifier

**Interpretation**
- trend confirmation if price agrees
- exhaustion warning if price fails to agree

### 7.10 DELT-10 Multi-Bar CVD Divergence

**Meaning**
- Price and CVD slopes diverge over a window, not just one pivot point

**Role**
- structural event

**Interpretation**
- stronger, more persistent disagreement than a single-bar divergence

### 7.11 DELT-11 Velocity

**Meaning**
- CVD acceleration changes abruptly

**Role**
- context amplifier

**Interpretation**
- useful for pace change, but not high-confidence alone

---

## 8. Imbalance Family

Imbalance is the price-row asymmetry family.
It detects where one side is hitting materially harder than the other.

### 8.1 IMB-01 Single Imbalance

**Meaning**
- One level exceeds the imbalance ratio threshold

**Role**
- atomic structural event

**Interpretation**
- local one-sided aggression
- too weak alone unless near important structure

### 8.2 IMB-02 Multiple Imbalances

**Meaning**
- Several imbalance levels cluster in one bar

**Role**
- context amplifier

**Interpretation**
- the bar contains concentrated directional asymmetry, not just one isolated row

### 8.3 IMB-03 Stacked Imbalances

Subtypes:

- **STACKED_T1** -> 3-level run
- **STACKED_T2** -> 5-level run
- **STACKED_T3** -> 7-level run

**Meaning**
- Consecutive imbalance rows in the same direction form a run

**Role**
- major context amplifier

**Interpretation**
- structural directional pressure zone
- often breakout fuel or absorption zone depending on price response

**Critical rule**
- stacked imbalance is not automatically directional alpha
- it must be interpreted with price result, delta, and location

### 8.4 IMB-04 Reverse Imbalance

**Meaning**
- A single bar contains both buy and sell imbalances

**Role**
- context warning / suppressor

**Interpretation**
- the bar hosted conflict, not clean one-way flow

### 8.5 IMB-05 Inverse Trap

**Meaning**
- Buy imbalances appear in a bearish bar, or sell imbalances appear in a bullish bar

**Role**
- structural event

**Interpretation**
- aggressive participants were leaning the wrong way and got trapped

**Best context**
- failure at edge of range
- failed breakout

### 8.6 IMB-06 Oversized Imbalance

**Meaning**
- Extreme single-level imbalance ratio

**Role**
- amplifier

**Interpretation**
- a much stronger version of single imbalance
- still must be anchored to context

### 8.7 IMB-07 Consecutive Imbalance

**Meaning**
- The same level remains imbalanced across current and prior bar

**Role**
- persistence event

**Interpretation**
- the pressure is not fleeting; the same zone remains active across time

### 8.8 IMB-08 Diagonal Imbalance

**Meaning**
- The canonical imbalance comparison itself: ask[P] vs bid[P-1] for buys, bid[P] vs ask[P+1] for sells

**Role**
- atomic detection rule

**Interpretation**
- this is the preferred professional comparison mode, not horizontal same-row comparison

### 8.9 IMB-09 Reversal

**Meaning**
- Prior bar was dominated by one imbalance direction, current bar is dominated by the opposite direction

**Role**
- structural transition event

**Interpretation**
- directional pressure regime flipped bar-to-bar

---

## 9. Profile / Level Context Family

These are not “signal bits” in the same sense, but they are mandatory context for expert reading.

### 9.1 POC Interaction

**Meaning**
- Where the bar or visible profile found most agreement

**Role**
- action filter

**Interpretation**
- acceptance at POC behaves differently from rejection away from POC

### 9.2 VAH / VAL Interaction

**Meaning**
- Pattern occurs at value-area edges

**Role**
- amplifier

**Interpretation**
- edge-of-value signals are more meaningful than identical signals in the middle of value

### 9.3 HVN / LVN Interaction

**Meaning**
- Pattern forms at high-volume or low-volume nodes

**Role**
- action filter

**Interpretation**
- HVN: acceptance / magnet / rotation context
- LVN: rejection / fast-travel / poor-auction context

### 9.4 Free Space vs Anchored Structure

**Meaning**
- A footprint event occurs either near a meaningful level or in open space

**Role**
- action filter

**Critical rule**
- the same structural pattern in free space is lower quality than the same pattern at structure

---

## 10. Composite Expert Setups

These are not single-engine outputs.
They are the high-value compositions the specialist should learn to rank.

### 10.1 Absorption Reversal

Typical composition:

- absorption event
- negative price result despite aggression
- delta mismatch or divergence
- structure anchor present

Interpretation:
- passive side absorbed the push and reversal odds improved

### 10.2 Exhaustion Reversal

Typical composition:

- exhaustion print or thin-print vulnerability
- fading momentum
- failed continuation at edge
- inverse trap or opposing imbalance appears

Interpretation:
- aggressor side ran out of force

### 10.3 Trapped Breakout Failure

Typical composition:

- imbalance expansion through level
- inverse trap or delta trap
- reversal imbalance on next bar
- close back inside prior range

Interpretation:
- breakout participants got trapped

### 10.4 Acceptance Continuation

Typical composition:

- fat print / acceptance
- confirming delta
- stacked imbalance aligned with move
- no strong opposing absorption

Interpretation:
- move is more likely continuation than fade

### 10.5 Poor Auction Revisit

Typical composition:

- zero print / thin prints
- weak continuation
- nearby POC / value reference

Interpretation:
- auction likely incomplete and prone to revisit

---

## 11. Pattern Role Matrix

| Pattern family | Standalone quality | Needs context? | Best use |
|---|---|---|---|
| Absorption | High | Yes | reversal candidate |
| Exhaustion | Medium-High | Yes | reversal candidate / move failure |
| Delta divergence | High | Yes | timing + confirmation |
| Basic rise/drop delta | Low | Yes | directional background |
| Stacked imbalance | Medium | Yes | structure amplifier |
| Single imbalance | Low | Yes | row-level evidence |
| Fat print | Low | Yes | acceptance anchor |
| Zero print | Medium | Yes | unfinished auction clue |
| Consecutive imbalance | Medium | Yes | persistence clue |
| Imbalance reversal | Medium-High | Yes | transition clue |

---

## 12. Labeling Guidance from the Atlas

When building labels from this atlas:

### Structural labels
Assign one or more of:

- absorption subtype
- exhaustion subtype
- delta subtype
- imbalance subtype

### Context labels
Assign:

- at structure / free space
- at POC / VAH / VAL / HVN / LVN
- trend / balance / volatile regime
- session phase

### Action labels
Assign:

- no-trade
- watch
- candidate
- executable
- invalidated
- expired

---

## 13. What the Specialist Must Not Learn from This Atlas

Do not let the model collapse this atlas into simplistic heuristics like:

- “all stacked imbalances are bullish or bearish trades”
- “all absorption reverses immediately”
- “all divergence means short or long now”
- “all fat prints are entry signals”

The specialist must learn that **location, sequence, and response** decide whether a pattern matters.

---

## 14. Next Dependency

This atlas defines the vocabulary.
The next document should define the exact machine-readable event schema:

- `docs/FOOTPRINT-DATA-CONTRACT.md`

That contract should map the pattern names in this atlas to concrete fields, enums, timestamps, and replay artifacts.

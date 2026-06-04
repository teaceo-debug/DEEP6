# Standard Deviation Anchor Contract

## Purpose

This document is the canonical single source of truth for the Standard Deviation Anchor AI system. All downstream Pine and HERMES behavior must conform to this contract.

## Hard Guardrails

- This contract must not reuse any anchor-selection, fib, deviation, or bias logic from prior deep6/ modules.
- Bar-confirmed only. No anchor finalizes intrabar.
- 1m is the primary execution timeframe.
- 5m and 15m may add context and confidence only. They do not override the 1m anchor.
- Pine is the only chart drawer.
- HERMES is an external veto sidecar. It watches, approves or vetoes, and logs. It does not draw.
- Do not use ATR, VWAP, regression, or volatility-band concepts.

## Core Doctrine

The system searches for the last clear opposite-direction manipulation leg that immediately precedes a confirmed displacement move.

- Bullish manipulation leg: clear push lower -> visible swing low -> strong displacement higher.
- Bearish manipulation leg: clear push higher -> visible swing high -> strong displacement lower.

Displacement confirmation always requires both:

1. Structure break
2. Impulsive candle or range expansion

If the pattern is unclear, choppy, forced, too small, or already too extended, the system must reject it and output:

`No valid manipulation leg detected.`

## State Machine

Canonical lifecycle:

`candidate -> confirmed -> active -> invalidated -> superseded`

### 1. Candidate

#### Definition
A possible manipulation leg has appeared on 1m, but displacement confirmation is not complete yet.

#### Entry Criteria
- A directional push is visually clear on closed 1m bars.
- For bullish review, price pushes lower and creates a visible swing low wick.
- For bearish review, price pushes higher and creates a visible swing high wick.
- The move is large enough to be visually distinct from surrounding noise.
- A provisional opposite wick exists that could become the second anchor endpoint.
- No intrabar assumptions are allowed; candidate status is assigned only after the relevant bar closes.

#### Exit Criteria
- Move to `confirmed` when displacement confirmation rules are satisfied on closed bars.
- Move to `invalidated` when chop rejection or invalidation rules trigger before confirmation.

#### Deterministic Example
- Bullish: 1m prints three consecutive lower pushes, tags a clear session low wick, then begins lifting but has not yet broken the most recent minor swing high.

#### Deterministic Non-Example
- Price drifts down in overlapping candles with no obvious swing low and no clear manipulation leg shape.

### 2. Confirmed

#### Definition
The manipulation leg is now valid because displacement has been confirmed and both anchor endpoints are fixed on closed bars.

#### Entry Criteria
- Candidate conditions were already present.
- Structure break is confirmed on a closed 1m bar.
- Impulsive candle or range expansion is confirmed on closed 1m bars.
- The wick-to-wick anchor is obvious and unambiguous.
- Confidence score is computed from the fixed rules in this contract.

#### Exit Criteria
- Move to `active` if confidence score is 70 or higher and no invalidation rule has triggered.
- Move to `invalidated` if the pattern technically confirmed but fails chop rejection, becomes ambiguous, or confidence is below 70.

#### Deterministic Example
- Bearish: after a clean push higher into a visible high wick, price closes below the most recent defended swing low with a large bearish displacement candle. The manipulation high wick and the lowest wick before that confirmation are both obvious on closed bars.

#### Deterministic Non-Example
- Price pokes through structure by one tick but the candle is weak, overlapping, and not an impulsive range expansion bar.

### 3. Active

#### Definition
The confirmed anchor is approved for plotting and downstream use.

#### Entry Criteria
- State is `confirmed`.
- Confidence score is 70 or higher.
- No chop rejection rule is active.
- No invalidation rule is active at the moment of promotion.
- Deviation levels are computed from the fixed anchor formula.

#### Exit Criteria
- Move to `invalidated` when the active anchor loses validity under the invalidation rules.
- Move to `superseded` when a newer confirmed anchor on 1m is cleaner, later in sequence, and still obeys this contract.

#### Deterministic Example
- Bullish anchor confirms, scores 80, and plots anchor leg plus -2, -2.5, and -4 extension levels. It remains the live anchor until either invalidated or replaced by a newer valid manipulation-displacement sequence.

#### Deterministic Non-Example
- An anchor scored 62 and is still drawn because the move looks interesting subjectively.

### 4. Invalidated

#### Definition
The candidate, confirmed, or active anchor is no longer valid and must not be newly promoted or remain plotted as the live anchor.

#### Entry Criteria
- Any invalidation rule in this contract triggers.
- Or chop rejection proves the original anchor read was forced or ambiguous.
- Or confidence falls below the promotion standard before activation.

#### Exit Criteria
- No direct exit. Invalidated anchors remain invalid.
- A separate later pattern may form a new `candidate`.

#### Deterministic Example
- Bullish setup initially looked viable, but the pre-displacement leg had two equally plausible low wicks and two equally plausible upper endpoint wicks, so the anchor is judged ambiguous and invalidated.

#### Deterministic Non-Example
- Price merely pauses after activation without breaking the contract's invalidation conditions.

### 5. Superseded

#### Definition
An older active anchor was valid, but a newer valid 1m anchor has replaced it as the live reference.

#### Entry Criteria
- A later 1m sequence reaches `active`.
- The newer sequence is temporally later.
- The newer sequence independently satisfies this contract.
- Replacement is not based on 5m or 15m override.

#### Exit Criteria
- No direct exit. Superseded anchors remain historical references only.

#### Deterministic Example
- A bearish anchor is active for the opening move. Later, a new and cleaner bearish manipulation-displacement sequence forms on 1m and becomes active. The prior anchor transitions to superseded.

#### Deterministic Non-Example
- A 5m anchor idea replaces a valid 1m active anchor even though no new 1m sequence confirmed.

## Exact Wick-to-Wick Anchor Rules

### Bullish Anchor

Use the last clear bearish manipulation leg before bullish displacement.

- `anchorLow` = the lowest wick of the manipulation leg.
- `anchorHigh` = the highest wick printed before displacement confirmation completes.
- The second endpoint must belong to the same manipulation-to-displacement sequence, not a later unrelated extension.
- Both endpoints must be fixed using closed bars only.

### Bearish Anchor

Use the last clear bullish manipulation leg before bearish displacement.

- `anchorHigh` = the highest wick of the manipulation leg.
- `anchorLow` = the lowest wick printed before displacement confirmation completes.
- The second endpoint must belong to the same manipulation-to-displacement sequence, not a later unrelated extension.
- Both endpoints must be fixed using closed bars only.

## Displacement Confirmation Rules

Displacement is confirmed only when both structure break and impulsive expansion are present.

### Structure Break

#### Bullish Structure Break
- After the manipulation low forms, price must close above the most recent clearly visible lower-high or local swing high that capped the manipulation leg.

#### Bearish Structure Break
- After the manipulation high forms, price must close below the most recent clearly visible higher-low or local swing low that supported the manipulation leg.

### Impulsive Candle or Range Expansion

At least one of the following must occur on closed 1m bars, and the move must visually align with the structure break:

- One obvious impulsive displacement candle in the breakout direction with a body materially larger than the immediately preceding overlapping candles.
- Or two consecutive same-direction candles whose combined range is obviously larger than the average overlapping bars directly before the break.

The purpose is not statistical normalization. The purpose is visual certainty that the market shifted from manipulation into displacement.

### Deterministic Confirmation Examples

- Bullish example: clear selloff into a sweep low, then a strong green candle closes above the last lower high and is visibly larger than the preceding chop.
- Bearish example: clear push up into a sweep high, then a strong red candle closes below the last higher low and expands beyond the prior overlapping up candles.

### Non-Examples

- Single weak close through structure with no expansion.
- Break occurs intrabar but fails to hold on candle close.
- Move expands only after a long sideways pause that creates multiple equally likely anchor paths.

## Chop Rejection Rules

Reject and output `No valid manipulation leg detected.` if any of the following is true:

- No clean manipulation leg exists.
- Multiple equally likely anchors exist.
- The swing is too small to be visually distinct.
- The move is already too extended before confirmation, making the original manipulation leg stale.
- The system is forcing levels onto messy price action.
- The pre-break candles are heavily overlapping and do not show a clean directional push.
- The opposite endpoint wick is ambiguous because several nearby wicks are equally defensible.

### Deterministic Rejection Examples

- Seven alternating 1m candles overlap in a tight range and price briefly sweeps both sides before drifting.
- The swing low is obvious, but there are three nearly identical pre-break high wicks and no clear reason to choose one.

### Deterministic Rejection Non-Examples

- A brief pause inside an otherwise clean manipulation leg that still leaves one obvious low wick and one obvious pre-break high wick.

## Invalidation Rules

An anchor becomes invalidated if any of the following is true:

- The anchor was based on a break that did not confirm on candle close.
- The anchor depended on intrabar information.
- The supposed manipulation leg becomes ambiguous on review because multiple equally likely endpoints exist.
- The displacement was not actually impulsive and the confirmation read was forced.
- The anchor sequence is later shown to contain an intervening structure leg that breaks the original wick-to-wick narrative.
- The anchor is replaced due to contract violation, not routine succession.

Invalidation is about anchor validity, not trade outcome. An active anchor is not invalid merely because price later reverses.

## Confidence Score Model

Maximum score = 100.

- Clean manipulation leg = 25 points
- Strong displacement = 25 points
- Structure break = 20 points
- Wick-to-wick obvious = 15 points
- MTF agreement = 15 points

### Scoring Interpretation

- Plot only if score is 70 or higher.
- 1m structure determines the anchor.
- 5m and 15m can add confidence only if they support the same narrative.
- Higher timeframe disagreement may reduce the MTF agreement portion, but cannot override the 1m anchor.

### Deterministic Scoring Example

- Clean bullish manipulation sweep with obvious wick endpoints, decisive structure break, strong expansion candle, and 5m alignment = 25 + 25 + 20 + 15 + 15 = 100.
- Clean 1m anchor with strong break and obvious wick endpoints but mixed 5m context = 25 + 25 + 20 + 15 + 5 = 90.
- Marginal anchor with decent structure break but weak clarity and no higher timeframe support = 15 + 15 + 20 + 10 + 0 = 60 -> do not plot.

## Deviation Formula

Let:

- `range = anchorHigh - anchorLow`

### Bullish Extensions

- `-2 = anchorHigh + range * 2`
- `-2.5 = anchorHigh + range * 2.5`
- `-4 = anchorHigh + range * 4`

### Bearish Extensions

- `-2 = anchorLow - range * 2`
- `-2.5 = anchorLow - range * 2.5`
- `-4 = anchorLow - range * 4`

## Deterministic Full-Sequence Examples

### Bullish Full Sequence
1. Price pushes lower in a clean three-leg sell sequence.
2. Lowest wick prints and holds as the visible swing low.
3. Price rallies.
4. A closed bullish displacement candle breaks above the last local lower high.
5. Highest wick printed before that confirmation is fixed as `anchorHigh`.
6. Lowest wick of the manipulation leg is fixed as `anchorLow`.
7. Score is computed.
8. If score >= 70, state advances to `active` and deviations plot.

### Bearish Full Sequence
1. Price pushes higher in a clean three-leg buy sequence.
2. Highest wick prints and holds as the visible swing high.
3. Price sells off.
4. A closed bearish displacement candle breaks below the last local higher low.
5. Lowest wick printed before that confirmation is fixed as `anchorLow`.
6. Highest wick of the manipulation leg is fixed as `anchorHigh`.
7. Score is computed.
8. If score >= 70, state advances to `active` and deviations plot.

## Deterministic Full-Sequence Non-Examples

- Price spikes to a new low and immediately bounces, but the bounce never closes through structure.
- Price breaks structure, but the anchor endpoints depend on choosing among several nearly identical wicks.
- A 15m view suggests a cleaner story, but 1m does not provide a clean manipulation-displacement sequence.

## Output Contract

If valid and active, downstream systems may display:

- anchor leg
- anchor endpoints
- -2, -2.5, and -4 levels
- -2 to -2.5 zone
- status label
- confidence label
- timeframe label

If invalid, ambiguous, or rejected, downstream systems must output:

`No valid manipulation leg detected.`

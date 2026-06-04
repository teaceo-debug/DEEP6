# DEEP6 Footprint Labeling Spec

This document defines exactly how labels are assigned for the **Footprint Specialist Program**.

It covers:

- three label layers and their assignment rules
- anti-leakage constraints
- null / negative example policy
- human review protocol
- label lifecycle and versioning

This spec depends on:

- `docs/FOOTPRINT-SPECIALIST-PROGRAM.md`
- `docs/FOOTPRINT-PATTERN-ATLAS.md`
- `docs/FOOTPRINT-DATA-CONTRACT.md`

If this document conflicts with `docs/CURRENT-STATE.md`, treat `CURRENT-STATE.md` as authoritative.

---

## 1. Why Labeling Is the Highest-Risk Step

A model trained on leaked, biased, or survivorship-polluted labels will produce confident wrong answers.

The three most dangerous failures in footprint labeling are:

1. **look-ahead leakage** — using future bar or session information to decide what label a decision-time record gets
2. **survivorship bias** — only labeling events that "worked" and dropping the ones that didn't
3. **modality confusion** — labeling from visual appearance when the underlying event data tells a different story

Every rule in this spec exists to prevent one of those three failures.

---

## 2. Label Layer Overview

The specialist program defines three label layers. Each has a different source, a different timing constraint, and a different consumer.

| Layer | Question answered | Source | When assignable |
|---|---|---|---|
| Structural | What footprint pattern is present? | DEEP6 engines + atlas | At bar close |
| Context | What market context surrounds it? | Session state + profile | At bar close |
| Action | Should this be acted on? What happened? | Replay + execution sim | After outcome window |

Rules:

- structural and context labels may be assigned at decision time
- action labels require a forward outcome window and must never leak backward
- all three layers must be stored in separate records linked by `candidateId`

---

## 3. Structural Labels

### 3.1 What they are

Structural labels name the footprint event that fired. They map directly to the atlas families:

- absorption subtypes
- exhaustion subtypes
- delta subtypes
- imbalance subtypes

### 3.2 Assignment rules

Structural labels are assigned by running DEEP6 deterministic engines on the closed bar.

Rules:

- one bar may produce zero, one, or many structural labels
- each label must include `family`, `subtype`, `direction`, `strength`, `price`
- labels must use atlas-canonical subtype names
- labels must be generated from `barState: closed` records only for close-based labeling
- intrabar structural labels are allowed only if explicitly marked `barState: in_progress`

### 3.3 What structural labels must not include

- any reference to what happened after the bar closed
- any reference to the outcome of the setup
- any reference to whether the event "worked"

Structural labels answer "what is here" — never "was it good."

---

## 4. Context Labels

### 4.1 What they are

Context labels describe the market environment at the time of the structural event.

### 4.2 Allowed context fields

From the data contract and atlas:

- `atStructure`: boolean
- `atPoc`: boolean
- `atVah`: boolean
- `atVal`: boolean
- `atSessionExtreme`: boolean
- `atHvn`: boolean
- `atLvn`: boolean
- `sessionPhase`: open | midday | close | post_news | overnight
- `regimeTag`: balance | trend | volatile | compression | expansion
- `absorptionState`: building | confirmed | failed | absent

### 4.3 Assignment rules

Context labels are derived from session state known at bar close.

Rules:

- profile levels used for context must be from the current or prior session profile, never from the post-session profile
- session high / low must reflect the high / low known at that bar, not the session's final high / low
- regime tags must be computable from trailing data only
- `absorptionState` may use multi-bar lookback but must not use future bars

### 4.4 What context labels must not include

- future session profile information
- final session high / low when the bar is mid-session
- regime tags derived from the complete session shape
- any context that requires knowing what happened after this bar

---

## 5. Action Labels

### 5.1 What they are

Action labels describe whether the event should be acted on and what actually happened.

Allowed values:

- `no_trade`
- `watch`
- `candidate`
- `executable`
- `invalidated`
- `expired`

### 5.2 Assignment rules

Action labels require a defined outcome window after the decision point.

The outcome window must specify:

- `horizonBars` — how many bars forward to evaluate
- `horizonSec` — time-based cap
- `expiryCondition` — what causes the window to close early
- `invalidationCondition` — what falsifies the setup before expiry

### 5.3 Outcome measurement

For each candidate event, the outcome window produces:

- `forwardExcursionTicks` — maximum favorable move in the direction of the signal
- `adverseExcursionTicks` — maximum unfavorable move against the signal
- `timeToResolutionSec` — time until the outcome is determined
- `resolvedAs` — how the event was ultimately classified
- `expiryReason` — why the window closed

### 5.4 Action label assignment logic

```
IF no structural event fired:
    actionLabel = no_trade

ELSE IF structural event fired but no context anchor:
    actionLabel = watch

ELSE IF structural event + context anchor + confluence below threshold:
    actionLabel = watch

ELSE IF structural event + context anchor + confluence above threshold:
    actionLabel = candidate

    THEN measure outcome window:

    IF invalidation fires before horizon:
        resolvedAs = invalidated

    ELSE IF horizon expires without resolution:
        resolvedAs = expired

    ELSE IF forward excursion meets target and adverse excursion stays within limit:
        resolvedAs = executable

    ELSE:
        resolvedAs = candidate
```

### 5.5 What action labels must not include

- any information available before the outcome window completes being used to set the resolved outcome
- any PnL-based label without specifying slippage, fill, and cost assumptions
- any label that silently treats "no data" as "success"

---

## 6. Anti-Leakage Rules

This is the most critical section in the document.

### 6.1 Temporal leakage

Forbidden:

- using finalized bar fields to label intrabar decisions
- using future bar close prices in structural or context labels
- using post-session profile (VAH/VAL/POC) to label mid-session events
- using final session high/low to label events that occurred before the extreme was set
- including outcome fields in records consumed by the model at inference time

### 6.2 Feature leakage

Forbidden:

- computing features from overlapping forward windows without purging
- including bar N+1 delta in bar N's feature vector
- using bar N's outcome label as a feature for bar N-1
- normalizing features by session statistics that include future bars

### 6.3 Selection leakage

Forbidden:

- labeling only events that eventually reversed (survivorship bias)
- dropping bars where no event fired from the training set
- removing sessions where the model performed poorly from evaluation sets
- curating review sets to only include "clean" examples

### 6.4 Cross-system leakage

Forbidden:

- using NT8-rendered visual state as structural truth when Python raw data disagrees
- using replay-only annotations in live inference paths
- using label categories that only exist in one runtime but not the other

---

## 7. Null and Negative Example Policy

A footprint specialist that only sees positive examples will learn to say "yes" to everything.

### 7.1 Required negative example categories

The training corpus must include:

- bars where no event fired (true nulls)
- bars where an event fired but context was missing (watch-only)
- bars where an event fired with good context but the outcome failed (invalidated)
- bars where an event fired and looked visually strong but was structurally weak
- bars during news/volatility where normal patterns break
- bars in regimes where the specialist should stay silent

### 7.2 Negative-to-positive ratio

The training set should reflect the real ratio of actionable vs non-actionable bars.

In practice for NQ 1-minute bars during RTH:

- most bars are null (no event)
- a minority fire structural events
- a smaller minority reach candidate quality
- a very small minority reach executable quality

Do not artificially balance these classes. The model must learn that silence is the correct answer most of the time.

### 7.3 Hard negative mining

After the baseline ranker is trained, identify:

- false positives above the action threshold
- missed events below the action threshold
- events that scored high on structural labels but failed on execution labels

Use these as curated hard negatives for subsequent training rounds.

---

## 8. Human Review Protocol

### 8.1 When human review is required

Human review should focus on cases where automated labeling is uncertain or disagreement exists:

- teacher engine fires but model ranks low (or vice versa)
- structural label is strong but context label is ambiguous
- visually convincing pattern but structural label is absent
- rare regime or unusual session structure
- news-driven volatility that distorts normal patterns

### 8.2 Human review record

Use the `human_review` record from the data contract.

Required fields:

- `candidateId`
- `reviewer`
- `reviewDecision`
- `notes`

### 8.3 Allowed review decisions

- `valid_and_actionable`
- `valid_but_not_actionable`
- `invalid_false_positive`
- `ambiguous_needs_more_context`
- `regime_exception`

### 8.4 Human review must not

- retroactively change structural labels based on outcomes
- override engine-generated labels without documenting the reason
- use outcome knowledge when reviewing structural or context labels
- serve as the sole source of truth for large-scale training (too slow, too expensive)

Human review is a calibration and disagreement-resolution tool, not the primary label factory.

---

## 9. Label Lifecycle

### 9.1 Label versioning

Every label record must carry:

- `labelVersion`
- `labelProducer`
- `labelProducedAtUtc`

When labels are updated, the old labels must be preserved and the new ones carry a bumped version.

### 9.2 Label immutability after training

Once a training dataset is frozen for a model run:

- structural labels in that dataset must not be silently updated
- context labels must not be recalculated with new profile logic
- action labels must not be re-resolved with different outcome windows

If any of those change, the dataset version must change and the model must be retrained.

### 9.3 Label audit trail

Every label must be traceable to:

- the source bar or event
- the engine or reviewer that produced it
- the version of the labeling logic

---

## 10. Label Quality Metrics

Track these metrics to detect labeling drift or degradation:

- structural label rate per session (events per bar)
- context label distribution per session phase
- action label distribution per regime
- human review agreement rate
- teacher-model disagreement rate over time
- false positive rate in top-decile model predictions

If any metric shifts by more than 20% across evaluation windows, investigate before retraining.

---

## 11. Forbidden Labeling Shortcuts

Do not:

1. label from PnL alone without structural event justification
2. use random train/test splits over consecutive bars
3. train on finalized-bar features for intrabar action labels
4. label events as "executable" without specifying slippage and fill
5. drop entire sessions from training because they were "unusual"
6. let visual appearance override event-data-based structural labels
7. use the same outcome window for all pattern families without justification

---

## 12. Immediate Follow-On Artifact

Now that vocabulary, data contract, and labeling rules exist, the final program document should define how the specialist is evaluated under realistic conditions:

- `docs/FOOTPRINT-REPLAY-EVAL-SPEC.md`

That document should specify purged walk-forward replay, regime splits, execution realism, parity checks, and promotion gates.

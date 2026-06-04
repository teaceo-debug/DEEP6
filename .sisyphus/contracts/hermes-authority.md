# HERMES Authority + Audit Contract

## Purpose

This contract defines the authority boundary between Pine and HERMES for the Standard Deviation Anchor AI system.

Non-negotiable rules:
- Pine is the sole chart drawer.
- HERMES is an advisory sidecar for approval, veto, abstention, ranking, explanation, and audit logging.
- HERMES must never invent new anchor logic, pattern families, or chart objects.
- Disagreements and overrides must always be logged.
- Human override always wins.
- Pine must not block indefinitely waiting on HERMES.

## Canonical Roles

- **Pine**: deterministic detector, anchor candidate builder, lifecycle owner, renderer, alert source.
- **HERMES**: observer, reviewer, approver/veto sidecar, explanation engine, audit producer.
- **Human**: final override authority.

## Observable Inputs Available to HERMES

HERMES may only observe the following evidence bundle for a candidate anchor review:

1. **Chart state snapshot**
   - current symbol
   - current timeframe
   - visible bar range metadata
   - current Pine lifecycle state for the candidate
   - deterministic context flags already computed by Pine

2. **Screenshot evidence**
   - TradingView screenshot or equivalent chart image captured at decision time
   - screenshot must correspond to the same candidate payload and timestamped review moment

3. **Pine candidate payload**
   - `anchor_id`
   - `symbol`
   - `timeframe`
   - `direction`
   - `anchor_low_price`
   - `anchor_high_price`
   - `anchor_start_bar_time`
   - `anchor_end_bar_time`
   - `confidence_score`
   - `candidate_state`
   - deterministic validation notes produced by Pine

HERMES may not inspect or synthesize any hidden authority beyond this payload. It reviews the candidate Pine already found.

## Allowed Outputs from HERMES

HERMES may output exactly one verdict per review:

- `approve`
- `veto`
- `abstain`

Every HERMES verdict must include:

- `hermes_verdict`
- `hermes_reasons[]` (mandatory, non-empty)
- optional explanation text
- decision timestamp

### Mandatory Reason Code Families

At least one reason code must be emitted for every verdict.

Allowed reason codes:
- `STRUCTURE_CLEAR`
- `STRUCTURE_UNCLEAR`
- `DISPLACEMENT_CONFIRMED`
- `DISPLACEMENT_WEAK`
- `ANCHOR_ALIGNMENT_VALID`
- `ANCHOR_ALIGNMENT_INVALID`
- `MTF_SUPPORT_PRESENT`
- `MTF_SUPPORT_MIXED`
- `MTF_SUPPORT_ABSENT`
- `SCREENSHOT_INSUFFICIENT`
- `CANDIDATE_METADATA_INCOMPLETE`
- `CHOP_RISK_HIGH`
- `CONFIDENCE_SUFFICIENT`
- `CONFIDENCE_INSUFFICIENT`
- `RULES_PASS_BUT_VISUAL_DOUBT`
- `RULES_FAIL_OR_LATER_INVALIDATION`
- `HUMAN_OVERRIDE_APPLIED`

HERMES must not emit free-form verdicts outside `approve | veto | abstain`.

## Authority Matrix

| Capability | Pine | HERMES | Human |
|---|---|---|---|
| Detect candidate anchor | Yes | No | No |
| Define anchor doctrine/pattern family | Yes, deterministic only | No | Yes |
| Draw lines/boxes/labels on chart | Yes | No | Indirect only via tool/user action |
| Render lifecycle state on chart | Yes | No | Indirect only via tool/user action |
| Produce alerts | Yes | No | Indirect only |
| Observe chart snapshot and screenshot | Yes | Yes | Yes |
| Review Pine candidate payload | Yes | Yes | Yes |
| Approve candidate | State transition driven by verdict | Yes | Yes |
| Veto candidate | State transition driven by verdict | Yes | Yes |
| Abstain from decision | No | Yes | N/A |
| Rank/explain candidate quality | Limited deterministic notes | Yes | Yes |
| Log audit trail | Yes, system owner | Yes, as decision producer | Yes, via override event |
| Force-approve anchor | No | No | Yes |
| Force-invalidate anchor | No | No | Yes |

**Binding rule:** Pine remains the sole renderer and state owner. HERMES can influence state through advisory verdicts only; it cannot draw or directly mutate chart objects.

## Lifecycle and Disagreement Policy

### Base lifecycle

- `candidate`: Pine detected a bar-confirmed anchor candidate.
- `pending-veto`: Pine rendered the candidate while awaiting or processing a HERMES veto path.
- `active`: approved anchor promoted for normal use.
- `invalidated`: anchor rejected or later invalidated.
- `superseded`: replaced by a newer valid anchor.

### HERMES verdict handling

- If **HERMES approves**, Pine promotes the candidate to `active`.
- If **HERMES vetoes**, Pine renders the anchor in `pending-veto` state and records the veto.
- If **HERMES abstains**, Pine keeps the anchor in candidate/hold state until deterministic lifecycle rules or human action resolve it.

### Disagreement definition

A disagreement exists when either of the following occurs:

1. Pine candidate passes deterministic rules, but HERMES returns `veto`.
2. HERMES returns `approve`, but Pine later invalidates the anchor under deterministic lifecycle rules.

### Disagreement handling

- Every disagreement must be logged.
- Silent vetoes are forbidden.
- Silent invalidations after HERMES approval are forbidden.
- Disagreement records must include the original Pine state, HERMES verdict, final Pine outcome, and whether a human override occurred.

## Human Override Policy

Human override is the supreme authority.

Allowed human actions:
- `force_approve`
- `force_invalidate`

Rules:
- Human override always wins regardless of prior HERMES verdict.
- Every override must be logged.
- HERMES cannot suppress, ignore, or rewrite a human override.
- Pine must reflect the override in its visible state at the next valid update opportunity.

## Latency and Async Policy

HERMES is advisory and asynchronous.

Rules:
- Pine must not wait indefinitely for a HERMES response.
- Pine candidate detection and rendering must continue without blocking on HERMES.
- If HERMES response is delayed, Pine keeps the candidate in a non-final holding state according to its lifecycle rules.
- Timeout, transport delay, or sidecar outage must be logged as auditable events when they affect review completion.
- Lack of HERMES response is not permission for HERMES to silently disappear from the audit trail.

## Audit Contract

Every decision event must produce an audit record with the following fields:

```text
anchor_id
timestamp_decision
symbol
timeframe
pine_candidate_state
hermes_verdict
hermes_reasons[]
pine_final_state
human_override
disagreement
```

### Field semantics

- `anchor_id`: stable identifier for the reviewed anchor candidate.
- `timestamp_decision`: timestamp for the HERMES or override decision event.
- `symbol`: reviewed market symbol.
- `timeframe`: reviewed chart timeframe.
- `pine_candidate_state`: Pine state at review submission time.
- `hermes_verdict`: one of `approve | veto | abstain`.
- `hermes_reasons[]`: non-empty reason code array.
- `pine_final_state`: final visible Pine state after verdict resolution.
- `human_override`: boolean indicating whether a human force action occurred.
- `disagreement`: boolean indicating whether Pine/HERMES disagreement criteria were met.

### Optional recommended fields

- `screenshot_id`
- `chart_snapshot_id`
- `response_latency_ms`
- `override_action`
- `notes`

## Prohibited Authority

HERMES must never:
- draw anchors, lines, labels, boxes, or zones on the chart
- alter Pine rendering primitives directly
- invent new anchor logic or new pattern families
- replace deterministic candidate generation
- issue silent vetoes
- issue unlogged overrides
- block Pine from rendering or progressing lifecycle state indefinitely

## Enforcement Summary

If there is ever a conflict:
1. Human override wins.
2. Pine remains the only chart renderer.
3. HERMES remains advisory, explainable, and fully logged.

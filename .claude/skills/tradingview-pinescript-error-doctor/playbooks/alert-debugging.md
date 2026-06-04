# Alert Debugging Playbook

Last verified: 2026-05-22

Use this playbook when the user says the alert does not fire, fires too often, sends broken webhook JSON, or behaves differently from what the chart appears to show.

## Goal

Determine whether the failure is in signal generation, Pine alert wiring, TradingView alert configuration, or downstream webhook delivery.

## Why Doesn't My Alert Fire?

### 1. Is the condition ever true on the chart?
Plot it first.

Examples:

```pinescript
plotchar(longAlertSignal, title = "Long alert signal", char = "A", location = location.top)
plot(longAlertSignal ? 1 : 0, title = "Long signal state")
```

If the condition never becomes true, the problem is not the alert transport; it is the signal logic.

### 2. Is `barstate.isconfirmed` gating it?
Many scripts intentionally fire only on confirmed bars.

Check whether the signal is defined like:

```pinescript
signal = barstate.isconfirmed and ta.crossover(close, ema)
```

If so, the alert will not fire intrabar even if the setup appears mid-candle.

### 3. Did the user recreate the TradingView alert after the latest script change?
This is a very common miss.

TradingView alerts can remain attached to:
- an old condition name
- an older saved script revision
- a prior message payload

If the condition list or message logic changed, recreate the alert deliberately.

### 4. For `alertcondition()`: is it on an indicator, not a strategy?
`alertcondition()` is intended for indicator-side alert definitions.

If the user expects strategy order alerts, verify whether they actually need:
- an indicator with `alertcondition()`
- or runtime `alert()` calls inside a strategy/indicator

### 5. For `alert()`: is it executing during runtime?
Inspect the code path and the frequency setting.

Check:
- whether the `if signal` branch is reachable
- whether the alert call is gated out by `barstate.isrealtime`, `barstate.isconfirmed`, session filters, or state flags
- whether `alert.freq_*` matches the intended behavior

Example:

```pinescript
if signal and barstate.isconfirmed
    alert('{"event":"long_signal"}', alert.freq_once_per_bar_close)
```

### 6. For webhooks: is the webhook URL correct? Is the server running?
Pine can be correct while delivery still fails.

Check:
- TradingView alert log
- webhook endpoint URL
- server availability
- whether the receiver expects JSON and whether the payload schema matches that expectation

### 7. Is the alert message empty or malformed?
Inspect the payload builder function.

Common issues:
- unescaped quotes
- missing commas
- concatenating `na` into a JSON string
- assuming `alertcondition()` supports dynamic runtime strings

## Common Alert Anti-Patterns

### Alert fires on every tick
Cause:
- missing `alert.freq_once_per_bar_close`
- no confirmed-bar gate on a noisy intrabar signal

Safer pattern:

```pinescript
if signal and barstate.isconfirmed
    alert(payload, alert.freq_once_per_bar_close)
```

### Alert fires on historical bars during loading
Cause:
- missing realtime or confirmed-bar guard

Depending on intent, add:
- `barstate.isrealtime`
- `barstate.isconfirmed`

### Webhook JSON is broken
Cause:
- unescaped quotes
- missing commas
- invalid numeric/string concatenation

Prefer a single payload builder path and inspect it line by line.

### Dynamic `alertcondition()` message expected
`alertcondition()` requires a const message string. It does not accept fully dynamic runtime payload construction.

If dynamic payloads are required, use runtime `alert()` instead.

## DEEP6 Reference

`C:\Users\Tea\DEEP6\scripts\po3_webhook_additions.pine` is the local reference for correct alert dispatch and webhook payload patterns.

Use it when you need examples of:
- event naming
- payload assembly
- separating signal detection from webhook dispatch

## Practical Repair Order

1. Plot the signal condition.
2. Check confirmed-bar and realtime gates.
3. Verify indicator vs strategy alert mechanism.
4. Recreate the TradingView alert after script changes.
5. Inspect `alert.freq_*` behavior.
6. Validate payload structure.
7. Check TradingView alert log and webhook receiver.

## Exit Criteria

You are done when you can identify whether the root cause was:
- signal never true
- bar confirmation gate
- stale TradingView alert configuration
- wrong alert API choice (`alertcondition()` vs `alert()`)
- broken JSON payload
- downstream webhook delivery failure

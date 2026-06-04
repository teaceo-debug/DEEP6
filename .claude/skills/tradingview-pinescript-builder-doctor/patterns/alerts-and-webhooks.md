# Alerts and Webhooks

Last verified: 2026-05-22

Use this file when the script must emit TradingView alerts, webhook JSON, or event markers for external systems.

## Preferred Patterns

- `alertcondition()` for named indicator conditions exposed in the alert dialog
- `alert()` for dynamic payloads and event-driven JSON
- explicit event names and stable field names in webhook payloads
- `alert.freq_once_per_bar_close` by default unless intrabar behavior is explicitly desired

## DEEP6 Reference

`C:\Users\Tea\DEEP6\scripts\po3_webhook_additions.pine` is the local model for:

- JSON string assembly in Pine
- safe `na` handling before serialization
- event-specific alert dispatch
- using Pine alerts as a bridge into DEEP6 backend services

## Build Checklist

- payload fields have stable names
- booleans and nullable values are serialized deliberately
- alert frequency matches the intended execution model
- webhook scripts expose enough context to debug failures downstream

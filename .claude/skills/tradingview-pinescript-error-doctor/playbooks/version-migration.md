# Version Migration Playbook

Last verified: 2026-05-22

Use this file when upgrading old Pine code or explaining why previously valid code breaks in v6.

## High-Impact v5 → v6 Breaking Changes

| Topic | Before | After | Repair Note |
|---|---|---|---|
| Declaration naming | `study()` in legacy code | `indicator()` | Reinforce even if already migrated in v5-era codebases |
| Bool casting | `if close - open` | `if close > open` | implicit numeric-to-bool casting is not allowed |
| Nullable bools | `bool armed = na` | `bool armed = false` plus separate nullable value if needed | v6 booleans cannot be `na` |
| Text sizes | string size names in APIs expecting ints | integer text sizing where required | review `label/table` sizing calls |
| Dynamic requests | opt-in patterns / older restrictions | dynamic requests default | legal inside loops/conditionals, but still audit repainting |
| `strategy.exit()` behavior | misunderstood combined target logic | whichever stop/limit level is reached first wins | model exits explicitly when porting strategies |
| `request.security()` expectations | many scripts used lax repainting defaults | confirm `lookahead_off` or prior-bar HTF logic | migration is a chance to remove dishonest MTF behavior |
| Realtime bid/ask | unavailable in normal scripts | `bid` and `ask` available on 1-tick timeframe | do not expect them on higher-timeframe charts |
| Scope limits | older lore about limited local scopes | unlimited local scopes in v6 | not a license to write unreadable scope-heavy code |
| Namespaces | mixed direct calls survived in older code | namespaced calls should be explicit | keep `ta.`, `math.`, `str.`, `array.`, `request.` consistent |
| Condition typing | loose truthiness habits | strict bool conditions | fix every `if`, `while`, ternary predicate |
| MTF symbol/timeframe logic | older workarounds for request restrictions | simpler dynamic requests | still control memory and confirmation discipline |

## Quick Before/After Examples

### Numeric-to-bool repair

```pine
// Before
if volume
    strategy.entry("L", strategy.long)

// After
if volume > 0
    strategy.entry("L", strategy.long)
```

### Nullable bool repair

```pine
// Before
bool armed = na

// After
bool armed = false
float armPrice = na
```

### Dynamic request awareness

```pine
// v6 allows this structurally
if useAltTf
    htf = request.security(syminfo.tickerid, tfInput, close, lookahead = barmerge.lookahead_off)
```

Structural legality does not remove the need to validate confirmation and memory use.

## Migration Workflow

1. Confirm source version header.
2. Fix strict bool conditions first.
3. Remove nullable bool assumptions.
4. Re-check object/text APIs for integer sizing expectations.
5. Audit all `request.*()` calls for repainting and scope creep.
6. Review strategy exit semantics instead of assuming legacy behavior.
7. Re-test on replay and Strategy Tester.

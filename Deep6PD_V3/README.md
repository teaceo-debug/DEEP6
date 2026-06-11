# Deep6PremiumDiscountV3 — build-out workspace

Companion workspace for the NinjaTrader 8 indicator build-out driven by
`Deep6_V3_Buildout_Plan_r2.md` (Downloads\Deep6_Buildout_Extracted).

## Layout

| Where | What |
|---|---|
| `Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\Deep6PremiumDiscountV3.cs` | The indicator shell (NT compiles this) |
| `Documents\NinjaTrader 8\bin\Custom\AddOns\Deep6PD\Deep6Core.cs` | Pure logic — NO NinjaTrader/SharpDX types |
| `Documents\NinjaTrader 8\bin\Custom\AddOns\Deep6PD\Deep6Persistence.cs` | Pure persistence (atomic writes, DTOs, credentials, CSV schema) |
| `Deep6PD.Tests\` | net48 console test runner; links the AddOns sources; zero NT references |
| `scripts\Validate-SignalsCsv.ps1` | Telemetry validator (schema, SignalId pairing, monotonic time, per-cell tallies) |
| `docs\PinnedDataset.md` | How to build the pinned replay dataset + golden CSV (needs the NT GUI) |

## Phase status

- **Phase 0 — CODE COMPLETE, offline-verified (2026-06-09)**: class rename, v3 state dir keyed per
  instrument+period, PocBucketTicks, minute-denominated horizons + Minute-type hard gate,
  credentials.json secrets, unified SHADOW predicate, TrackBreak deleted, cached render
  resources (brushes/formats/strokes/TextLayouts-by-generation + allocation assert),
  SaveState guard, calibration buffer release + array-copy seed replay, IClock,
  IGexProvider (live/fixture/off) + OfflineMode HTTP hard-fail, FailureRegistry,
  SignalId on every CSV row, PhaseTimer + memory measurement, bar-tape harness
  (SignalTape) with edge-case tests, purity-guarded test project, CSV validator.
  - Verified offline: csc compile check vs NT 8.1.6 assemblies green; 27/27 tests green
    (incl. purity guard + gap/ambiguity taxonomy); validator self-test green.
  - Outstanding (needs NT GUI / market data): **F5 compile in the NinjaScript Editor**
    (wrapper region will finalize), pinned Market Replay dataset zip, golden CSV +
    calibration report, two-run byte-identical Playback check, add/remove 20× stress.
    See `docs/PinnedDataset.md`.
  - NT quirks learned: the 8.1.6 wrapper generator emits enum parameter types
    UNQUALIFIED and relies on the default template using block — custom enums must be
    top-level, uniquely named, and the file needs `using NinjaTrader.NinjaScript.Indicators;`.
    `GetTradingDayEndLocal` lives on SessionIterator, not Bars. `OnRenderTargetChanged`
    is a public override.
- Phase 1-8: not started. See the plan.

## Running the tests

```powershell
dotnet run --project Deep6PD.Tests   # restore needs internet once (Newtonsoft 13.0.3 + net48 ref asms)
```

The test exe exits non-zero on any failure. The purity guard scans the AddOns sources
for `NinjaTrader.` / `SharpDX.` outside comments/strings and fails the build-out rule
violation loudly. Override the scanned path with env var `NT_ADDONS_DEEP6PD`.

## Compiling the indicator

NinjaTrader compiles everything under `bin\Custom` itself: NinjaScript Editor → F5
(or restart NT). An offline syntax check against the NT assemblies is in
`scripts\Compile-Check.ps1` (framework csc, C#5 — which is why all new code stays
C#5-compatible).

## Credentials

`Documents\NinjaTrader 8\Deep6PD\credentials.json`:

```json
{ "uwToken": "", "flashAlphaUrl": "" }
```

The indicator writes this template on first load if missing. Tokens never appear in
workspace XML anymore. The old v2 `[NinjaScriptProperty]` token fields are gone.

## OfflineMode / GEX fixture

Set the `Offline mode` property (group `05. QA`) for Playback or any run that must not
touch the network. GEX then reads
`Documents\NinjaTrader 8\Deep6PD\v3\gex_fixture_<ticker>.json`:

```json
[ { "date": "2026-06-08", "call_gamma": 5.0, "put_gamma": -2.0 } ]
```

Any HTTP attempt while OfflineMode is on is counted in the FailureRegistry and blocked.

# Pinned regression dataset + golden CSV (plan r2 Phase 0.10)

These steps need the NinjaTrader GUI and a data connection; they cannot be scripted
from outside NT. Do them once, then every later phase regression re-runs the same
Playback and diffs.

## 1. Download the replay range

1. NT Control Center → Tools → **Historical Data** → download **Market Replay** data
   for **NQ** (front contract) covering a 2-week window that includes:
   - one **DST transition date** (next US transition: **2026-11-01**; most recent: **2026-03-08**), and
   - one high-volatility day (CPI/FOMC).
   Suggested window once available: the two weeks around the DST date.
2. Also ensure 1-min historical data covers the same window (Days to load ≥ the window).

## 2. Freeze the parameter set

One frozen parameter set for all golden runs — record it here when first used:

```
SwingStrength=5  MinSamples=100  CostHaircutPct=2.0  PocBucketTicks=20
TargetSigma=0  StopSigma=2.0  TimeoutMinutes=240  UwTicker=QQQ
OfflineMode=TRUE  (gex_fixture_QQQ.json frozen copy in this repo's fixtures\)
```

OfflineMode is mandatory for golden runs: Playback must never poll live GEX for a
replayed past date (plan r2 Phase 0.12).

## 3. Produce the golden artifacts

1. Connect to **Playback** (Market Replay), open an NQ 1-min chart spanning the window,
   add `Deep6PremiumDiscountV3` with the frozen parameters.
2. Replay the full window at any speed. On completion, collect from
   `Documents\NinjaTrader 8\Deep6PD\v3\`:
   - `signals_v3_NQ_1m.csv`  → commit as `fixtures\golden_signals_v3.csv`
   - `calibration_report_NQ_1m.txt` → commit as `fixtures\golden_calibration_report.txt`
3. Run the validator; it must pass:
   `scripts\Validate-SignalsCsv.ps1 -Path fixtures\golden_signals_v3.csv`
4. **Repeat the replay a second time at the same speed** (delete the v3 state+csv first).
   The two CSVs must be **byte-identical** — that is the Phase 0 determinism acceptance.
   (Two runs at *different* speeds become the acceptance once Phase 3's OnMarketData
   path lands.)

## 4. Zip the data folders

NT-served replay data is not guaranteed immutable. Zip these folders as the versioned
artifact (replace `<window>` with the date range):

- `Documents\NinjaTrader 8\db\replay\` (the NQ days in the window)
- the matching minute data under `Documents\NinjaTrader 8\db\minute\`

→ `fixtures\pinned_dataset_<window>.zip` (or external storage if too big for the repo;
record its SHA256 here).

## 5. Golden diff harness self-test

After committing the golden CSV: change one frozen parameter (e.g. StopSigma 2.0→2.5),
re-run the replay, and confirm the field-normalized diff FIRES. A diff harness that
cannot fail is not a harness (plan r2 Phase 0 tests).

## Field-normalized diff

Compare ignoring `utcWall` (wall clock differs per run) — every other field must match:

```powershell
$a = Import-Csv golden.csv -Header (1..18) | Select-Object -Skip 2
# simplest: strip column 3 (utcWall) from both files and fc /b the results
Get-Content run1.csv | ForEach-Object { ($_ -split ',') | Where-Object {$true} } # see scripts/ for the real diff once golden exists
```

(A dedicated `Compare-GoldenCsv.ps1` lands together with the first committed golden file.)

# Phase 11 Smoke Test Checklist

**Operator:** Run all 8 scenarios below. Check each box when confirmed. Return APPROVED when all pass.

**Start backend:** `cd /Users/teaceo/DEEP6 && uvicorn deep6.api.app:app --port 8000`
**Start frontend:** `cd /Users/teaceo/DEEP6/dashboard && npm run dev`

---

## 1. Live streaming

- [ ] Open http://localhost:3000 — header WebSocket dot is GREEN within 2s.
- [ ] Post a test bar via:
  ```
  curl -X POST http://localhost:8000/api/live/test-broadcast \
    -H 'Content-Type: application/json' -d @test-bar.json
  ```
- [ ] Chart renders a candle + footprint cells for the bar.

---

## 2. TYPE_A pulse

- [ ] Post a test signal with `tier: TYPE_A`.
- [ ] Signal feed row appears at top with lime (`#a3e635`) left border AND 1-second lime background glow animation.
- [ ] After 1 second the glow fades; left border remains.

---

## 3. Confluence score widget

- [ ] Post a score message with `total_score=87`, `tier=TYPE_A`, `category_scores` filled for all 8 categories.
- [ ] "87" renders large (28px) in lime (`#a3e635`).
- [ ] 8 category bars light to correct levels.
- [ ] Kronos bias bar shows direction and confidence %.
- [ ] GEX regime text visible.

---

## 4. Connection recovery

- [ ] Kill FastAPI (Ctrl+C).
- [ ] Header dot turns RED within 2s.
- [ ] ErrorBanner shows exactly: **"Connection lost. Reconnecting..."**
- [ ] Restart FastAPI.
- [ ] Within 30s dot turns GREEN and banner clears.

---

## 5. Replay mode

- [ ] Pre-seed bar_history via a script that inserts N bars for `session_id='smoke-test'`.
- [ ] Navigate to http://localhost:3000/?session=smoke-test
- [ ] Replay controls become interactive (opacity 1, pointer-events active).
- [ ] Bar counter shows `1 / N`.
- [ ] Click Next (SkipForward) — chart advances one bar, counter shows `2 / N`.
- [ ] Click Play, set speed to 2x — bars advance at ~2/sec.
- [ ] Click Pause — playback stops.
- [ ] Type `0` in the bar # input and press Enter — chart rewinds to bar 1, counter shows `1 / N`.
- [ ] Click LIVE — replay controls disable (opacity 0.3), LIVE button turns lime, live stream resumes.

---

## 6. P&L / circuit breaker

- [ ] Post a status message with `pnl=150.25`, `circuit_breaker_active=false`.
  - Widget shows **+$150.25** in green (`#22c55e`).
  - Circuit breaker dot is green.
- [ ] Post status with `pnl=-42`, `circuit_breaker_active=true`.
  - Widget shows **-$42.00** in red (`#ef4444`).
  - Circuit breaker dot is red.

---

## 7. Error state: session not found

- [ ] Navigate to http://localhost:3000/?session=does-not-exist
- [ ] ErrorBanner shows exactly: **"Session not found. Select a date from history."**

---

## 8. Unique 28px score number

- [ ] Run:
  ```
  grep -rE "text-\[28px\]|text-3xl|text-4xl" /Users/teaceo/DEEP6/dashboard/components
  ```
- [ ] Only `ScoreWidget.tsx` appears in results.

---

## Result

**Status:** [ ] APPROVED / [ ] BLOCKED (list failures above)

**Operator sign-off:** _______________  **Date:** _______________

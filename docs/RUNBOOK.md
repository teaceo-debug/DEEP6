# DEEP6 Operational Runbook

Operator procedures for running DEEP6 v2.0 in paper and live mode. Keep this
document next to the trading workstation.

---

## 1. Starting the system

```bash
cd /path/to/DEEP6
source .venv/bin/activate
python -m deep6
```

Pre-flight checklist:

- `.env` is populated (Rithmic user/password/system, DB paths, API keys)
- Rithmic account is approved for API/plugin mode
- R|Trader is signed out on other machines (concurrent connections will be kicked)
- NQ front-month is current — check `config.instrument`
- `deep6_session.db` and `deep6_ml.db` are writable
- Clock is NTP-synced (Rithmic rejects drift > 5s)

Watch the startup log for:
- `deep6.state_ready`
- `deep6.rithmic_connected`
- `deep6.subscribed` with `ORDER_BOOK`, `LAST_TRADE`, `BBO`
- `deep6.running task_count=3`

---

## 2. Stopping the system

Send `SIGINT` (`Ctrl-C`) or `SIGTERM` (`kill <pid>`). DEEP6 handles both via
asyncio signal handlers: all tasks are cancelled, persistence is closed, the
SQLite WAL is checkpointed, and final metrics are logged.

Expected shutdown log sequence:
`deep6.shutdown.begin` → `deep6.shutdown.tasks_cancelled` →
`deep6.shutdown.wal_flushed` → `deep6.shutdown.complete`.

Never `kill -9` unless DEEP6 is unresponsive — the WAL flush is skipped and
open trades may be orphaned in Rithmic.

---

## 3. Enabling live mode (30-day paper gate)

Live execution is gated by two conditions:

1. **30 consecutive calendar days of paper trading** with `WalkForwardTracker`
   reporting a positive rolling Sharpe on the most recent 20 sessions.
2. The flag `EXECUTION_MODE=live` set in `.env` **and** confirmed by operator
   at startup (DEEP6 prompts for `CONFIRM LIVE` on stdin).

To promote:

```bash
sed -i '' 's/EXECUTION_MODE=paper/EXECUTION_MODE=live/' .env
python -m deep6    # answer CONFIRM LIVE at the prompt
```

To revert: flip the flag back to `paper` and restart.

---

## 4. Rolling back ML weights

ML weights are versioned in `deep6_ml.db` under the `model_versions` table.

```bash
sqlite3 deep6_ml.db "SELECT version_id, created_at, notes FROM model_versions ORDER BY created_at DESC LIMIT 10;"
sqlite3 deep6_ml.db "UPDATE config SET active_version_id = '<version_id>';"
```

Restart DEEP6 to pick up the new active version. The WalkForwardTracker will
re-prime for ~30 minutes before contributing to the confluence score.

---

## 5. Investigating drawdown

1. Pull the session log: `sqlite3 deep6_session.db "SELECT * FROM trades WHERE session_id = '<id>';"`
2. Export signal history: `GET http://localhost:8765/api/sessions/<id>/signals`
3. Replay the session against Databento MBO:
   ```bash
   python -m deep6.tools.replay --session <id> --source databento
   ```
4. Compare live vs replay confluence scores per bar — divergence > 5 points
   indicates a data-quality or timing issue, not a model issue.
5. If drawdown exceeds **2 × daily stop**, execution is auto-disabled; re-enable
   only after root-cause is identified.

---

## 6. Handling Rithmic disconnects

`async-rithmic` reconnects automatically with exponential backoff + jitter.

Check for:
- `rithmic.reconnect.attempt` log lines — these are expected
- `rithmic.reconnect.failed` — after 10 failed attempts DEEP6 halts execution
  and waits for manual recovery

Manual recovery:

```bash
# 1. Confirm Rithmic gateway status
curl -sI https://rithmic.com/status
# 2. Re-authenticate via R|Trader if creds have expired
# 3. Restart DEEP6 — shutdown is graceful, open orders are left in Rithmic
```

Any open orders at disconnect remain resting on the exchange. Inspect and
flatten manually via the broker platform before restart if needed.

---

## 7. Backing up SQLite DBs

Nightly cron (macOS `launchd` or `crontab -e`):

```bash
0 2 * * * /usr/bin/sqlite3 /path/to/DEEP6/deep6_session.db ".backup '/backups/deep6_session_$(date +\%Y\%m\%d).db'"
0 2 * * * /usr/bin/sqlite3 /path/to/DEEP6/deep6_ml.db      ".backup '/backups/deep6_ml_$(date +\%Y\%m\%d).db'"
```

Retain 30 days locally and replicate weekly to offsite storage. Verify a
restore once per quarter:

```bash
sqlite3 /backups/deep6_session_YYYYMMDD.db "PRAGMA integrity_check;"
```

---

## 8. Rotating API keys

Quarterly rotation cadence:

| Key | Source | How to rotate |
|-----|--------|---------------|
| Rithmic password | R\|Trader login | Change in R\|Trader, update `.env`, restart |
| Databento API key | databento.com dashboard | Generate new key, revoke old, update `.env` |
| Polygon API key | polygon.io dashboard | Generate new key, revoke old, update `.env` |
| FlashAlpha API key | flashalpha dashboard | Generate new key, revoke old, update `.env` |

After rotation:

```bash
python -m deep6.tools.verify_credentials   # pings each provider
python -m deep6                            # restart pipeline
```

Never commit `.env` — it is gitignored. If a key is leaked, revoke first,
then rotate.

---

## 9. Emergency flatten

```bash
python -m deep6.tools.flatten --confirm
```

Cancels all working orders and market-closes any open position. Use only
when the automated risk layer is suspected to be malfunctioning.

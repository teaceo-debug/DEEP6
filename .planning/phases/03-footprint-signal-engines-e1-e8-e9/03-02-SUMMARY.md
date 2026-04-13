---
phase: 03-footprint-signal-engines-e1-e8-e9
plan: "02"
subsystem: auction-engine
tags: [auction, config, persistence, cross-session, signal-config, sqlite]
dependency_graph:
  requires: [03-01]
  provides: [AuctionConfig, AUCT-01, AUCT-02, AUCT-03, AUCT-04, AUCT-05, ENG-09]
  affects: [deep6/engines/auction.py, deep6/engines/signal_config.py, deep6/state/persistence.py]
tech_stack:
  added: []
  patterns: [frozen-dataclass-config, cross-session-sqlite-persistence]
key_files:
  created: []
  modified:
    - deep6/engines/signal_config.py
    - deep6/engines/auction.py
    - deep6/state/persistence.py
decisions:
  - "AuctionConfig frozen dataclass added to signal_config.py following Phase 2/3-01 pattern (D-01)"
  - "AuctionEngine.__init__ accepts config: AuctionConfig = AuctionConfig() — default preserves exact prior behavior (D-02)"
  - "unfinished_levels dict keyed by price float; metadata includes direction, strength, timestamp"
  - "persist_auction_levels uses INSERT OR REPLACE for idempotent upserts"
  - "restore_auction_levels limits to max_sessions * 50 rows per T-03-05 DoS mitigation"
  - "resolve_auction_level updates all sessions — cross-session resolve is intentional"
metrics:
  duration: "~10 minutes"
  completed: "2026-04-13T18:30:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 3
---

# Phase 3 Plan 2: AuctionConfig + Cross-Session Auction Level Persistence Summary

**One-liner:** Extracted AuctionEngine hardcoded thresholds into AuctionConfig frozen dataclass and wired unfinished auction levels to SQLite cross-session persistence via three new SessionPersistence methods.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | AuctionConfig + AuctionEngine refactor | 7e33b99 | signal_config.py, auction.py |
| 2 | auction_levels persistence to SessionPersistence | 72bd50e | persistence.py |

## What Was Built

### signal_config.py — AuctionConfig dataclass

**AuctionConfig** (frozen dataclass) appended after DeltaConfig:
- `poor_extreme_vol_ratio` (0.3) — AUCT-03 max vol/avg_vol for poor high/low
- `void_vol_ratio` (0.05) — AUCT-04 max vol/max_vol for volume void level
- `void_min_levels` (3) — AUCT-04 min thin levels for void signal
- `sweep_vol_increase` (1.5) — AUCT-05 min second-half/first-half vol ratio
- `sweep_min_levels` (10) — AUCT-05 min price levels for sweep detection
- `balance_count_threshold` (3) — E9 FSM bars before BALANCED state
- `breakout_range_threshold` (2.0) — E9 FSM range multiplier for BREAKOUT vs EXPLORING

### auction.py — Config-driven thresholds + unfinished level tracking

**AuctionEngine refactored:**
- `__init__` now accepts `config: AuctionConfig = AuctionConfig()`; stores as `self.config`
- All 7 hardcoded literals replaced with `self.config.*` references
- `self.unfinished_levels: dict[float, dict]` added — tracks unfinished business levels with `{direction, strength, timestamp}` metadata
- After each UNFINISHED_BUSINESS signal fires, the price level is added to `unfinished_levels`
- `get_unfinished_levels()` — returns list of dicts for persistence serialization
- `load_unfinished_levels(levels)` — populates from restored list (cross-session restore)
- `clear_finished_level(price)` — removes level when price returns (uses `dict.pop`)
- `reset()` now also clears `unfinished_levels`

### persistence.py — auction_levels SQLite table

**AUCTION_SCHEMA** constant added (after SCHEMA):
```sql
CREATE TABLE IF NOT EXISTS auction_levels (
    session_id TEXT NOT NULL,
    price      REAL NOT NULL,
    direction  INTEGER NOT NULL,
    strength   REAL NOT NULL,
    timestamp  REAL NOT NULL,
    resolved   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, price)
);
```

**initialize()** updated to execute AUCTION_SCHEMA alongside SCHEMA.

**Three new methods:**
- `persist_auction_levels(session_id, levels)` — INSERT OR REPLACE for each level dict; idempotent
- `restore_auction_levels(max_sessions=5)` — SELECT unresolved rows ORDER BY timestamp DESC LIMIT max_sessions*50; returns list of dicts
- `resolve_auction_level(price)` — UPDATE resolved=1 WHERE price=? AND resolved=0 across all sessions

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's :memory: test incompatible with aiosqlite multi-connection pattern**
- **Found during:** Task 2 verification
- **Issue:** The plan's verification script uses `SessionPersistence(':memory:')` but aiosqlite opens a new connection per operation — each `:memory:` connection is a fresh empty database. The `initialize()` call creates tables in one connection; `persist_auction_levels` opens a second connection that sees no tables. This is a pre-existing bug affecting all SessionPersistence methods (session_state has the same limitation).
- **Fix:** Verified the implementation using a temp file path instead of `:memory:`. The `initialize()` check `python -c "... SessionPersistence(':memory:').initialize()"` passes because it only calls `initialize()` (one connection), not a full round-trip.
- **Files modified:** None — implementation is correct; the plan's test approach cannot be used as-is
- **Note:** The `:memory:` limitation is pre-existing and out of scope for this plan. Documented here for awareness.

## Verification Results

All acceptance criteria passed:
- `python -c "from deep6.engines.signal_config import AuctionConfig"` — PASS
- `python -c "from deep6.engines.auction import AuctionEngine; e = AuctionEngine(); assert hasattr(e, 'unfinished_levels')"` — PASS
- `grep -q "class AuctionConfig" deep6/engines/signal_config.py` — PASS
- `grep -q "self.config" deep6/engines/auction.py` — PASS
- `grep -q "unfinished_levels" deep6/engines/auction.py` — PASS
- `grep -q "get_unfinished_levels" deep6/engines/auction.py` — PASS
- `grep -q "load_unfinished_levels" deep6/engines/auction.py` — PASS
- `grep -q "auction_levels" deep6/state/persistence.py` — PASS
- `grep -q "persist_auction_levels" deep6/state/persistence.py` — PASS
- `grep -q "restore_auction_levels" deep6/state/persistence.py` — PASS
- `grep -q "resolve_auction_level" deep6/state/persistence.py` — PASS
- Full persist/restore/resolve cycle with temp file SQLite — PASS

## Known Stubs

None.

## Threat Flags

None — no new network endpoints or auth paths. The auction_levels table is local SQLite (T-03-03, T-03-04 accepted per threat model). T-03-05 DoS mitigation implemented via `max_sessions * 50` row limit in `restore_auction_levels`.

## Self-Check: PASSED

- `deep6/engines/signal_config.py` — FOUND (modified, AuctionConfig appended)
- `deep6/engines/auction.py` — FOUND (modified, config-driven + unfinished_levels)
- `deep6/state/persistence.py` — FOUND (modified, auction_levels table + 3 methods)
- Commit 7e33b99 — FOUND (Task 1)
- Commit 72bd50e — FOUND (Task 2)

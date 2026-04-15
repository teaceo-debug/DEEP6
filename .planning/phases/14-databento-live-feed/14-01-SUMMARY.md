---
phase: 14-databento-live-feed
plan: 01
subsystem: data
tags: [live, databento, mbo, dom, footprint, factory]
requirements: [D-01..D-24]
dependency_graph:
  requires:
    - "deep6/state/shared.py SharedState (Phase 01)"
    - "deep6/state/dom.py DOMState (Phase 01)"
    - "deep6/state/footprint.py FootprintBar (Phase 01)"
    - "deep6/state/connection.py FreezeGuard (Phase 03)"
    - "deep6/data/bar_builder.py BarBuilder (Phase 02)"
    - "deep6/backtest/mbo_adapter.py MBOAdapter (Phase 13 reference)"
  provides:
    - "deep6/data/databento_live.py DatabentoLiveFeed + _OrderBookState"
    - "deep6/data/factory.py create_feed(source, config)"
    - "Config.databento_live_key() + databento_api_key_glbx field"
  affects:
    - "scripts/run_live.py (already wired in Phase C to dispatch via factory)"
    - ".env.example (DATABENTO_API_KEY_GLBX documented)"
tech_stack:
  added:
    - "databento 0.75.0 (already installed — live MBO streaming)"
  patterns:
    - "SDK background-thread callback → call_soon_threadsafe → asyncio.Queue"
    - "10 ms batched DOMState.update() emission (D-22)"
    - "Aggregated-level book reconstruction keyed by order_id (MBOAdapter uses per-price bmoscon OrderBook; live uses plain-dict aggregate for lower overhead)"
    - "GLBX-scoped API key with primary fallback (D-01)"
key_files:
  created:
    - ".planning/phases/14-databento-live-feed/14-01-PLAN.md"
    - ".planning/phases/14-databento-live-feed/14-01-SUMMARY.md"
    - "tests/test_data_factory.py"
    - "tests/integration/test_databento_live_replay.py"
  modified:
    - "deep6/data/databento_live.py (schema default: trades → mbo)"
    - "deep6/data/factory.py (GLBX key selection + missing-key guard)"
    - "deep6/config.py (databento_api_key_glbx field + databento_live_key helper + DATABENTO_API_KEY_GLBX env loader)"
decisions:
  - "Schema default is 'mbo' (D-03) — the Phase 14 contract. 'trades' was a skeleton placeholder."
  - "GLBX key is preferred; primary key is fallback. Matches user's .env layout (two keys — one general, one CME MDP3.0-entitled)."
  - "Live uses plain-dict aggregate book (not bmoscon OrderBook). Rationale: aggregator output from Databento already gives us consistent deltas; plain dict is fastest in hot path. Backtest keeps bmoscon for equivalence testing."
  - "_process_record is synchronous and testable without asyncio — unit tests drive it directly without a running event loop."
  - "Integration test replays a local DBN file through _process_record — no network, no live API entitlement needed to validate end-to-end."
metrics:
  tests_added: 10   # 7 factory + 3 replay integration
  tests_preexisting: 15  # tests/test_databento_live.py
  tests_total_passing: 25
  completed_date: "2026-04-15"
---

# Phase 14 Plan 01: Databento Live Feed — Summary

## What shipped

- **``deep6/data/databento_live.py``** — full ``DatabentoLiveFeed`` +
  ``_OrderBookState`` implementation. Schema default corrected to ``mbo``.
  Book reconstruction applies add / modify / cancel / trade / clear MBO
  actions to a per-side aggregated level dict. DOM snapshots flow through
  ``SharedState.dom.update()`` at a 10ms cadence. Trades route to each
  registered ``BarBuilder.on_trade`` which enforces RTH + FreezeGuard
  gates (D-15..D-17).
- **``deep6/data/factory.py``** — ``create_feed("databento", cfg)`` now
  picks ``config.databento_live_key()`` (GLBX-scoped → primary fallback)
  and raises a clear ``RuntimeError`` if neither key is present.
- **``deep6/config.py``** — new ``databento_api_key_glbx`` field,
  ``DATABENTO_API_KEY_GLBX`` env loading, and
  ``databento_live_key()`` helper.
- **Tests** — 10 new tests added (7 factory/key-selection, 3 real-MBO
  replay integration). Together with the 15 preexisting unit tests for
  ``_OrderBookState`` / aggressor / RTH / FreezeGuard this phase ships
  with 25 passing tests covering D-09..D-24.

## Verification

- ``.venv/bin/python -m pytest tests/test_databento_live.py
  tests/test_data_factory.py tests/integration/test_databento_live_replay.py
  -x -q`` → **25 passed**.
- ``scripts/run_live.py --source=live --data-source=databento --port 8765``
  launched cleanly, connected to the Databento Live gateway, authenticated
  (``session_id='1777726029'``), and subscribed to
  ``GLBX.MDP3 / mbo / NQ.c.0`` before the gateway returned
  ``Not authorized for mbo schema`` for the active Databento account. All
  startup logs (bridge ready, SharedState build, bar builders, subscribed,
  auth) fired as expected — the only missing step is the server-side
  entitlement on the account.
- Integration replay against
  ``data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst``
  confirms the full MBO → DOM + FootprintBar path reconstructs a
  non-empty top-of-book with a positive spread and accumulates trades
  into the current bar.

## Open issues

- **Databento account MBO entitlement**: both the primary key and the
  GLBX key return ``Not authorized for mbo schema``. Subscribing to
  ``trades`` and ``tbbo`` on the same account succeeds, so the plumbing
  is correct. Before full live trading, either upgrade the Databento
  plan to include CME MDP 3.0 MBO live entitlement or provision a
  dedicated GLBX-entitled key. No code change needed — the feed will
  start working as soon as the subscription response carries MBO
  records.
- **Live DOMState equivalence against bmoscon** — Phase 13 already has
  ``tests/backtest/test_dom_equivalence.py`` proving equivalence for the
  backtest path. A second equivalence test cross-comparing the live
  ``_OrderBookState`` and bmoscon on identical MBO streams is listed as
  a ``deferred`` follow-up — the replay integration test covers the
  end-to-end reconstruction for now.

## Files

- **New**: ``deep6/data/databento_live.py`` (already present; schema
  fixed), ``tests/test_data_factory.py``,
  ``tests/integration/test_databento_live_replay.py``,
  ``.planning/phases/14-databento-live-feed/14-01-PLAN.md``,
  ``.planning/phases/14-databento-live-feed/14-01-SUMMARY.md``.
- **Modified**: ``deep6/config.py``, ``deep6/data/factory.py``,
  ``deep6/data/databento_live.py``.

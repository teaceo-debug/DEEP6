# DEEP6 Edge Research Skill

## Purpose

This skill equips agents to conduct rigorous, reproducible backtesting research
on the DEEP6 signal engine — specifically DOM/order flow signals on NQ futures.
It covers the full research loop: data access → signal collection → attribution
analysis → edge identification → hypothesis testing.

## When to load this skill

Load this skill when any agent is asked to:
- Find which DEEP6 signals have real edge
- Test a signal or combination hypothesis
- Run backtests on DOM / footprint / order flow signals
- Build new signal detectors and measure their alpha
- Run signal attribution after downloading Databento MBO data
- Answer "does X signal work?" or "what's the best time of day for Y signal?"
- Compare signal performance across market regimes

## Skill entry point

1. Read `knowledge.md` — master framework, data paths, signal taxonomy
2. Read the relevant playbook for your task:
   - `playbooks/signal-attribution.md` — run and interpret attribution
   - `playbooks/mbo-backtesting.md` — MBO-specific testing (Databento data)
   - `playbooks/dom-signal-dev.md` — building and testing new DOM signals
   - `playbooks/hypothesis-testing.md` — testing specific edge hypotheses
3. Read `data/signal-taxonomy.md` — full 44-signal reference with categories

## Multi-agent parallelization

This skill is designed for PARALLEL agent workstreams. Each agent takes one category:

| Agent | Focus | Command |
|-------|-------|---------|
| Agent A | Absorption + Exhaustion | `python scripts/signal_analyze.py --category absorption` |
| Agent B | Imbalance + Delta | `python scripts/signal_analyze.py --category imbalance` |
| Agent C | Volume Profile + Auction | `python scripts/signal_analyze.py --category volume_profile` |
| Agent D | DOM engines (ENG_02-05) | `python scripts/signal_analyze.py --signal ENG_02,ENG_03,ENG_04,ENG_05` |
| Agent E | Trap + Vol Patterns | `python scripts/signal_analyze.py --category trapped` |
| Agent F | Pair synergy research | `python scripts/signal_analyze.py --no-pairs` then pair drill-down |
| Agent G | Time-of-day research | Query signal_events.csv directly, group by hour |
| Agent H | Regime-conditioned edge | Filter signal_events.csv by trend/mean-reversion periods |

## Knowledge Base (load for deep research tasks)

| File | Contents | When to load |
|------|----------|-------------|
| `knowledge/mbo-strategy-taxonomy.md` | All 22 manipulation patterns with MBO signatures, detection algorithms, counter-strategies | Any spoof/iceberg/layering/absorption work |
| `knowledge/mbo-algorithms.md` | Complete Python implementations: OFI, Kyle's λ, Hawkes, VPIN, queue tracker, iceberg detector, spoof detector, feature vector | Building or debugging detectors |
| `knowledge/institutional-architecture.md` | Full 9-layer system blueprint: data → book → signals → levels → features → LLM → classifiers → decisions → execution | Architecture decisions, new component design |
| `knowledge/nq-strategy-library.md` | NQ-specific strategies: ORB, VWAP reversion, stop sweeps, options-futures interaction, HFT signatures | Strategy development, hypothesis generation |

## Base path

`C:\Users\Tea\DEEP6\.claude\skills\deep6-edge-research\`

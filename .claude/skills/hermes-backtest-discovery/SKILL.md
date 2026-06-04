# hermes-backtest-discovery — DEEP6 Autonomous Backtest Discovery

Invoke this skill when the user asks you to:
- Run backtest loop, run discovery iteration, run one backtest
- Discover entry strategies, find entry models, test entry models
- Backtest against MBO data, evaluate strategies on MBO data
- Continue strategy evolution, evolve strategies, iterate strategies
- Read backtest loop state, describe what strategies have been tested
- Summarize discovery progress, report best strategy found

## Skill Entry Point

Load `knowledge.md` in this directory first for complete iteration protocol, data paths, CLI commands, strategy config reference, fitness criteria, mutation strategy, and Obsidian write protocol.

## Workflow

1. **Read brain state** — Load brain/Backtest-Loop.md + query DuckDB for iteration history
2. **Decide action** — First run: generate; subsequent: mutate best; every 5th: explore random
3. **Generate config** — Use mutation_engine or param_bounds defaults; validate with config_validator
4. **Run backtest** — Execute scripts/backtest_loop.py via CLI; capture JSON output
5. **Evaluate + write** — Check fitness criteria; write to DuckDB + Obsidian; print NEXT ACTION

## Dependencies

None — self-contained skill

## Base path: `C:\Users\Tea\DEEP6\.claude\skills\hermes-backtest-discovery\`

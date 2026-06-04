# NT8 Install / Repair Skill

Invoke this skill when the user wants to:
- install NinjaTrader 8 on a fresh machine
- uninstall NinjaTrader 8 cleanly
- repair a broken NT8 install
- recover from startup loops, database corruption, or config corruption
- reconnect platform setup after a reinstall

## Entry Point

1. Load `knowledge.md` in this directory first.
2. Determine whether the task is **fresh install**, **repair in place**, **clean uninstall**, or **rebuild after corruption**.
3. Prefer the smallest safe repair before recommending a destructive reinstall.

## Invariants

- Always protect user data first: back up workspaces, templates, `Config.xml`, and DB files before destructive actions.
- Distinguish platform problems from NinjaScript problems; do not reinstall NT8 just because one indicator fails to compile.
- If the issue is compile-only, hand off to `nt8-fix` instead.
- If the issue is strategy/runtime configuration after install, hand off to `nt8-strategy-operations`.

## OpenCode Skills (Universal NT8 Knowledge)

Use these when broader NT8 platform knowledge is needed:
- `ninjatrader-machine-profile`
- `ninjatrader-error-doctor`

# NT8 Install / Repair Knowledge Base

## Scope

This skill handles platform lifecycle work:
- install
- uninstall
- repair
- corruption recovery
- first-launch validation

It is the right skill when NT8 itself is unhealthy.

## Machine Paths

| Purpose | Path |
|---|---|
| NT8 root | `C:\Users\Tea\Documents\NinjaTrader 8\` |
| Custom source | `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\` |
| Workspaces | `C:\Users\Tea\Documents\NinjaTrader 8\workspaces\` |
| Logs | `C:\Users\Tea\Documents\NinjaTrader 8\log\` |
| DB | `C:\Users\Tea\Documents\NinjaTrader 8\db\` |
| Primary DB concern | `C:\Users\Tea\Documents\NinjaTrader 8\db\NinjaTrader.sqlite` |
| Repo install guide | `C:\Users\Tea\DEEP6\ninjatrader\deploy\INSTALL-EVERYTHING.md` |

## Repair Decision Tree

### A. Fresh install
Use when NT8 is not present or the machine is new.

1. Install NT8.
2. Launch once so the `Documents\NinjaTrader 8\` tree is created.
3. Confirm `bin\Custom\` exists.
4. Confirm NT8 starts cleanly before deploying DEEP6 code.
5. Use `INSTALL-EVERYTHING.md` for full DEEP6 deployment and initial configuration.

### B. Repair in place
Use when NT8 exists but startup, menus, editor, or indicators are behaving abnormally.

1. Confirm whether the issue is platform-wide or file-specific.
2. Back up:
   - `Config.xml`
   - `db\`
   - `workspaces\`
   - any custom templates the user cares about
3. Check for recent log errors under `log\`.
4. If startup loops or DB errors point to persistence corruption, move to corruption recovery.
5. If files are missing or system indicators disappeared, use NT8 repair/reinstall flow.

### C. Corruption recovery
Known DEEP6 lesson from prior sessions:

- `db\NinjaTrader.sqlite` can become corrupt enough for integrity checks to fail.
- Startup can loop on persisted DEEP6 strategy rows.

Recovery pattern:
1. Stop NT8 completely.
2. Back up `db\` and `Config.xml`.
3. Rebuild or replace corrupted DB files.
4. Purge bad persisted strategy rows if the loop is tied to a broken strategy entry.
5. Restart NT8 cleanly.
6. Only after platform stability is restored, redeploy/recompile DEEP6 code.

### D. Clean uninstall / reinstall
Use only when targeted repair is not enough.

1. Export or back up anything user-created first.
2. Remove NT8 through Windows uninstall flow.
3. Remove leftover state only if the goal is a truly clean rebuild.
4. Reinstall NT8.
5. Launch once before restoring or redeploying DEEP6 artifacts.

## First-Launch Validation Checklist

After install or repair, verify all of these before moving on:

1. NT8 launches without crash or loop.
2. `C:\Users\Tea\Documents\NinjaTrader 8\bin\Custom\` exists.
3. NinjaScript Editor opens.
4. Output Window opens.
5. Compile can be triggered.
6. Connection configuration menu is accessible.
7. Chart window can be opened.

## DEEP6-Specific Follow-On Skills

After install/repair, route to the next correct skill:

- deploy/build work → `nt8-build-verify`
- broken NinjaScript → `nt8-fix`
- account/ATM/enablement work → `nt8-strategy-operations`
- on-chart proof and acceptance → `nt8-chart-verification`

## Do Not Confuse These Cases

- **Compile error** != platform corruption
- **Indicator not visible** != reinstall trigger
- **ATM template missing** != build failure
- **Tick replay disabled on chart** != broken indicator

Repair the actual failing layer, not the loudest symptom.

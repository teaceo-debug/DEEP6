# DEEP6 Agent-to-Agent Communication Protocol

## How Mac Claude and Windows Claude Talk

Both agents use **GitHub Issues** as a message bus. No extra infrastructure. No merge conflicts. Both already have `gh` CLI access.

---

## Message Types

### Mac → Windows (labels: `from-mac`)

| Type | Title Format | When |
|------|-------------|------|
| DEPLOY | `[DEPLOY] description of changes` | After pushing new code |
| CONFIG | `[CONFIG] parameter changes` | After optimization produces new values |
| REQUEST | `[REQUEST] what you need` | Asking Windows to do something |
| QUESTION | `[QUESTION] what you need to know` | Asking for info from NT8 |

### Windows → Mac (labels: `from-windows`)

| Type | Title Format | When |
|------|-------------|------|
| STATUS | `[STATUS] daily report YYYY-MM-DD` | End of each RTH session |
| ERROR | `[ERROR] CS#### or runtime description` | Compile or runtime failure |
| CAPTURE | `[CAPTURE] N sessions recorded` | New NDJSON files pushed |
| ANSWER | `[ANSWER] re: original question` | Response to a Mac question |
| ALERT | `[ALERT] critical issue` | Something needs immediate attention |

---

## Protocol Rules

### Rule 1: Every message is a GitHub Issue

```bash
# Mac sending a deploy notification:
gh issue create \
  --title "[DEPLOY] R3 weight optimization — imbalance=25, abs=20" \
  --body "Pushed commit abc1234. Changes: ConfluenceScorer weights updated per R3 optimization. Windows agent should pull and recompile." \
  --label "from-mac"

# Windows reporting compile success:
gh issue create \
  --title "[STATUS] Compile clean — 0 errors, strategy running" \
  --body "Pulled abc1234. F5 compile: 0 errors. Strategy reloaded. First scorer output: [DEEP6 Scorer] bar=1 score=+54.20 tier=TYPE_C" \
  --label "from-windows"
```

### Rule 2: Close issues when handled

```bash
# Windows closes the deploy issue after successful compile:
gh issue close 42 --comment "Deployed and running. Compile clean."

# Mac closes the capture issue after pulling the data:
gh issue close 45 --comment "Captured sessions pulled. Running Round 4 optimizer."
```

### Rule 3: Check for messages every cycle

**Mac agent** (at start of each session):
```bash
# Read unresolved messages from Windows
gh issue list --label "from-windows" --state open --json number,title,body,createdAt
```

**Windows agent** (every 5-min poll):
```bash
# Read unresolved messages from Mac
gh issue list --label "from-mac" --state open --json number,title,body,createdAt
```

### Rule 4: Priority handling

| Priority | Label | Response time |
|----------|-------|---------------|
| ALERT | `urgent` | Immediate (next poll cycle) |
| ERROR | `from-windows` | Next Mac session |
| DEPLOY | `from-mac` | Next Windows poll (5 min) |
| STATUS | `from-windows` | Informational — no response needed |

---

## Setup (One-Time)

### On both machines, authenticate GitHub CLI:

```bash
gh auth login
```

### Create the labels:

```bash
gh label create "from-mac" --color "0E8A16" --description "Message from Mac Claude"
gh label create "from-windows" --color "1D76DB" --description "Message from Windows Claude"
gh label create "urgent" --color "D93F0B" --description "Needs immediate attention"
```

---

## Example Conversation

### Scenario: Mac pushes new code, Windows compiles and reports back

**Step 1 — Mac pushes code + creates issue:**
```bash
git push origin main

gh issue create \
  --title "[DEPLOY] Phase 18 Wave 2 — HUD badge + tier markers" \
  --body "Commit f25368e pushed. Adds SharpDX HUD rendering + Draw.Diamond/Triangle tier markers to DEEP6Footprint.cs OnRender. Windows: pull, compile, verify HUD appears on live chart." \
  --label "from-mac"
```

**Step 2 — Windows polls, sees the issue, acts:**
```bash
# Check for Mac messages
gh issue list --label "from-mac" --state open

# Pull and deploy
git pull origin main
xcopy ninjatrader\Custom\Indicators\DEEP6 "$dest\Indicators\DEEP6\" /E /I /Y

# NT8 auto-recompiles...

# Report back
gh issue create \
  --title "[STATUS] HUD badge rendering — VERIFIED" \
  --body "Compiled clean. HUD badge visible top-right showing Score: +62.40 / Tier: TYPE_C. Tier markers not yet visible (no TYPE_B entry on current session). Screenshot description: gold POC line at 20045, olive VA lines, profile anchors on right gutter, HUD box 384x80px with dark background." \
  --label "from-windows"

# Close the deploy issue
gh issue close 12 --comment "Deployed and verified."
```

**Step 3 — Mac reads the status, decides next action:**
```bash
gh issue list --label "from-windows" --state open
# Sees the HUD verification — proceeds to Wave 3
gh issue close 13 --comment "Acknowledged. Proceeding to scorer migration."
```

### Scenario: Windows hits a compile error

**Windows detects error:**
```bash
gh issue create \
  --title "[ERROR] CS0246: SignalTier not found in ScorerEntryGate.cs line 42" \
  --body "After pulling commit def5678, NT8 compile failed:

\`\`\`
error CS0246: The type or namespace name 'SignalTier' could not be found
File: AddOns\DEEP6\Scoring\ScorerEntryGate.cs
Line: 42
\`\`\`

Attempted fix: added \`using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;\` — still fails.
Need Mac agent to check if SignalTier was moved or renamed in the last commit." \
  --label "from-windows" --label "urgent"
```

**Mac sees the urgent issue, fixes, pushes:**
```bash
# Read the error
gh issue view 15

# Fix the code
# ... edit ScorerEntryGate.cs ...

git add . && git commit -m "fix(nt8): restore SignalTier import in ScorerEntryGate"
git push origin main

gh issue comment 15 --body "Fixed in commit ghi9012. SignalTier enum was moved to Registry namespace in last refactor. Added the using directive. Please pull and recompile."
```

**Windows pulls fix, compiles, closes:**
```bash
git pull origin main
# ... recompile ...
gh issue close 15 --comment "Fix confirmed. Compile clean. Strategy running."
```

### Scenario: Windows captures live sessions for Mac to optimize

**Windows after a good trading day:**
```bash
# Copy captures to repo
copy "$captures\2026-04-17-session.ndjson" "$repo\ninjatrader\captures\"
copy "$captures\2026-04-18-session.ndjson" "$repo\ninjatrader\captures\"
git add ninjatrader/captures/
git commit -m "data(vm): 2 live RTH sessions captured (Apr 17-18)"
git push origin main

gh issue create \
  --title "[CAPTURE] 2 live sessions ready — Apr 17-18" \
  --body "Pushed 2 NDJSON captures to ninjatrader/captures/:
- 2026-04-17-session.ndjson (389 bars, 14 signals, 2 dry-run entries)
- 2026-04-18-session.ndjson (391 bars, 22 signals, 4 dry-run entries)

Ready for Round 4 optimization on real data." \
  --label "from-windows"
```

**Mac pulls and optimizes:**
```bash
git pull origin main

# Run optimizer on real data
python3 -m deep6.backtest.vbt_harness --mode sweep \
  --sessions-dir ninjatrader/captures/ \
  --output-dir ninjatrader/backtests/results-live/

# If results suggest config changes:
gh issue create \
  --title "[CONFIG] Round 4 results — threshold 70→65, imbalance weight 25→28" \
  --body "Live data optimization complete. 2 sessions, 6 entries. Results:
- Current config: Sharpe=1.2, PF=2.8
- Proposed: threshold=65, imb_weight=28 → Sharpe=1.8, PF=3.4

Pushing code change now." \
  --label "from-mac"

git push origin main
```

---

## Automation: Windows Agent Issue Polling

Add this to the Windows agent's core loop (in WINDOWS-AI-AGENT.md step 1):

```powershell
# Check for Mac messages before git pull
$macIssues = gh issue list --label "from-mac" --state open --json number,title,body | ConvertFrom-Json

foreach ($issue in $macIssues) {
    Write-Host "Message from Mac: $($issue.title)"

    if ($issue.title -match "^\[DEPLOY\]") {
        Write-Host "  → Deploy requested. Pulling..."
        # Continue to PULL step
    }
    elseif ($issue.title -match "^\[CONFIG\]") {
        Write-Host "  → Config change. Pulling and recompiling..."
        # Continue to PULL step
    }
    elseif ($issue.title -match "^\[REQUEST\]") {
        Write-Host "  → Request from Mac. Processing..."
        # Parse body for specific request
    }
}
```

## Automation: Mac Agent Issue Check

Add this to your Mac Claude Code session startup:

```bash
# Check what Windows reported since last session
gh issue list --label "from-windows" --state open --json number,title,createdAt | jq '.[] | "\(.createdAt) \(.title)"'
```

---

## Dashboard View

At any time, see the full conversation:

```bash
# All open messages
gh issue list --state open --json number,title,labels,createdAt

# Full history
gh issue list --state all --limit 50 --json number,title,labels,state,createdAt
```

---

*Communication Protocol v1.0*
*Channel: GitHub Issues on teaceo-debug/DEEP6*
*No extra infrastructure. No merge conflicts. Searchable history.*

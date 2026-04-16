# .handoff/ — Cross-Machine AI Communication Channel

This directory enables seamless communication between AI assistants running on different machines (Mac + Windows) without email or copy-paste.

## How It Works

1. **Mac (Claude Code)** writes a task to `.handoff/to-windows.md`
2. Mac commits + pushes to GitHub
3. **Windows (OpenCode)** pulls, reads `.handoff/to-windows.md`, executes the task
4. Windows writes results to `.handoff/to-mac.md`
5. Windows commits + pushes
6. Mac pulls and reads the results

## Protocol

### Sending a task (either direction):

Write to `to-windows.md` or `to-mac.md`:

```markdown
---
from: mac
to: windows
status: pending
timestamp: 2026-04-16T06:00:00Z
---

## Task

[What needs to be done]

## Context

[Files to read, background info]

## Expected Result

[What success looks like]
```

### Completing a task:

Update the same file, change status to `done`:

```markdown
---
from: windows
to: mac
status: done
timestamp: 2026-04-16T06:15:00Z
---

## Result

[What was accomplished]

## Issues

[Any problems encountered]

## Files Changed

[List of files modified]
```

## Automation

On each machine, the AI can poll for new tasks:

```bash
# Pull and check for pending tasks (run periodically or before starting work)
git pull origin main
cat .handoff/to-mac.md    # on Mac
cat .handoff/to-windows.md  # on Windows
```

## Current Machines

| Machine | OS | AI Tool | Role |
|---------|-----|---------|------|
| Mac | macOS | Claude Code | Simulator development, analytics, Python |
| Windows | Windows | OpenCode | NinjaTrader 8, NT8 compilation, live trading |

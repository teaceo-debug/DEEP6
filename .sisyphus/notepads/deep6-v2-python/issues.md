# Issues — deep6-v2-python

(None yet — session just started)

## [2026-05-23] Evidence command quoting
- Inline `python -c` QA commands on PowerShell are easy to break with nested quotes.
- Use `& python -c "..."` with Python triple-quoted SQL strings when capturing evidence output.

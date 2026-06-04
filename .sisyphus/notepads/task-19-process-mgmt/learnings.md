## Learnings

- GEX Terminal now has a dedicated structured logger module with rotating file output and JSONL audit support.
- PID lock enforcement belongs in `__main__.py` before server start and should be skipped for `--dry-run`.
- `os.kill(pid, 0)` is sufficient for detecting a live PID here; stale PID files can be removed safely.

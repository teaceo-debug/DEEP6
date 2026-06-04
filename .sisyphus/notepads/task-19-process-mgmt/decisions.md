## Decisions

- Logging target: `~/.deep6/gexdoctor_v2.log` with 10MB rotation and 3 backups.
- Audit target: `~/.deep6/gexdoctor_v2_audit.jsonl` using newline-delimited JSON records.
- Shutdown scope kept minimal: only `SIGINT` and `SIGTERM`, plus `atexit` cleanup.

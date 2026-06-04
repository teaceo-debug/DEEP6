2026-05-28: Kept API keys out of config.yaml and relied on BaseSettings/env overrides only.
2026-05-28: Used a flattened from_yaml loader so sectioned YAML can remain readable without requiring nested Pydantic models.
2026-05-28: Implemented FlashAlpha as a fresh adapter with run_in_executor wrapping and direct httpx fallback instead of importing nq_atlas client code.
2026-05-28: Implemented GEXDoctor as an overlay-only Draw.* indicator that polls the enriched JSON on-bar at a configurable interval instead of adding timers or SharpDX dependencies.
2026-05-28: Kept launch.py as the canonical CLI implementation and turned gexdoctor.py into a thin compatibility wrapper so python -m gexdoctor resolves correctly in this repo layout.

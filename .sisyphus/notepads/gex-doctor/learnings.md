2026-05-28: Implemented stdlib-only structured logging for gexdoctor with a JSONL file handler plus human-readable console handler.
2026-05-28: BaseSettings config works cleanly with flattened YAML sections and GEXDOCTOR_* env overrides.
2026-05-28: FlashAlpha live bundle parsing must ignore top-level live_gex_delta for DEX and instead read flow_adjusted_dealer_risk.live_net_dex; missing live_net_dex is surfaced through feed_quality.missing_fields.
2026-05-28: FlashAlpha adapter freshness is carried through feed_quality.latency_seconds and a "stale" marker once bundle as_of age exceeds 120 seconds.
2026-05-28: NT8 Draw.HorizontalLine with stable tags updates GEX levels cleanly in place; pairing each line with a Draw.Text label tag gives simple, SharpDX-free chart annotations.
2026-05-28: The gexdoctor package had a top-level gexdoctor.py shadowing the intended module entrypoint, so python -m gexdoctor needed a shim that proxies to launch.main().
2026-05-28: Windows console encoding can choke on Unicode arrows in argparse help text; ASCII-only CLI strings kept --help stable.
2026-05-28: Integration coverage for gexdoctor is cleanest when the producer uses real interpreter/scorer logic with only adapter and price service mocked; FlashAlpha raw fixture payloads can be turned into snapshots through FlashAlphaAdapter._parse_live_bundle without any live API access.
2026-05-28: The most stable way to test producer price fallback is to seed producer._last_output directly, then force price_service.get_nq_quote() to raise; that isolates fallback semantics from multi-cycle AsyncMock sequencing.

"""E6 VP+Context Engine and E7 ML Quality Engine.

E6VPContextEngine (ENG-06): Wires POCEngine + SessionProfile + GexEngine + ZoneRegistry
into a single process() call, returning a unified VPContextResult per bar close.

E7MLQualityEngine (ENG-07): Stub returning 1.0 (neutral quality multiplier) until
Phase 9 implements Kalman filter + XGBoost classifier with 16+ features.

Per CONTEXT.md D-06, D-07: ZoneRegistry consolidation and confluence scoring live here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from deep6.engines.gex import GexEngine, GexSignal
from deep6.engines.poc import POCEngine, POCSignal
from deep6.engines.signal_config import GexConfig, POCConfig, VolumeProfileConfig
from deep6.engines.volume_profile import SessionProfile, VolumeZone
from deep6.engines.zone_registry import ConfluenceResult, ZoneRegistry
from deep6.state.footprint import FootprintBar


@dataclass
class VPContextResult:
    """Output of E6VPContextEngine.process() — unified context for one bar close."""
    poc_signals: list[POCSignal] = field(default_factory=list)
    gex_signal: Optional[GexSignal] = None
    active_zones: list[VolumeZone] = field(default_factory=list)
    zone_events: list[str] = field(default_factory=list)
    confluence: Optional[ConfluenceResult] = None
    poc_migration: tuple[int, float] = (0, 0.0)  # (direction, velocity) — VPRO-08
    ml_quality: float = 1.0                       # E7 quality multiplier


class E6VPContextEngine:
    """E6 VP+Context Engine — the macro context layer for all signal scoring.

    Maintains session-level volume profile, POC state, GEX levels, and
    zone lifecycle. Every bar close produces a VPContextResult consumed by
    the Phase 7 confluence scorer.

    ENG-06: DEX-ARRAY + VWAP/IB/GEX/POC with LVN zone lifecycle.
    """

    def __init__(
        self,
        gex_api_key: str,
        poc_config: POCConfig | None = None,
        vp_config: VolumeProfileConfig | None = None,
        gex_config: GexConfig | None = None,
    ):
        self.poc_engine = POCEngine(config=poc_config)
        self.session_profile = SessionProfile(config=vp_config)
        self.gex_engine = GexEngine(api_key=gex_api_key, config=gex_config)
        self.registry = ZoneRegistry()
        self._bar_count: int = 0
        self._ml_engine = E7MLQualityEngine()

    def process(self, bar: FootprintBar) -> VPContextResult:
        """Process one bar close. Returns unified VP+Context result.

        Steps:
          1. Accumulate bar volume into session profile (VPRO-01)
          2. Detect new LVN/HVN zones and load into registry (VPRO-02/03, ZONE-01)
          3. Update zone lifecycle — fired events returned as strings (VPRO-04)
          4. Process POC signals from bar (POC-01..08)
          5. Get GEX signal for current price (GEX-02..05)
          6. Check cross-type confluence (ZONE-02)
          7. Return VPContextResult
        """
        self._bar_count += 1

        # 1. Accumulate bar volume
        self.session_profile.add_bar(bar)

        # 2. Detect new zones -> load into registry
        new_zones = self.session_profile.detect_zones(bar.close)
        for z in new_zones:
            self.registry.add_zone(z)

        # 3. Update zone lifecycle
        zone_events = self.session_profile.update_zones(bar, self._bar_count)

        # 4. POC signals
        poc_signals = self.poc_engine.process(bar)
        poc_migration = self.poc_engine.get_migration()

        # 5. GEX signal
        gex_signal = self.gex_engine.get_signal(bar.close)

        # 6. Confluence check
        confluence = self.registry.get_confluence(bar.close)

        # 7. Active zones
        active_zones = self.registry.get_all_active()

        return VPContextResult(
            poc_signals=poc_signals,
            gex_signal=gex_signal,
            active_zones=active_zones,
            zone_events=zone_events,
            confluence=confluence,
            poc_migration=poc_migration,
            ml_quality=self._ml_engine.score(bar),
        )

    def fetch_gex(self, spot_price: float) -> None:
        """Fetch GEX levels from API and load into registry. Call every ~60s.

        GEX-01: ingestion from Polygon API via GexEngine.
        GEX-02: levels available as price points in ZoneRegistry.
        """
        levels = self.gex_engine.fetch_and_compute(spot_price)
        self.registry.add_gex_levels(levels)

    def on_session_start(self, prior_bins: dict | None = None) -> None:
        """Reset for new session. Pass prior_bins for multi-session persistence.

        VPRO-07: prior session bins are decay-weighted (session_decay_weight=0.70).
        """
        vp_config = self.session_profile.config
        self.session_profile = SessionProfile(config=vp_config, prior_bins=prior_bins)
        self.registry.clear()
        self.poc_engine.reset()
        self._bar_count = 0


class E7MLQualityEngine:
    """E7 ML Quality Engine — stub returning neutral multiplier.

    Returns 1.0 (no adjustment) until Phase 9 implements:
      - Kalman filter for online signal weight estimation
      - XGBoost classifier with 16+ features for quality scoring
      - Per-regime quality adjustments

    ENG-07: ML quality multiplier for confluence scorer.
    """

    def score(self, bar: FootprintBar | None = None) -> float:
        """Return quality multiplier. Always 1.0 (neutral) until Phase 9.

        Phase 9 will replace this with XGBoost.score(features) -> float in [0.5, 1.5].
        """
        return 1.0

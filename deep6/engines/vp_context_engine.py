"""E6 VP+Context Engine and E7 ML Quality Engine.

E6VPContextEngine (ENG-06): Wires POCEngine + SessionProfile + GexEngine + ZoneRegistry
into a single process() call, returning a unified VPContextResult per bar close.

E7MLQualityEngine (ENG-07): Returns a dynamic quality multiplier driven by live deployed
weights (Phase 9). Falls back to 1.0 (neutral) when no weight_loader is provided or
no weight file has been deployed yet.

Per CONTEXT.md D-06, D-07: ZoneRegistry consolidation and confluence scoring live here.
Per T-09-14: Weight file re-read uses mtime caching inside WeightLoader.read_current()
             to avoid repeated disk I/O on every bar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from deep6.engines.gex import GexEngine, GexSignal
from deep6.engines.poc import POCEngine, POCSignal
from deep6.engines.signal_config import GexConfig, POCConfig, VolumeProfileConfig
from deep6.engines.volume_profile import SessionProfile, VolumeZone
from deep6.engines.zone_registry import ConfluenceResult, ZoneRegistry
from deep6.state.footprint import FootprintBar

if TYPE_CHECKING:
    from deep6.ml.weight_loader import WeightLoader
    from deep6.ml.hmm_regime import HMMRegimeDetector


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
    """E7 ML Quality Engine — live weight quality multiplier.

    Reads deployed weights from WeightLoader on each bar (mtime-cached per T-09-14).
    Returns a quality multiplier in [0.5, 1.5] derived from the mean signal weight.

    Falls back to 1.0 (neutral) when:
    - weight_loader is None (backward-compatible stub mode)
    - No weight file has been deployed yet
    - Weight file is unreadable

    Optionally adjusts by HMM regime if regime_detector is provided and fitted.

    ENG-07: ML quality multiplier for confluence scorer.
    Per T-09-14: File read is mtime-cached inside WeightLoader — re-reads only on change.
    """

    def __init__(
        self,
        weight_loader: Optional["WeightLoader"] = None,
        regime_detector: Optional["HMMRegimeDetector"] = None,
    ) -> None:
        """Initialise E7MLQualityEngine.

        Args:
            weight_loader:    WeightLoader instance for reading deployed weights.
                              If None, engine operates in stub mode (returns 1.0).
            regime_detector:  HMMRegimeDetector for optional regime-based adjustment.
                              If None or not fitted, no regime adjustment is applied.
        """
        self._weight_loader = weight_loader
        self._regime_detector = regime_detector

    def score(self, bar: FootprintBar | None = None) -> float:
        """Return quality multiplier based on deployed weights.

        Computation:
          1. If no weight_loader → return 1.0 (stub mode).
          2. Read current weights (mtime-cached — O(1) when file unchanged).
          3. If no weights data → return 1.0.
          4. Compute mean of signal weights and clamp to [0.5, 1.5].
          5. If regime_detector is fitted, apply regime_adjustments multiplier.

        Returns:
            float in [0.5, 1.5] — quality multiplier for confluence scorer.
        """
        if self._weight_loader is None:
            return 1.0

        data = self._weight_loader.read_current()
        if data is None:
            return 1.0

        weights: dict[str, float] = data.get("weights", {})
        if not weights:
            return 1.0

        # Base quality = mean of all signal weights, clamped to [0.5, 1.5]
        quality = sum(weights.values()) / len(weights)
        quality = max(0.5, min(1.5, quality))

        # Optional regime adjustment
        if self._regime_detector is not None and self._regime_detector.is_fitted():
            regime_adjustments: dict = data.get("regime_adjustments", {})
            if regime_adjustments and bar is not None:
                # Use last known regime (predict_current requires signal rows —
                # here we apply a stored per-regime multiplier from the weight file)
                # regime_adjustments shape: {regime_label: {signal: float}}
                # For quality adjustment we use a dedicated "quality_multiplier" key
                # if present, otherwise skip.
                for regime_label, adj in regime_adjustments.items():
                    if isinstance(adj, dict):
                        multiplier = adj.get("quality_multiplier")
                        if multiplier is not None:
                            quality = max(0.5, min(1.5, quality * float(multiplier)))
                            break

        return quality

    # Alias for plan compatibility (process is the standard engine method name)
    def process(self, bar: FootprintBar | None = None) -> float:
        """Alias for score() — standard engine process() interface."""
        return self.score(bar)

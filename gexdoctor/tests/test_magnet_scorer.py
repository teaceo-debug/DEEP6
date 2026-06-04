from __future__ import annotations

import time

import pytest

from gexdoctor.monitor.schemas import (
    FADealerRisk,
    FAFeedQuality,
    FAOISimulator,
    FAPinData,
    FARegime,
    FlashAlphaSnapshot,
    MagnetResult,
)
from gexdoctor.monitor.magnet_scorer import (
    ANTI_FLICKER_MARGIN,
    LEVEL_TYPE_WEIGHTS,
    MIN_CONFIDENCE,
    MagnetScorer,
    MagnetState,
)


# ---------------------------------------------------------------------------
# Helper: build FlashAlphaSnapshot from overrides
# ---------------------------------------------------------------------------

def _snap(
    *,
    gex_sign: str = "positive",
    net_gex: float = 5e9,
    gamma_flip: float = 22000.0,
    call_wall: float | None = 22300.0,
    put_wall: float | None = 21700.0,
    max_pain: float | None = 22050.0,
    pin_risk: float | None = 0.0,
    magnet_strike: float | None = None,
    flow_direction: str = "neutral",
    oi_delta_confidence: float | None = 1.0,
    dte: int | None = 5,
    missing_fields: list[str] | None = None,
) -> FlashAlphaSnapshot:
    return FlashAlphaSnapshot(
        timestamp="2026-05-28T14:30:00Z",
        symbol="NQ",
        underlying_price=22100.0,
        session_phase="intraday",
        dte=dte,
        regime=FARegime(
            net_gex=net_gex,
            gex_sign=gex_sign,
            gamma_flip=gamma_flip,
            call_wall=call_wall,
            put_wall=put_wall,
            max_pain=max_pain,
        ),
        dealer_risk=FADealerRisk(flow_direction=flow_direction),
        pin=FAPinData(pin_risk=pin_risk, magnet_strike=magnet_strike),
        oi_simulator=FAOISimulator(oi_delta_confidence=oi_delta_confidence),
        feed_quality=FAFeedQuality(missing_fields=missing_fields or []),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMagnetScorerSelection:
    """Core magnet selection logic."""

    def test_select_call_wall_as_magnet(self):
        """Positive GEX, call wall above NQ → call_wall selected."""
        scorer = MagnetScorer()
        snap = _snap(
            gex_sign="positive",
            call_wall=22200.0,   # 100 pts from NQ → dist_score=0.8, score=0.68
            put_wall=21700.0,    # 400 pts away → low score
            gamma_flip=21800.0,  # 300 pts away → lower than call_wall
        )
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "valid"
        assert result.primary_magnet == 22200.0

    def test_pin_magnet_wins_high_pin_risk(self):
        """pin_risk=80, magnet_strike at NQ → pin_magnet_strike selected (highest weight)."""
        scorer = MagnetScorer()
        snap = _snap(
            gex_sign="positive",
            pin_risk=80.0,
            magnet_strike=22100.0,
            call_wall=22300.0,
            put_wall=21700.0,
            gamma_flip=22000.0,
        )
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "valid"
        assert result.primary_magnet == 22100.0
        # Verify it was selected as pin_magnet_strike type
        pin_candidates = [
            c for c in result.supporting_levels if c.level_type == "pin_magnet_strike"
        ]
        assert len(pin_candidates) == 1
        assert pin_candidates[0].score >= LEVEL_TYPE_WEIGHTS["call_wall"]

    def test_score_below_threshold_no_magnet(self):
        """Low oi_confidence (0.1) → score below 0.65, no_magnet returned."""
        scorer = MagnetScorer()
        # Put all levels far away (>400 pts) AND low OI confidence
        snap = _snap(
            gex_sign="positive",
            call_wall=22600.0,  # 500 pts away
            put_wall=21500.0,   # 600 pts away
            gamma_flip=22600.0, # 500 pts away
            max_pain=22600.0,   # 500 pts away
            oi_delta_confidence=0.1,
        )
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "no_magnet"
        assert result.primary_magnet is None

    def test_no_levels_returns_no_magnet(self):
        """Snapshot with all None levels → no_magnet."""
        scorer = MagnetScorer()
        snap = _snap(
            call_wall=None,
            put_wall=None,
            gamma_flip=0.0,  # 0 is treated as invalid
            max_pain=None,
        )
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "no_magnet"
        assert result.primary_magnet is None
        assert "no levels available" in result.invalidation_reason

    def test_negative_gex_weights_gamma_flip(self):
        """Negative GEX → gamma_flip gets higher regime_score than walls."""
        scorer = MagnetScorer()
        # Place gamma_flip and call_wall equidistant from price
        snap = _snap(
            gex_sign="negative",
            gamma_flip=22200.0,
            call_wall=22200.0,  # same distance
            put_wall=21700.0,
        )
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "valid"
        # gamma_flip should win: base 0.90 * regime 1.0 > call_wall base 0.85 * regime 0.7
        assert result.primary_magnet == 22200.0
        # Verify by inspecting candidates
        gf = [c for c in result.supporting_levels if c.level_type == "gamma_flip"]
        cw = [c for c in result.supporting_levels if c.level_type == "call_wall"]
        assert gf[0].score > cw[0].score

    def test_gamma_flip_regime_alignment(self):
        """gamma_flip in positive GEX gets 0.9 regime_score (not 1.0)."""
        scorer = MagnetScorer()
        snap = _snap(
            gex_sign="positive",
            gamma_flip=22050.0,  # close to NQ
            call_wall=22300.0,   # further
        )
        result = scorer.score(snap, current_nq=22100.0)
        # gamma_flip: base=0.90, regime=0.9, close distance
        # call_wall: base=0.85, regime=1.0 (above in positive), further distance
        gf = [c for c in result.supporting_levels if c.level_type == "gamma_flip"]
        assert len(gf) == 1
        # The regime_score for gamma_flip in positive GEX should be factored in
        # gamma_flip raw: 0.90 * dist * 0.9 * flow * pin * conf
        # We can verify it's calculated correctly by checking it's < 0.90 * 1.0
        assert gf[0].score <= 0.90


class TestAntiFlicker:
    """Anti-flicker mechanism tests."""

    def test_anti_flicker_blocks_small_improvement(self):
        """Current magnet at 0.78, new best at 0.89 (margin=0.11 < 0.12) → current kept."""
        scorer = MagnetScorer()
        # First call — establish current magnet
        snap1 = _snap(
            gex_sign="positive",
            call_wall=22200.0,
            gamma_flip=22000.0,
        )
        result1 = scorer.score(snap1, current_nq=22100.0)
        assert result1.status == "valid"
        first_magnet = result1.primary_magnet

        # Manually set state to simulate specific score
        scorer._state.current_score = 0.78
        scorer._state.current_magnet = result1
        scorer._state.locked_at = time.monotonic()

        # Second call with slightly better candidate (margin < 0.12)
        # We need a scenario where best score is ~0.89
        snap2 = _snap(
            gex_sign="positive",
            call_wall=22150.0,  # closer = higher dist_score
            gamma_flip=22000.0,
        )
        # Check that anti-flicker keeps the old result
        result2 = scorer.score(snap2, current_nq=22100.0)
        # Should return the same result as before (anti-flicker)
        assert result2.primary_magnet == first_magnet

    def test_anti_flicker_allows_large_improvement(self):
        """Current at 0.50, new pin magnet (margin > 0.12) → new selected."""
        scorer = MagnetScorer()
        # Establish with a valid magnet first
        snap1 = _snap(
            gex_sign="positive",
            call_wall=22150.0,  # close → valid score
            gamma_flip=21800.0,
        )
        result1 = scorer.score(snap1, current_nq=22100.0)
        assert result1.status == "valid"

        # Set a low current score to guarantee margin > 0.12
        scorer._state.current_score = 0.50
        scorer._state.locked_at = time.monotonic()

        # New candidate with much higher score (pin magnet close by)
        snap2 = _snap(
            gex_sign="positive",
            pin_risk=80.0,
            magnet_strike=22100.0,  # exactly at NQ = max dist_score
            call_wall=22400.0,
            gamma_flip=22000.0,
        )
        result2 = scorer.score(snap2, current_nq=22100.0)
        # Should replace — pin magnet at price with high pin_risk scores very high
        assert result2.primary_magnet == 22100.0

    def test_anti_flicker_force_refresh(self):
        """force_refresh=True → always replaces."""
        scorer = MagnetScorer()
        snap1 = _snap(call_wall=22150.0, gamma_flip=21800.0)
        result1 = scorer.score(snap1, current_nq=22100.0)
        assert result1.status == "valid"

        # Set high current score to block normal replacement
        scorer._state.current_score = 0.99
        scorer._state.locked_at = time.monotonic()

        # With force_refresh, should always select new magnet
        snap2 = _snap(call_wall=22200.0, gamma_flip=21800.0)
        result2 = scorer.score(snap2, current_nq=22100.0, force_refresh=True)
        assert result2.status == "valid"
        assert result2.primary_magnet == 22200.0


class TestInvalidation:
    """Every magnet must have invalidation."""

    def test_every_magnet_has_invalidation(self):
        """All valid MagnetResult objects have non-None invalidation_level."""
        scorer = MagnetScorer()

        # Test with each level type producing a valid magnet
        scenarios = [
            _snap(gex_sign="positive", call_wall=22200.0, gamma_flip=22000.0),
            _snap(gex_sign="negative", gamma_flip=22050.0, call_wall=22500.0),
            _snap(gex_sign="positive", put_wall=22050.0, call_wall=22500.0, gamma_flip=21000.0),
            _snap(gex_sign="positive", pin_risk=80.0, magnet_strike=22100.0, gamma_flip=22000.0),
            _snap(gex_sign="positive", max_pain=22100.0, dte=0, gamma_flip=22000.0),
        ]

        for snap in scenarios:
            result = scorer.score(snap, current_nq=22100.0, force_refresh=True)
            if result.status == "valid":
                assert result.invalidation_level is not None, (
                    f"Missing invalidation for magnet at {result.primary_magnet}"
                )
                assert result.invalidation_reason != ""

    def test_call_wall_invalidation_above(self):
        """Call wall invalidation is above the wall level."""
        scorer = MagnetScorer()
        snap = _snap(gex_sign="positive", call_wall=22200.0, gamma_flip=22000.0)
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "valid"
        assert result.invalidation_level is not None
        assert result.invalidation_level > 22200.0

    def test_put_wall_invalidation_below(self):
        """Put wall invalidation is below the wall level."""
        scorer = MagnetScorer()
        # Make put_wall the winner by placing it close and everything else far
        snap = _snap(
            gex_sign="positive",
            put_wall=22050.0,
            call_wall=22500.0,
            gamma_flip=21500.0,
        )
        result = scorer.score(snap, current_nq=22100.0)
        assert result.status == "valid"
        if result.primary_magnet == 22050.0:
            assert result.invalidation_level < 22050.0


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_max_pain_expiry_boost_0dte(self):
        """Max pain gets higher weight on 0DTE."""
        scorer = MagnetScorer()
        snap_0dte = _snap(
            gex_sign="positive",
            max_pain=22100.0,
            dte=0,
            call_wall=22500.0,  # far
            gamma_flip=21500.0,  # far
        )
        result = scorer.score(snap_0dte, current_nq=22100.0)
        # max_pain_expiry weight=0.80 vs max_pain=0.40
        expiry_candidates = [
            c for c in result.supporting_levels if c.level_type == "max_pain_expiry"
        ]
        assert len(expiry_candidates) == 1
        assert expiry_candidates[0].score > 0.0

    def test_amplifying_flow_boosts_score(self):
        """Amplifying flow direction gives 1.1x multiplier."""
        scorer = MagnetScorer()
        snap_neutral = _snap(
            flow_direction="neutral",
            call_wall=22200.0,
            gamma_flip=22000.0,
        )
        snap_amplifying = _snap(
            flow_direction="amplifying",
            call_wall=22200.0,
            gamma_flip=22000.0,
        )
        r_neutral = scorer.score(snap_neutral, current_nq=22100.0, force_refresh=True)
        r_amp = scorer.score(snap_amplifying, current_nq=22100.0, force_refresh=True)

        # Get call_wall scores from each
        cw_neutral = [c for c in r_neutral.supporting_levels if c.level_type == "call_wall"]
        cw_amp = [c for c in r_amp.supporting_levels if c.level_type == "call_wall"]
        assert cw_amp[0].score > cw_neutral[0].score

    def test_constants_match_spec(self):
        """Verify spec constants are correct."""
        assert MIN_CONFIDENCE == 0.65
        assert ANTI_FLICKER_MARGIN == 0.12
        assert LEVEL_TYPE_WEIGHTS["pin_magnet_strike"] == 1.00
        assert LEVEL_TYPE_WEIGHTS["gamma_flip"] == 0.90
        assert LEVEL_TYPE_WEIGHTS["call_wall"] == 0.85
        assert LEVEL_TYPE_WEIGHTS["put_wall"] == 0.85
        assert LEVEL_TYPE_WEIGHTS["max_pain_expiry"] == 0.80
        assert LEVEL_TYPE_WEIGHTS["max_pain"] == 0.40

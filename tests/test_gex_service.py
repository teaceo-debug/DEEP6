from __future__ import annotations

import math
import unittest

from scripts.gex_service import (
    AggregateBook,
    ExposureSnapshot,
    build_payload,
    compute_charm,
    compute_gex,
    compute_vanna,
    choose_anchor_levels,
)


class GexServiceTests(unittest.TestCase):
    def test_compute_gex_uses_spot_squared_formula(self) -> None:
        got = compute_gex(gamma=0.0125, open_interest=1000, spot=500.0)
        expected = 0.0125 * 1000 * 100.0 * 500.0 * 500.0 * 0.01
        self.assertTrue(math.isclose(got, expected, rel_tol=1e-12))

    def test_vanna_and_charm_are_finite_for_reasonable_inputs(self) -> None:
        vanna = compute_vanna(spot=500.0, strike=505.0, time_to_expiry_years=2/365, rate=0.05, dividend_yield=0.0, sigma=0.22)
        charm = compute_charm(spot=500.0, strike=505.0, time_to_expiry_years=2/365, rate=0.05, dividend_yield=0.0, sigma=0.22)
        self.assertTrue(math.isfinite(vanna))
        self.assertTrue(math.isfinite(charm))

    def test_choose_anchor_levels_extracts_expected_level_roles(self) -> None:
        book = AggregateBook(
            spot=500.0,
            by_strike={
                490.0: ExposureSnapshot(gex=-1200.0, vex=-900.0, dex=-1500.0, chex=-700.0),
                500.0: ExposureSnapshot(gex=250.0, vex=100.0, dex=800.0, chex=100.0),
                510.0: ExposureSnapshot(gex=2200.0, vex=1300.0, dex=500.0, chex=1500.0),
            },
        )
        levels = choose_anchor_levels(book)
        self.assertAlmostEqual(levels["gamma_flip"].price, 498.2758620689655)
        self.assertEqual(levels["call_wall"].price, 510.0)
        self.assertEqual(levels["put_wall"].price, 490.0)
        self.assertEqual(levels["hvl"].price, 510.0)
        self.assertEqual(levels["vanna_call"].price, 510.0)
        self.assertEqual(levels["vanna_put"].price, 490.0)
        self.assertEqual(levels["dex_peak"].price, 490.0)
        self.assertEqual(levels["charm_drift"].price, 510.0)

    def test_build_payload_preserves_asset_metadata_and_levels(self) -> None:
        payload = build_payload(
            generated_at_utc="2026-04-26T19:12:50Z",
            assets=[
                {
                    "underlying": "QQQ",
                    "futures_root": "NQ",
                    "spot": 500.0,
                    "mapped_spot": 20123.0,
                    "ratio": 40.246,
                    "is_0dte": True,
                    "regime": "VOL↓=BUY",
                    "levels": {
                        "gamma_flip": {"symbol": "⚡", "label": "GAMMA FLIP", "action": "REGIME PIVOT", "price": 20050.0, "value": 0.0},
                    },
                }
            ],
        )
        self.assertEqual(payload["generated_at_utc"], "2026-04-26T19:12:50Z")
        self.assertEqual(payload["assets"][0]["underlying"], "QQQ")
        self.assertEqual(payload["assets"][0]["futures_root"], "NQ")
        self.assertEqual(payload["assets"][0]["levels"]["gamma_flip"]["symbol"], "⚡")


if __name__ == "__main__":
    unittest.main()

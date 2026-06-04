from __future__ import annotations

import pytest

from deep6v2.data.gex_client import GEXClient, GEXLevels


@pytest.fixture
def levels() -> GEXLevels:
    return GEXLevels(
        call_wall=21500.0,
        put_wall=21000.0,
        gamma_flip=21250.0,
        hvl=21300.0,
        timestamp=1700000000.0,
    )


@pytest.fixture
def client() -> GEXClient:
    return GEXClient(api_key="test-key")


class TestZoneBonus:
    def test_near_call_wall(self, client: GEXClient, levels: GEXLevels) -> None:
        bonus = client.calculate_zone_bonus(21500.0, levels)
        assert bonus == 8.0

    def test_within_range_call_wall(self, client: GEXClient, levels: GEXLevels) -> None:
        bonus = client.calculate_zone_bonus(21497.5, levels)
        assert bonus == pytest.approx(4.0)

    def test_near_put_wall(self, client: GEXClient, levels: GEXLevels) -> None:
        bonus = client.calculate_zone_bonus(21000.0, levels)
        assert bonus == 8.0

    def test_far_from_walls(self, client: GEXClient, levels: GEXLevels) -> None:
        bonus = client.calculate_zone_bonus(21250.0, levels)
        assert bonus == 0.0

    def test_none_levels(self, client: GEXClient) -> None:
        bonus = client.calculate_zone_bonus(21500.0, None)
        assert bonus == 0.0


class TestGEXMult:
    def test_above_gamma_flip(self, client: GEXClient, levels: GEXLevels) -> None:
        mult = client.calculate_gex_mult(21300.0, levels)
        assert mult == 1.05

    def test_below_gamma_flip(self, client: GEXClient, levels: GEXLevels) -> None:
        mult = client.calculate_gex_mult(21200.0, levels)
        assert mult == 1.0

    def test_at_gamma_flip(self, client: GEXClient, levels: GEXLevels) -> None:
        mult = client.calculate_gex_mult(21250.0, levels)
        assert mult == 1.0

    def test_none_levels(self, client: GEXClient) -> None:
        mult = client.calculate_gex_mult(21300.0, None)
        assert mult == 1.0


class TestFetchLevels:
    @pytest.mark.asyncio
    async def test_no_api_key(self) -> None:
        client = GEXClient(api_key=None)
        # Ensure env var doesn't leak in
        import os

        old = os.environ.pop("MASSIVE_API_KEY", None)
        try:
            no_key_client = GEXClient(api_key=None)
            result = await no_key_client.fetch_levels()
            assert result is None
        finally:
            if old is not None:
                os.environ["MASSIVE_API_KEY"] = old

    @pytest.mark.asyncio
    async def test_with_key_returns_cached(self, client: GEXClient) -> None:
        result = await client.fetch_levels()
        assert result is None  # No cached levels yet

    def test_last_levels_default_none(self, client: GEXClient) -> None:
        assert client.last_levels is None

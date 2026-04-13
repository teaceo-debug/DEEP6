"""Shared pytest fixtures for DEEP6 test suite."""
import pytest
from deep6.config import Config


@pytest.fixture
def config() -> Config:
    return Config(
        rithmic_user="test_user",
        rithmic_password="test_pass",
        rithmic_system_name="Rithmic Test",
        rithmic_uri="wss://rituz00100.rithmic.com:443",
        db_path=":memory:",
    )


@pytest.fixture
def fake_tick_factory():
    """Returns a callable that produces fake tick dicts with specified aggressor.

    aggressor: 0=UNSPECIFIED, 1=BUY (ask aggressor), 2=SELL (bid aggressor)
    """
    def factory(price: float = 21000.0, size: int = 1, aggressor: int = 1) -> dict:
        return {
            "data_type": "LAST_TRADE",
            "price": price,
            "size": size,
            "aggressor": aggressor,
        }
    return factory

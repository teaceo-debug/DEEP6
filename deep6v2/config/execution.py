from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionConfig(BaseSettings):
    max_contracts: int = 2
    max_trades_per_session: int = 10
    daily_loss_cap_dollars: float = 500.0
    rth_start: str = "09:30"
    rth_end: str = "16:00"
    confirmation_delay_bars: int = 1
    dry_run: bool = True

    model_config = SettingsConfigDict(env_prefix="EXECUTION_")


__all__ = ["ExecutionConfig"]

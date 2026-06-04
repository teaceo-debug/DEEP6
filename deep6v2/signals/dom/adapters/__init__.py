from __future__ import annotations

from .replay_adapter import ReplayDOMAdapter

try:
    from .live_adapter import FeedStaleError, LiveDOMAdapter
except ModuleNotFoundError:  # pragma: no cover - live adapter lands in parallel work.
    __all__ = ["ReplayDOMAdapter"]
else:
    __all__ = ["FeedStaleError", "LiveDOMAdapter", "ReplayDOMAdapter"]

"""Standard Deviation Anchor AI — HERMES sidecar observation bridge.

Watches TradingView chart state, receives Pine candidate payloads,
captures screenshots, and routes through the HERMES approve/veto pipeline
with full audit logging.
"""

from deep6.sd_anchor.sidecar import HermesVerdict, SDSidecar
from deep6.sd_anchor.webhook import normalize_pine_payload

__all__ = ["HermesVerdict", "SDSidecar", "normalize_pine_payload"]

"""DEEP6 orderflow package — VPIN and other microstructure modulators.

This package adds flow-toxicity measurements that modulate the FUSED LightGBM
meta-learner confidence (scorer output). Orthogonal to the 44-signal vote: does
not change direction, does not modify per-signal raw scores, does not stack
with the IB multiplier on per-signal values.

See phase 12-01 CONTEXT for locked design decisions.
"""
from deep6.orderflow.vpin import VPINEngine, FlowRegime
from deep6.orderflow.slingshot import SlingshotDetector, SlingshotResult

__all__ = ["VPINEngine", "FlowRegime", "SlingshotDetector", "SlingshotResult"]

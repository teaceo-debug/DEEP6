from __future__ import annotations

__all__ = ["AbsorptionDetector"]


def __getattr__(name: str):
    if name == "AbsorptionDetector":
        from deep6v2.signals.absorption import AbsorptionDetector

        return AbsorptionDetector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

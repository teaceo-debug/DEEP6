from __future__ import annotations

from collections.abc import Sequence


def least_squares_slope(values: list[float] | Sequence[float]) -> float:
    """Simple OLS slope for evenly-spaced values (x = 0, 1, 2, ...)."""
    n = len(values)
    if n < 2:
        return 0.0

    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


__all__ = ["least_squares_slope"]

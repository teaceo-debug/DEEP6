"""Dark pool support/resistance level computation from raw prints."""
from __future__ import annotations

import logging
import statistics
from typing import Optional

from gex_terminal.schemas_institutional import DarkPoolLevel

logger = logging.getLogger(__name__)

DEFAULT_CLUSTER_PCT = 0.005
DEFAULT_NQ_QQQ_RATIO = 41.16  # NQ ~30500 / QQQ ~741 (June 2026)


class DarkPoolLevelEngine:
    """Clusters dark pool prints into support/resistance levels."""

    def __init__(self, cluster_pct: float = DEFAULT_CLUSTER_PCT) -> None:
        self._cluster_pct = cluster_pct

    def compute_levels(
        self,
        prints: list[dict],
        current_price_nq: Optional[float] = None,
        nq_qqq_ratio: float = DEFAULT_NQ_QQQ_RATIO,
        max_levels: int = 10,
    ) -> list[DarkPoolLevel]:
        """Cluster prints and return support/resistance levels sorted by strength."""
        if not prints:
            return []

        entries: list[dict[str, float]] = []
        for raw_print in prints:
            price = self._safe_float(raw_print.get("price"))
            premium = self._safe_float(raw_print.get("premium"), 0.0)
            size = self._safe_float(raw_print.get("size"), 0.0)
            if price and price > 0:
                entries.append({"price": price, "premium": abs(premium), "size": size})

        if not entries:
            return []

        entries.sort(key=lambda entry: entry["price"])
        clusters = self._cluster(entries)
        all_premiums = [cluster["total_premium"] for cluster in clusters if cluster["total_premium"] > 0]
        median_premium = statistics.median(all_premiums) if all_premiums else 1.0

        levels: list[DarkPoolLevel] = []
        for cluster in clusters:
            price_nq = round(cluster["center"] * nq_qqq_ratio, 2)
            level_type = "NEUTRAL"
            if current_price_nq is not None:
                level_type = "SUPPORT" if price_nq < current_price_nq else "RESIST"

            multiplier = (
                round(cluster["total_premium"] / median_premium, 2)
                if median_premium > 0
                else 1.0
            )

            levels.append(
                DarkPoolLevel(
                    price_nq=price_nq,
                    total_premium=cluster["total_premium"],
                    print_count=cluster["count"],
                    volume=cluster["total_size"],
                    multiplier=multiplier,
                    std_dev=round(cluster["std"], 4),
                    level_type=level_type,
                )
            )

        levels.sort(key=lambda level: level.total_premium, reverse=True)
        return levels[:max_levels]

    def _cluster(self, entries: list[dict[str, float]]) -> list[dict[str, float]]:
        """Greedy clustering by price proximity."""
        if not entries:
            return []

        clusters: list[dict[str, float]] = []
        current = [entries[0]]

        for entry in entries[1:]:
            ref_price = current[0]["price"]
            if ref_price > 0 and abs(entry["price"] - ref_price) / ref_price <= self._cluster_pct:
                current.append(entry)
                continue
            clusters.append(self._summarize(current))
            current = [entry]

        if current:
            clusters.append(self._summarize(current))

        return clusters

    def _summarize(self, entries: list[dict[str, float]]) -> dict[str, float]:
        prices = [entry["price"] for entry in entries]
        premiums = [entry["premium"] for entry in entries]
        sizes = [entry["size"] for entry in entries]

        total_premium = sum(premiums)
        if total_premium > 0:
            center = sum(price * weight for price, weight in zip(prices, premiums)) / total_premium
        else:
            center = statistics.mean(prices)

        std_dev = statistics.stdev(prices) if len(prices) > 1 else 0.0
        return {
            "center": center,
            "total_premium": total_premium,
            "total_size": sum(sizes),
            "count": float(len(entries)),
            "std": std_dev,
        }

    def _safe_float(self, val: object, default: float = 0.0) -> Optional[float]:
        if val is None:
            return default if default != 0.0 else None
        try:
            return float(val)
        except (TypeError, ValueError):
            logger.debug("Skipping non-numeric dark pool value: %r", val)
            return default


__all__ = ["DarkPoolLevelEngine", "DEFAULT_CLUSTER_PCT", "DEFAULT_NQ_QQQ_RATIO"]

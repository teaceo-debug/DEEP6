"""Atomic weight file manager.

Handles reading, writing, and rolling back deployed weight files.

Key invariants:
- D-20: Atomic swap — weight file is never in a partially-written state.
  Write to .tmp first, then os.replace() which is atomic on POSIX/macOS.
- D-21: 7-day backup retention. Previous weights kept as rollback fallback.
- Scorer calls read_current() once per bar. No lock needed — os.replace
  is atomic on POSIX/macOS; partial reads are impossible.
- T-09-09: Write to .tmp first, then os.replace — atomic on macOS/POSIX;
  no half-written state.

Usage:
    loader = WeightLoader()
    loader.write_atomic(weight_file)   # deploys new weights
    ok = loader.rollback()             # restores previous if within TTL
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any

from deep6.ml.lgbm_trainer import WeightFile

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase 12-05: WalkForward override merging
# ---------------------------------------------------------------------------


def apply_walk_forward_overrides(
    weight_file: WeightFile, tracker: object | None
) -> WeightFile:
    """Merge WalkForwardTracker disable mask into ``regime_adjustments``.

    Phase 12-05 feedback loop: the tracker's ``get_weights_override()`` returns
    a ``regime → category → multiplier`` map where 0.0 means the (regime,
    category) cell is currently auto-disabled. This function merges that map
    multiplicatively into ``weight_file.regime_adjustments`` so downstream
    LightGBM fusion naturally suppresses disabled cells.

    Returns a NEW WeightFile (no in-place mutation) so callers can safely
    snapshot the merged value at bar-close without races (FOOTGUN 3 — no
    mid-bar weight flip).

    If ``tracker`` is None or has no overrides, returns the original
    ``weight_file`` unchanged.
    """
    if tracker is None:
        return weight_file
    try:
        overrides = tracker.get_weights_override()  # type: ignore[attr-defined]
    except Exception:
        log.warning("walk_forward.overrides.unavailable", exc_info=True)
        return weight_file
    if not overrides:
        return weight_file

    # Multiplicative composition with any pre-existing adjustments.
    merged: dict[str, dict[str, float]] = {
        regime: dict(cats) for regime, cats in (weight_file.regime_adjustments or {}).items()
    }
    for regime, cat_map in overrides.items():
        dst = merged.setdefault(regime, {})
        for category, mult in cat_map.items():
            existing = dst.get(category, 1.0)
            dst[category] = float(existing) * float(mult)

    return WeightFile(
        weights=dict(weight_file.weights),
        regime_adjustments=merged,
        feature_importances=dict(weight_file.feature_importances),
        training_date=weight_file.training_date,
        n_samples=weight_file.n_samples,
        metrics=dict(weight_file.metrics),
        wfe=weight_file.wfe,
        model_path=weight_file.model_path,
        model_checksum=weight_file.model_checksum,
    )


class WeightLoader:
    """Manages atomic weight file reads, writes, and rollbacks.

    File layout:
        weights_path      — current active weights (written atomically)
        backup_path       — previous weights (for rollback within TTL)
        weights_path.tmp  — temporary staging file (removed on successful write)

    Thread safety: os.replace() is atomic on POSIX and macOS. No explicit
    lock is needed for the scorer's per-bar read path.

    Per T-09-14 (mitigate): read_current() uses mtime-based caching —
    re-reads the file only when its mtime has changed. This prevents
    repeated disk I/O at 1,000+ callbacks/sec while ensuring stale
    weights are never served after a deploy (write_atomic invalidates cache).
    """

    def __init__(
        self,
        weights_path: str = "./deep6_weights.json",
        backup_path: str = "./deep6_weights_prev.json",
        backup_ttl_days: int = 7,
    ) -> None:
        self.weights_path = str(Path(weights_path).expanduser().resolve())
        self.backup_path = str(Path(backup_path).expanduser().resolve())
        self.backup_ttl_days = backup_ttl_days
        # T-09-14: mtime cache — avoids redundant disk reads
        self._cached_mtime: float | None = None
        self._cached_data: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Write + rollback
    # ------------------------------------------------------------------

    def write_atomic(self, weight_file: WeightFile) -> None:
        """Write weight_file to disk atomically.

        Algorithm (T-09-09):
          1. If current file exists: copy to backup_path (D-21 rollback).
          2. Serialize to JSON and write to weights_path + ".tmp".
          3. os.replace(tmp, weights_path) — atomic rename on POSIX/macOS.

        Scorer reads weights_path once per bar. Between steps 2 and 3 the
        old file is still fully intact. After step 3 the new file is live.
        The .tmp file is always cleaned up (renamed away or on error).

        Args:
            weight_file: Trained WeightFile to deploy.
        """
        tmp_path = self.weights_path + ".tmp"

        # Step 1: rotate current → backup
        if os.path.exists(self.weights_path):
            shutil.copy2(self.weights_path, self.backup_path)
            log.info("weight_loader.backup_created", extra={"backup": self.backup_path})

        # Step 2: write to tmp
        payload = weight_file.to_json()
        payload["deployed_at"] = time.time()

        try:
            # Ensure parent directory exists
            Path(self.weights_path).parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w") as fh:
                json.dump(payload, fh, indent=2)

            # Step 3: atomic rename — T-09-09
            os.replace(tmp_path, self.weights_path)
        except Exception:
            # Clean up tmp on failure — never leave a partial file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        # T-09-14: Invalidate mtime cache so next read_current() re-reads from disk
        self._cached_mtime = None
        self._cached_data = None

        log.info(
            "weight_loader.write_atomic.complete",
            extra={
                "path": self.weights_path,
                "training_date": weight_file.training_date,
                "wfe": weight_file.wfe,
            },
        )

    def rollback(self) -> bool:
        """Restore previous weight file if backup exists and within TTL.

        D-21: backup retained for backup_ttl_days. Rollback is blocked
        after that window to prevent deploying stale weights.

        Returns:
            True if rollback succeeded, False if no valid backup available.
        """
        if not os.path.exists(self.backup_path):
            log.info("weight_loader.rollback.no_backup")
            return False

        age = self.backup_age_days()
        if age is not None and age > self.backup_ttl_days:
            log.warning(
                "weight_loader.rollback.backup_expired",
                extra={"age_days": age, "ttl_days": self.backup_ttl_days},
            )
            return False

        # Atomic swap: backup → current
        tmp_path = self.weights_path + ".tmp"
        shutil.copy2(self.backup_path, tmp_path)
        os.replace(tmp_path, self.weights_path)

        log.info(
            "weight_loader.rollback.complete",
            extra={"backup": self.backup_path, "age_days": age},
        )
        return True

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def read_current(self) -> dict[str, Any] | None:
        """Read the current weight file JSON, using mtime cache (T-09-14).

        Re-reads from disk only when the file's mtime has changed since the
        last successful read. Returns cached data otherwise — O(1) hot path
        for the scorer at 1,000+ callbacks/sec.

        No lock needed — os.replace is atomic on POSIX/macOS; a concurrent
        write produces a complete file. write_atomic() invalidates the cache.

        Returns:
            Parsed JSON dict, or None if file does not exist.
        """
        if not os.path.exists(self.weights_path):
            self._cached_mtime = None
            self._cached_data = None
            return None

        try:
            current_mtime = os.path.getmtime(self.weights_path)
        except OSError:
            return None

        # Cache hit — file unchanged since last read
        if self._cached_mtime is not None and current_mtime == self._cached_mtime:
            return self._cached_data

        # Cache miss — read from disk and update cache
        data = self._read_json(self.weights_path)
        if data is not None:
            self._cached_mtime = current_mtime
            self._cached_data = data
        return data

    def read_previous(self) -> dict[str, Any] | None:
        """Read the backup weight file JSON.

        Returns:
            Parsed JSON dict, or None if no backup exists.
        """
        return self._read_json(self.backup_path)

    def backup_age_days(self) -> float | None:
        """Return the age of the backup file in fractional days.

        Returns:
            Age in days, or None if no backup file exists.
        """
        if not os.path.exists(self.backup_path):
            return None
        mtime = os.path.getmtime(self.backup_path)
        elapsed_seconds = time.time() - mtime
        return elapsed_seconds / 86400.0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _read_json(path: str) -> dict[str, Any] | None:
        """Read and parse a JSON file; return None on any error."""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("weight_loader.read_failed", extra={"path": path, "exc": str(exc)})
            return None

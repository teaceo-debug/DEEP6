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


class WeightLoader:
    """Manages atomic weight file reads, writes, and rollbacks.

    File layout:
        weights_path      — current active weights (written atomically)
        backup_path       — previous weights (for rollback within TTL)
        weights_path.tmp  — temporary staging file (removed on successful write)

    Thread safety: os.replace() is atomic on POSIX and macOS. No explicit
    lock is needed for the scorer's per-bar read path.
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
        """Read the current weight file JSON.

        Scorer calls this once per bar. No lock needed — os.replace is
        atomic on POSIX/macOS; a concurrent write produces a complete file.

        Returns:
            Parsed JSON dict, or None if file does not exist.
        """
        return self._read_json(self.weights_path)

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

from __future__ import annotations

import datetime
import glob
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


class NT8Paths:
    def __init__(self) -> None:
        userprofile = os.environ.get("USERPROFILE", r"C:\Users\Tea")
        self.userprofile = userprofile
        self.nt8_root = os.path.join(userprofile, "Documents", "NinjaTrader 8")
        self.custom_source = os.path.join(self.nt8_root, "bin", "Custom")
        self.custom_dll = os.path.join(self.custom_source, "NinjaTrader.Custom.dll")
        self.indicators_dir = os.path.join(self.custom_source, "Indicators")
        self.strategies_dir = os.path.join(self.custom_source, "Strategies")
        self.log_dir = os.path.join(self.nt8_root, "log")
        self.workspaces_dir = os.path.join(self.nt8_root, "workspaces")
        self.install_xml = os.path.join(self.log_dir, "Install.xml")
        self.repo_source = self._detect_repo_source()
        self.ninjascript_exe = r"C:\Program Files\NinjaTrader 8\bin\NinjaScript.exe"

    def _detect_repo_source(self) -> str:
        env_repo = os.environ.get("DEEP6_REPO_ROOT")
        if env_repo:
            return os.path.join(env_repo, "ninjatrader", "Custom")

        here = Path(__file__).resolve()
        repo_root = here.parents[4] if len(here.parents) >= 5 else Path(self.userprofile).parent
        candidate = repo_root / "ninjatrader" / "Custom"
        if candidate.exists() or repo_root.exists():
            return str(candidate)

        return r"C:\Users\Tea\DEEP6\ninjatrader\Custom"

    def _path_map(self) -> dict[str, str]:
        return {
            "nt8_root": self.nt8_root,
            "custom_source": self.custom_source,
            "custom_dll": self.custom_dll,
            "indicators_dir": self.indicators_dir,
            "strategies_dir": self.strategies_dir,
            "log_dir": self.log_dir,
            "workspaces_dir": self.workspaces_dir,
            "install_xml": self.install_xml,
            "repo_source": self.repo_source,
            "ninjascript_exe": self.ninjascript_exe,
        }

    def validate(self) -> dict:
        return {
            name: {"path": path, "exists": os.path.exists(path)}
            for name, path in self._path_map().items()
        }

    def check_devaddon(self) -> bool:
        try:
            with urllib.request.urlopen("http://localhost:19206/health", timeout=2) as response:
                return response.status == 200
        except Exception:
            return False

    def available_compile_paths(self) -> list[str]:
        available = []
        if self.check_devaddon():
            available.append("devaddon_http")
        if os.path.exists(self.ninjascript_exe):
            available.append("ninjascript_exe")
        available.append("editor_uia")
        return available

    def get_latest_log(self) -> str | None:
        log_dir = Path(self.log_dir)
        if not log_dir.exists():
            return None

        today = datetime.datetime.now().strftime("%Y%m%d")
        pattern = os.path.join(self.log_dir, f"log.{today}.*.txt")
        matches = glob.glob(pattern)
        if not matches:
            return None

        latest_path = max(matches, key=lambda p: os.path.getmtime(p))
        return latest_path

    def to_json(self) -> str:
        validation = self.validate()
        report = {
            "message": "NT8 paths detected" if any(item["exists"] for item in validation.values()) else "NT8 not installed or not found",
            "paths": {name: item["path"] for name, item in validation.items()},
            "validation": validation,
            "available_compile_paths": self.available_compile_paths(),
            "latest_log": self.get_latest_log(),
        }
        return json.dumps(report, indent=2)


if __name__ == "__main__":
    paths = NT8Paths()
    print(paths.to_json())

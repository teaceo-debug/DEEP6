"""
DEEP6 Control Center v2 — Desktop monitoring dashboard with service control.

Tabs:
  Overview    — JSON data files, running services, port connectivity
  Depth Radar — Live wall report, ML classification service, start/stop

Usage:
    python tools/control_center.py
"""

import os
import sys
import json
import socket
import subprocess
import signal
import threading
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import customtkinter as ctk

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NT8_TEMPLATES = os.path.join(
    os.path.expanduser("~"), "Documents", "NinjaTrader 8", "templates", "DEEP6"
)
WALLS_JSON = os.path.join(NT8_TEMPLATES, "depth_radar_walls.json")
KRONOS_JSON = os.path.join(NT8_TEMPLATES, "kronos_forecast.json")
KRONOS_SERVICE = os.path.join(
    os.path.expanduser("~"), "Documents", "NinjaTrader 8", "templates", "DEEP6",
    "kronos_sidecar", "deep6_kronos_service.py",
)
KRONOS_VENV_PY = os.path.join(
    os.path.expanduser("~"), "Documents", "NinjaTrader 8", "templates", "DEEP6",
    "kronos_sidecar", ".venv", "Scripts", "python.exe",
)
LOGS_DIR = PROJECT_ROOT / "logs"

DATA_FILES = [
    ("massive_options_icebergs.json", "Options iceberg detection", 5),
    ("massive_gex_map.json", "GEX gamma exposure map", 5),
    ("institutional_context.json", "Institutional context & dark pool", 5),
    ("depth_radar_walls.json", "DOM wall detection", 5),
    ("kronos_forecast.json", "Kronos E10 directional bias", 15),
    ("bias_v3.json", "Live bias signal output", 10),
    ("gex_command.json", "FlashAlpha GEX data", 60),
    ("massive_gex_map_v2.json", "GEX map v2 (extended)", 60),
    ("mbo_levels.json", "MBO L3 level data", 10),
    ("options_decision_surface_v3.json", "Options decision surface", 120),
    ("options_level_intelligence.json", "Options level intelligence", 120),
]

# GEX Doctor output — written to NT8 AddOns dir, not templates dir
GEX_DOCTOR_JSON = str(Path(os.environ.get("PUBLIC", r"C:\Users\Public")) /
                      "Documents" / "NinjaTrader 8" / "bin" / "Custom" /
                      "AddOns" / "gex_nq.json")

SERVICES = [
    ("NinjaTrader", "process", "NinjaTrader", "Trading platform"),
    ("TradingView", "process", "TradingView", "Chart platform"),
    ("GEX Doctor", "cmdline", "nq_atlas_bridge", "GEX magnet → NT8 chart"),
    ("GEX Map Service", "cmdline", "massive_gex_map_service", "Gamma exposure mapping"),
    ("Options Iceberg", "cmdline", "massive_options_iceberg_service", "Hidden order detection"),
    ("Institutional Context", "cmdline", "institutional_context_service", "Dark pool & flow bias"),
    ("Depth Radar", "cmdline", "live_mbo_radar", "MBO-native wall classification (44 causal features)"),
    ("Kronos Sidecar", "cmdline", "deep6_kronos_service", "AI directional bias model"),
]

PORTS = [
    (9203, "Depth Radar Health", "MBO V4 radar metrics"),
    (9222, "TradingView CDP", "Chrome DevTools Protocol"),
    (8765, "ML Backend", "FastAPI core API"),
    (8766, "NQ ATLAS", "Options bias engine"),
    (8767, "Confluence", "Institutional middleware"),
    (8780, "SD Anchor", "TradingView webhook receiver"),

    (3000, "Dashboard", "Next.js frontend"),
]

# Service launch commands (cwd = PROJECT_ROOT)
LAUNCH_CMDS = {
    "GEX Doctor": [
        sys.executable, "gexdoctor/nq_atlas_bridge.py",
        "--url", "http://localhost:8766",
        "--interval", "15",
    ],
    "Depth Radar": [
        sys.executable, "-m", "deep6.services.live_mbo_radar",
        "--source", "rithmic", "--min-wall", "10", "--all-hours",
    ],
    "Kronos Sidecar": [
        KRONOS_VENV_PY if os.path.isfile(KRONOS_VENV_PY) else sys.executable,
        KRONOS_SERVICE, "--loop", "--interval-seconds", "60",
        "--fallback-momentum",
    ],
}

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------

C_BG = "#0a0e14"
C_PANEL = "#111820"
C_BORDER = "#1e2732"
C_TEXT = "#c5cdd8"
C_DIM = "#5c6773"
C_LIVE = "#2ecc71"
C_STALE = "#f39c12"
C_DEAD = "#e74c3c"
C_OFF = "#555e6a"
C_ACCENT = "#3498db"
C_HEADER = "#e8eaed"
C_GENUINE = "#2ecc71"
C_SPOOF = "#e74c3c"
C_ICEBERG = "#3498db"
C_STALE_CLS = "#95a5a6"
C_BTN = "#1a3a5c"
C_BTN_HOVER = "#245080"
C_BTN_DANGER = "#5c1a1a"
C_BTN_DANGER_H = "#803030"

# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------


def scan_json_files():
    results = []
    now = datetime.now()
    for filename, desc, stale_min in DATA_FILES:
        path = os.path.join(NT8_TEMPLATES, filename)
        entry = {
            "name": filename, "desc": desc, "path": path,
            "exists": False, "size": 0, "modified": None,
            "age_str": "", "status": "MISSING", "preview": "",
        }
        if os.path.isfile(path):
            stat = os.stat(path)
            mtime = datetime.fromtimestamp(stat.st_mtime)
            age = now - mtime
            entry.update(exists=True, size=stat.st_size, modified=mtime, age_str=_fmt_age(age))
            if age < timedelta(minutes=stale_min):
                entry["status"] = "LIVE"
            elif age < timedelta(hours=6):
                entry["status"] = "STALE"
            else:
                entry["status"] = "DEAD"
        results.append(entry)
    order = {"LIVE": 0, "STALE": 1, "DEAD": 2, "MISSING": 3}
    results.sort(key=lambda r: order.get(r["status"], 4))
    return results


def scan_services():
    results = []
    for display, match_type, match_val, desc in SERVICES:
        entry = {"name": display, "desc": desc, "running": False, "pid": None, "mem_mb": 0, "uptime_str": ""}
        try:
            for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "create_time"]):
                info = proc.info
                matched = False
                if match_type == "process":
                    matched = (info["name"] or "").lower().startswith(match_val.lower())
                elif match_type == "cmdline":
                    cmdline = " ".join(info["cmdline"] or [])
                    matched = match_val.lower() in cmdline.lower()
                if matched:
                    entry["running"] = True
                    entry["pid"] = info["pid"]
                    mem = info.get("memory_info")
                    if mem:
                        entry["mem_mb"] = round(mem.rss / (1024 * 1024), 1)
                    ct = info.get("create_time")
                    if ct:
                        entry["uptime_str"] = _fmt_age(datetime.now() - datetime.fromtimestamp(ct))
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        results.append(entry)
    results.sort(key=lambda r: (0 if r["running"] else 1, r["name"]))
    return results


def scan_ports():
    results = []
    for port, name, desc in PORTS:
        entry = {"port": port, "name": name, "desc": desc, "open": False}
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.3)
            entry["open"] = sock.connect_ex(("127.0.0.1", port)) == 0
            sock.close()
        except Exception:
            pass
        results.append(entry)
    results.sort(key=lambda r: (0 if r["open"] else 1, r["port"]))
    return results


def read_walls_json():
    """Read depth_radar_walls.json and return parsed wall data."""
    if not os.path.isfile(WALLS_JSON):
        return {"walls": [], "meta": {"status": "MISSING", "age_str": "", "wall_count": 0, "symbol": ""}}
    try:
        stat = os.stat(WALLS_JSON)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mtime
        with open(WALLS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        walls = data.get("walls", [])
        # Sort: biggest first
        walls.sort(key=lambda w: w.get("max_size", 0), reverse=True)
        meta = {
            "status": "LIVE" if age < timedelta(minutes=5) else ("STALE" if age < timedelta(hours=6) else "DEAD"),
            "age_str": _fmt_age(age),
            "wall_count": len(walls),
            "symbol": data.get("symbol", ""),
            "mid_price": data.get("mid_price", 0),
            "timestamp": data.get("timestamp", ""),
            "size_bytes": stat.st_size,
        }
        # Classification summary
        counts = {"GENUINE": 0, "SPOOF": 0, "ICEBERG": 0, "STALE": 0, "UNKNOWN": 0}
        for w in walls:
            cls = w.get("classification", "UNKNOWN")
            counts[cls] = counts.get(cls, 0) + 1
        meta["counts"] = counts
        return {"walls": walls, "meta": meta}
    except Exception as exc:
        return {"walls": [], "meta": {"status": "ERROR", "age_str": str(exc), "wall_count": 0, "symbol": ""}}


def read_kronos_json():
    """Read kronos_forecast.json and return parsed forecast data."""
    empty = {"forecast": {}, "path": [], "model": {}, "status_info": {}, "meta": {"status": "MISSING", "age_str": ""}}
    if not os.path.isfile(KRONOS_JSON):
        return empty
    try:
        stat = os.stat(KRONOS_JSON)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mtime
        with open(KRONOS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        fc = data.get("forecast", {})
        path_bars = data.get("path", {}).get("bars", [])
        status_blk = data.get("status", {})
        meta = {
            "status": "LIVE" if age < timedelta(minutes=15) else ("STALE" if age < timedelta(hours=6) else "DEAD"),
            "age_str": _fmt_age(age),
            "symbol": data.get("symbol", ""),
            "timestamp": data.get("timestampUtc", ""),
        }
        model = {
            "name": data.get("modelName", ""),
            "device": data.get("modelDevice", ""),
            "lookback": data.get("lookbackBars", 0),
            "context": data.get("maxContext", 0),
            "pred_bars": data.get("predictionBars", 0),
            "bar_period": data.get("barPeriod", ""),
            "source": data.get("sourceStatus", ""),
        }
        return {"forecast": fc, "path": path_bars, "model": model, "status_info": status_blk, "meta": meta}
    except Exception as exc:
        return {"forecast": {}, "path": [], "model": {}, "status_info": {}, "meta": {"status": "ERROR", "age_str": str(exc)}}


def read_gex_doctor_json():
    """Read gex_nq.json from NT8 AddOns and return parsed GEX Doctor data."""
    empty = {"levels": {}, "meta": {"status": "MISSING", "age_str": "", "source": ""}}
    if not os.path.isfile(GEX_DOCTOR_JSON):
        return empty
    try:
        stat = os.stat(GEX_DOCTOR_JSON)
        mtime = datetime.fromtimestamp(stat.st_mtime)
        age = datetime.now() - mtime
        with open(GEX_DOCTOR_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        stale_sec = data.get("stale_after_seconds", 300)
        if age.total_seconds() < stale_sec:
            file_status = "LIVE"
        elif age.total_seconds() < stale_sec * 6:
            file_status = "STALE"
        else:
            file_status = "DEAD"
        return {
            "levels": {
                "magnet":      data.get("primary_magnet"),
                "confidence":  data.get("magnet_confidence", 0),
                "bias":        data.get("bias_direction", "no_vote"),
                "flip":        data.get("flip"),
                "call_wall":   data.get("call_wall"),
                "put_wall":    data.get("put_wall"),
                "invalidation": data.get("invalidation_level"),
                "invalidation_reason": data.get("invalidation_reason", ""),
                "regime":      data.get("regime", ""),
                "pin_risk":    data.get("pin_risk"),
                "lean":        data.get("lean", ""),
                "caveats":     data.get("caveats", []),
                "nq_spot":     data.get("nq_spot"),
                "qqq_spot":    data.get("qqq_spot"),
            },
            "meta": {
                "status":   file_status,
                "age_str":  _fmt_age(age),
                "source":   data.get("source", ""),
                "as_of":    data.get("as_of", ""),
            },
        }
    except Exception as exc:
        return {"levels": {}, "meta": {"status": "ERROR", "age_str": str(exc), "source": ""}}


def _fmt_age(td):
    s = int(td.total_seconds())
    if s < 0:
        return "future?"
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h {(s % 3600) // 60}m"
    return f"{s // 86400}d {(s % 86400) // 3600}h"


def _fmt_size(n):
    if n < 1024:
        return f"{n}B"
    if n < 1048576:
        return f"{n / 1024:.1f}KB"
    return f"{n / 1048576:.1f}MB"


# ---------------------------------------------------------------------------
# Service control
# ---------------------------------------------------------------------------


def find_service_pid(match_val):
    """Return PID of running service or None."""
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if match_val.lower() in cmdline.lower():
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return None


def start_service(name):
    """Start a launchable service. Returns (success, message)."""
    cmd = LAUNCH_CMDS.get(name)
    if not cmd:
        return False, f"No launch command for {name}"
    if find_service_pid(cmd[1] if len(cmd) > 1 else name):
        return False, f"{name} already running"
    LOGS_DIR.mkdir(exist_ok=True)
    slug = name.lower().replace(" ", "_")
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT),
            stdout=open(LOGS_DIR / f"{slug}.log", "w"),
            stderr=open(LOGS_DIR / f"{slug}.err.log", "w"),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return True, f"Started {name} (PID {proc.pid})"
    except Exception as exc:
        return False, f"Failed: {exc}"


def stop_service(name, match_val):
    """Stop a service by killing its process. Returns (success, message)."""
    pid = find_service_pid(match_val)
    if not pid:
        return False, f"{name} not running"
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        proc.wait(timeout=5)
        return True, f"Stopped {name} (PID {pid})"
    except Exception as exc:
        return False, f"Kill failed: {exc}"


# ---------------------------------------------------------------------------
# UI Widgets
# ---------------------------------------------------------------------------


class StatusDot(ctk.CTkFrame):
    def __init__(self, master, color=C_OFF, size=10, **kw):
        super().__init__(master, width=size, height=size, corner_radius=size // 2, fg_color=color, **kw)
        self.configure(width=size, height=size)

    def set_color(self, color):
        self.configure(fg_color=color)


class SectionHeader(ctk.CTkFrame):
    def __init__(self, master, title, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        ctk.CTkLabel(self, text=title, font=("Segoe UI", 13, "bold"), text_color=C_ACCENT, anchor="w").pack(side="left", padx=(0, 10))
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER).pack(side="left", fill="x", expand=True, pady=8)


class FileRow(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", height=26, **kw)
        self.grid_columnconfigure(2, weight=1)
        self.dot = StatusDot(self, size=8)
        self.dot.grid(row=0, column=0, padx=(0, 8), pady=3)
        self.name_lbl = ctk.CTkLabel(self, text="", font=("Consolas", 12), text_color=C_TEXT, anchor="w", width=280)
        self.name_lbl.grid(row=0, column=1, sticky="w")
        self.status_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 11, "bold"), width=55, anchor="w")
        self.status_lbl.grid(row=0, column=2, sticky="w", padx=(4, 0))
        self.size_lbl = ctk.CTkLabel(self, text="", font=("Consolas", 11), text_color=C_DIM, width=65, anchor="e")
        self.size_lbl.grid(row=0, column=3, padx=(8, 0))
        self.age_lbl = ctk.CTkLabel(self, text="", font=("Consolas", 11), text_color=C_DIM, width=65, anchor="e")
        self.age_lbl.grid(row=0, column=4, padx=(4, 0))
        self.desc_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 10), text_color=C_DIM, anchor="w")
        self.desc_lbl.grid(row=0, column=5, sticky="w", padx=(12, 0))

    def update_data(self, info):
        c = {"LIVE": C_LIVE, "STALE": C_STALE, "DEAD": C_DEAD}.get(info["status"], C_OFF)
        self.dot.set_color(c)
        self.name_lbl.configure(text=info["name"])
        self.status_lbl.configure(text=info["status"], text_color=c)
        self.size_lbl.configure(text=_fmt_size(info["size"]) if info["exists"] else "-")
        self.age_lbl.configure(text=info["age_str"] if info["exists"] else "-")
        self.desc_lbl.configure(text=info["desc"])


class ServiceRow(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", height=26, **kw)
        self.grid_columnconfigure(2, weight=1)
        self.dot = StatusDot(self, size=8)
        self.dot.grid(row=0, column=0, padx=(0, 8), pady=3)
        self.name_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 12), text_color=C_TEXT, anchor="w", width=180)
        self.name_lbl.grid(row=0, column=1, sticky="w")
        self.status_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 11, "bold"), width=80, anchor="w")
        self.status_lbl.grid(row=0, column=2, sticky="w")
        self.detail_lbl = ctk.CTkLabel(self, text="", font=("Consolas", 11), text_color=C_DIM, anchor="w")
        self.detail_lbl.grid(row=0, column=3, sticky="w", padx=(8, 0))

    def update_data(self, info):
        c = C_LIVE if info["running"] else C_DEAD
        self.dot.set_color(c)
        self.name_lbl.configure(text=info["name"])
        self.status_lbl.configure(text="RUNNING" if info["running"] else "STOPPED", text_color=c)
        parts = []
        if info["pid"]:
            parts.append(f"PID {info['pid']}")
        if info["mem_mb"]:
            parts.append(f"{info['mem_mb']}MB")
        if info["uptime_str"]:
            parts.append(info["uptime_str"])
        self.detail_lbl.configure(text="  ".join(parts))


class PortRow(ctk.CTkFrame):
    def __init__(self, master, **kw):
        super().__init__(master, fg_color="transparent", height=26, **kw)
        self.dot = StatusDot(self, size=8)
        self.dot.grid(row=0, column=0, padx=(0, 8), pady=3)
        self.port_lbl = ctk.CTkLabel(self, text="", font=("Consolas", 12, "bold"), text_color=C_TEXT, width=50, anchor="w")
        self.port_lbl.grid(row=0, column=1, sticky="w")
        self.name_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 12), text_color=C_TEXT, width=160, anchor="w")
        self.name_lbl.grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.status_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 11, "bold"), width=60, anchor="w")
        self.status_lbl.grid(row=0, column=3, sticky="w", padx=(4, 0))
        self.desc_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 10), text_color=C_DIM, anchor="w")
        self.desc_lbl.grid(row=0, column=4, sticky="w", padx=(12, 0))

    def update_data(self, info):
        c = C_LIVE if info["open"] else C_OFF
        self.dot.set_color(c)
        self.port_lbl.configure(text=str(info["port"]))
        self.name_lbl.configure(text=info["name"])
        self.status_lbl.configure(text="OPEN" if info["open"] else "CLOSED", text_color=c)
        self.desc_lbl.configure(text=info["desc"])


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------


class DEEP6ControlCenter(ctk.CTk):
    REFRESH_MS = 5000

    def __init__(self):
        super().__init__()
        self.title("DEEP6 Control Center")
        self.geometry("960x820")
        self.minsize(800, 550)
        self.configure(fg_color=C_BG)
        ctk.set_appearance_mode("dark")

        self._file_rows = []
        self._svc_rows = []
        self._port_rows = []
        self._wall_rows = []
        self._refreshing = False
        self._toast_after_id = None

        self._build_ui()
        self._do_refresh()

    # ------------------------------------------------------------------ UI

    def _build_ui(self):
        # Title bar
        title_frame = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=50)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)

        ctk.CTkLabel(title_frame, text="DEEP6 CONTROL CENTER", font=("Segoe UI", 16, "bold"), text_color=C_HEADER).pack(side="left", padx=16, pady=8)

        self._status_lbl = ctk.CTkLabel(title_frame, text="", font=("Consolas", 10), text_color=C_DIM)
        self._status_lbl.pack(side="right", padx=16)

        ctk.CTkButton(
            title_frame, text="Refresh", width=80, height=30, font=("Segoe UI", 11),
            fg_color=C_BTN, hover_color=C_BTN_HOVER, command=self._manual_refresh,
        ).pack(side="right", padx=(0, 8), pady=8)

        # Toast label (for feedback messages)
        self._toast_lbl = ctk.CTkLabel(self, text="", font=("Segoe UI", 11), text_color=C_STALE, fg_color=C_PANEL, corner_radius=6, height=0)

        # Tabs
        self._tabs = ctk.CTkTabview(self, fg_color=C_BG, segmented_button_fg_color=C_PANEL, segmented_button_selected_color=C_BTN, segmented_button_unselected_color=C_BORDER)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._build_overview_tab()
        self._build_depth_radar_tab()
        self._build_kronos_tab()
        self._build_gex_doctor_tab()

    def _build_overview_tab(self):
        tab = self._tabs.add("Overview")
        body = ctk.CTkScrollableFrame(tab, fg_color=C_BG, corner_radius=0)
        body.pack(fill="both", expand=True)

        SectionHeader(body, "DATA FILES").pack(fill="x", pady=(4, 6))
        for _ in DATA_FILES:
            row = FileRow(body)
            row.pack(fill="x", pady=1)
            self._file_rows.append(row)

        SectionHeader(body, "SERVICES").pack(fill="x", pady=(16, 6))
        for _ in SERVICES:
            row = ServiceRow(body)
            row.pack(fill="x", pady=1)
            self._svc_rows.append(row)

        SectionHeader(body, "PORT CONNECTIVITY").pack(fill="x", pady=(16, 6))
        for _ in PORTS:
            row = PortRow(body)
            row.pack(fill="x", pady=1)
            self._port_rows.append(row)

    def _build_gex_doctor_tab(self):
        tab = self._tabs.add("GEX Doctor")
        body = ctk.CTkScrollableFrame(tab, fg_color=C_BG, corner_radius=0)
        body.pack(fill="both", expand=True)

        # -- Service control
        SectionHeader(body, "SERVICE CONTROL").pack(fill="x", pady=(4, 6))
        ctrl = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8)
        ctrl.pack(fill="x", pady=(0, 8), padx=4)
        r = ctk.CTkFrame(ctrl, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=10)
        self._gd_dot = StatusDot(r, size=10)
        self._gd_dot.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(r, text="GEX Doctor", font=("Segoe UI", 13), text_color=C_TEXT).pack(side="left")
        self._gd_status = ctk.CTkLabel(r, text="", font=("Segoe UI", 11, "bold"), width=80)
        self._gd_status.pack(side="left", padx=(12, 0))
        self._gd_detail = ctk.CTkLabel(r, text="", font=("Consolas", 10), text_color=C_DIM)
        self._gd_detail.pack(side="left", padx=(8, 0))
        ctk.CTkButton(r, text="Stop", width=60, height=26, font=("Segoe UI", 10), fg_color=C_BTN_DANGER, hover_color=C_BTN_DANGER_H, command=lambda: self._svc_action("stop", "GEX Doctor", "nq_atlas_bridge")).pack(side="right", padx=2)
        ctk.CTkButton(r, text="Start", width=60, height=26, font=("Segoe UI", 10), fg_color=C_BTN, hover_color=C_BTN_HOVER, command=lambda: self._svc_action("start", "GEX Doctor", None)).pack(side="right", padx=2)

        # -- Magnet display (big)
        SectionHeader(body, "NQ MAGNET").pack(fill="x", pady=(8, 6))
        mag_frame = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8)
        mag_frame.pack(fill="x", pady=(0, 8), padx=4)

        top = ctk.CTkFrame(mag_frame, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 4))
        self._gd_magnet = ctk.CTkLabel(top, text="--", font=("Consolas", 32, "bold"), text_color=C_DIM)
        self._gd_magnet.pack(side="left")
        self._gd_conf = ctk.CTkLabel(top, text="", font=("Consolas", 18), text_color=C_DIM)
        self._gd_conf.pack(side="left", padx=(16, 0))
        self._gd_bias = ctk.CTkLabel(top, text="", font=("Segoe UI", 16, "bold"), text_color=C_DIM)
        self._gd_bias.pack(side="left", padx=(20, 0))
        self._gd_file_status = ctk.CTkLabel(top, text="", font=("Segoe UI", 10, "bold"), text_color=C_DIM)
        self._gd_file_status.pack(side="right")

        # Key levels row
        levels = ctk.CTkFrame(mag_frame, fg_color="transparent")
        levels.pack(fill="x", padx=16, pady=(4, 14))
        self._gd_levels = {}
        for key, label in [("flip", "Gamma Flip"), ("call_wall", "Call Wall"), ("put_wall", "Put Wall"), ("invalidation", "Invalidation"), ("pin_risk", "Pin Score")]:
            f = ctk.CTkFrame(levels, fg_color="transparent")
            f.pack(side="left", padx=(0, 24))
            self._gd_levels[key] = ctk.CTkLabel(f, text="--", font=("Consolas", 14, "bold"), text_color=C_TEXT)
            self._gd_levels[key].pack()
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 9), text_color=C_DIM).pack()

        # -- Lean / narrative
        SectionHeader(body, "POSITIONING READ").pack(fill="x", pady=(8, 6))
        lean_frame = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8)
        lean_frame.pack(fill="x", pady=(0, 8), padx=4)
        self._gd_lean = ctk.CTkLabel(lean_frame, text="", font=("Consolas", 11), text_color=C_TEXT, anchor="w", justify="left")
        self._gd_lean.pack(fill="x", padx=16, pady=12)

        # -- Caveats / data quality
        SectionHeader(body, "DATA").pack(fill="x", pady=(8, 6))
        self._gd_meta = ctk.CTkLabel(body, text="", font=("Consolas", 10), text_color=C_DIM, anchor="w", justify="left")
        self._gd_meta.pack(fill="x", padx=8, pady=(0, 4))

    def _build_depth_radar_tab(self):
        tab = self._tabs.add("Depth Radar")
        body = ctk.CTkScrollableFrame(tab, fg_color=C_BG, corner_radius=0)
        body.pack(fill="both", expand=True)

        # -- Service controls
        SectionHeader(body, "SERVICE CONTROL").pack(fill="x", pady=(4, 6))

        ctrl_frame = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8)
        ctrl_frame.pack(fill="x", pady=(0, 8), padx=4)

        # Depth Radar row (V4 MBO-native)
        r1 = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        r1.pack(fill="x", padx=12, pady=(10, 10))
        self._dr_live_dot = StatusDot(r1, size=10)
        self._dr_live_dot.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(r1, text="Depth Radar", font=("Segoe UI", 13), text_color=C_TEXT).pack(side="left")
        self._dr_live_status = ctk.CTkLabel(r1, text="", font=("Segoe UI", 11, "bold"), width=80)
        self._dr_live_status.pack(side="left", padx=(12, 0))
        self._dr_live_detail = ctk.CTkLabel(r1, text="", font=("Consolas", 10), text_color=C_DIM)
        self._dr_live_detail.pack(side="left", padx=(8, 0))
        ctk.CTkButton(r1, text="Stop", width=60, height=26, font=("Segoe UI", 10), fg_color=C_BTN_DANGER, hover_color=C_BTN_DANGER_H, command=lambda: self._svc_action("stop", "Depth Radar", "live_mbo_radar")).pack(side="right", padx=2)
        ctk.CTkButton(r1, text="Start", width=60, height=26, font=("Segoe UI", 10), fg_color=C_BTN, hover_color=C_BTN_HOVER, command=lambda: self._svc_action("start", "Depth Radar", None)).pack(side="right", padx=2)

        # -- Classification summary
        SectionHeader(body, "CLASSIFICATION SUMMARY").pack(fill="x", pady=(8, 6))

        sum_frame = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8, height=50)
        sum_frame.pack(fill="x", pady=(0, 8), padx=4)

        self._cls_labels = {}
        inner = ctk.CTkFrame(sum_frame, fg_color="transparent")
        inner.pack(pady=10, padx=16)
        for tag, color, label in [("GENUINE", C_GENUINE, "Genuine"), ("SPOOF", C_SPOOF, "Spoof"), ("ICEBERG", C_ICEBERG, "Iceberg"), ("STALE", C_STALE_CLS, "Stale")]:
            f = ctk.CTkFrame(inner, fg_color="transparent")
            f.pack(side="left", padx=16)
            self._cls_labels[tag] = ctk.CTkLabel(f, text="0", font=("Consolas", 22, "bold"), text_color=color)
            self._cls_labels[tag].pack()
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 10), text_color=C_DIM).pack()

        # -- Data header
        SectionHeader(body, "WALL DATA").pack(fill="x", pady=(8, 4))
        self._walls_meta_lbl = ctk.CTkLabel(body, text="", font=("Consolas", 10), text_color=C_DIM, anchor="w")
        self._walls_meta_lbl.pack(fill="x", padx=8, pady=(0, 4))

        # Column headers
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x", padx=4)
        for text, w in [("SIDE", 45), ("PRICE", 90), ("SIZE", 50), ("MAX", 50), ("CLASS", 75), ("CONF", 45), ("AGE", 60), ("REFILLS", 50)]:
            ctk.CTkLabel(hdr, text=text, font=("Segoe UI", 9), text_color=C_DIM, width=w, anchor="w").pack(side="left", padx=2)

        # Wall rows (pre-allocate 40)
        self._wall_container = body
        self._wall_rows = []
        for _ in range(40):
            row = self._make_wall_row(body)
            self._wall_rows.append(row)

    def _make_wall_row(self, parent):
        f = ctk.CTkFrame(parent, fg_color="transparent", height=22)
        labels = {}
        for key, w, font in [("side", 45, ("Consolas", 11, "bold")), ("price", 90, ("Consolas", 11)), ("size", 50, ("Consolas", 11)), ("max", 50, ("Consolas", 11)), ("cls", 75, ("Segoe UI", 10, "bold")), ("conf", 45, ("Consolas", 10)), ("age", 60, ("Consolas", 10)), ("refills", 50, ("Consolas", 10))]:
            lbl = ctk.CTkLabel(f, text="", font=font, text_color=C_TEXT, width=w, anchor="w")
            lbl.pack(side="left", padx=2)
            labels[key] = lbl
        f._labels = labels
        return f

    def _build_kronos_tab(self):
        tab = self._tabs.add("Kronos")
        body = ctk.CTkScrollableFrame(tab, fg_color=C_BG, corner_radius=0)
        body.pack(fill="both", expand=True)

        # -- Service control
        SectionHeader(body, "SERVICE CONTROL").pack(fill="x", pady=(4, 6))
        ctrl = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8)
        ctrl.pack(fill="x", pady=(0, 8), padx=4)
        r = ctk.CTkFrame(ctrl, fg_color="transparent")
        r.pack(fill="x", padx=12, pady=10)
        self._kr_dot = StatusDot(r, size=10)
        self._kr_dot.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(r, text="Kronos Sidecar", font=("Segoe UI", 13), text_color=C_TEXT).pack(side="left")
        self._kr_status = ctk.CTkLabel(r, text="", font=("Segoe UI", 11, "bold"), width=80)
        self._kr_status.pack(side="left", padx=(12, 0))
        self._kr_detail = ctk.CTkLabel(r, text="", font=("Consolas", 10), text_color=C_DIM)
        self._kr_detail.pack(side="left", padx=(8, 0))
        ctk.CTkButton(r, text="Stop", width=60, height=26, font=("Segoe UI", 10), fg_color=C_BTN_DANGER, hover_color=C_BTN_DANGER_H, command=lambda: self._svc_action("stop", "Kronos Sidecar", "deep6_kronos_service")).pack(side="right", padx=2)
        ctk.CTkButton(r, text="Start", width=60, height=26, font=("Segoe UI", 10), fg_color=C_BTN, hover_color=C_BTN_HOVER, command=lambda: self._svc_action("start", "Kronos Sidecar", None)).pack(side="right", padx=2)

        # -- Forecast display (big visual)
        SectionHeader(body, "FORECAST").pack(fill="x", pady=(8, 6))
        fc_frame = ctk.CTkFrame(body, fg_color=C_PANEL, corner_radius=8)
        fc_frame.pack(fill="x", pady=(0, 8), padx=4)

        # Direction + confidence (big)
        top_row = ctk.CTkFrame(fc_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=16, pady=(14, 4))
        self._kr_direction = ctk.CTkLabel(top_row, text="--", font=("Segoe UI", 28, "bold"), text_color=C_DIM)
        self._kr_direction.pack(side="left")
        self._kr_confidence = ctk.CTkLabel(top_row, text="", font=("Consolas", 20), text_color=C_DIM)
        self._kr_confidence.pack(side="left", padx=(16, 0))
        self._kr_meta_lbl = ctk.CTkLabel(top_row, text="", font=("Consolas", 10), text_color=C_DIM)
        self._kr_meta_lbl.pack(side="right")

        # Key metrics row
        metrics = ctk.CTkFrame(fc_frame, fg_color="transparent")
        metrics.pack(fill="x", padx=16, pady=(4, 14))
        self._kr_metrics = {}
        for key, label in [("move", "Expected Move"), ("return", "Return %"), ("slope", "Slope"), ("vol", "Volatility"), ("agree", "Path Agreement"), ("uncert", "Uncertainty")]:
            f = ctk.CTkFrame(metrics, fg_color="transparent")
            f.pack(side="left", padx=(0, 20))
            self._kr_metrics[key] = ctk.CTkLabel(f, text="--", font=("Consolas", 14, "bold"), text_color=C_TEXT)
            self._kr_metrics[key].pack()
            ctk.CTkLabel(f, text=label, font=("Segoe UI", 9), text_color=C_DIM).pack()

        # -- Model info
        SectionHeader(body, "MODEL").pack(fill="x", pady=(8, 6))
        self._kr_model_lbl = ctk.CTkLabel(body, text="", font=("Consolas", 11), text_color=C_DIM, anchor="w", justify="left")
        self._kr_model_lbl.pack(fill="x", padx=8, pady=(0, 8))

        # -- Predicted path
        SectionHeader(body, "PREDICTED PATH").pack(fill="x", pady=(8, 4))
        hdr = ctk.CTkFrame(body, fg_color="transparent")
        hdr.pack(fill="x", padx=4)
        for text, w in [("TIME (UTC)", 160), ("OPEN", 90), ("HIGH", 90), ("LOW", 90), ("CLOSE", 90), ("VOLUME", 80)]:
            ctk.CTkLabel(hdr, text=text, font=("Segoe UI", 9), text_color=C_DIM, width=w, anchor="w").pack(side="left", padx=2)

        self._kr_path_rows = []
        for _ in range(12):
            row_f = ctk.CTkFrame(body, fg_color="transparent", height=22)
            labels = {}
            for key, w in [("time", 160), ("open", 90), ("high", 90), ("low", 90), ("close", 90), ("vol", 80)]:
                lbl = ctk.CTkLabel(row_f, text="", font=("Consolas", 11), text_color=C_TEXT, width=w, anchor="w")
                lbl.pack(side="left", padx=2)
                labels[key] = lbl
            row_f._labels = labels
            self._kr_path_rows.append(row_f)

    # ------------------------------------------------------------------ Service actions

    def _svc_action(self, action, name, match_val):
        def _run():
            if action == "start":
                ok, msg = start_service(name)
            else:
                ok, msg = stop_service(name, match_val)
            self.after(0, lambda: self._show_toast(msg, ok))
            self.after(500, lambda: self._force_refresh())
        threading.Thread(target=_run, daemon=True).start()

    def _show_toast(self, msg, success=True):
        color = C_LIVE if success else C_DEAD
        self._toast_lbl.configure(text=f"  {msg}  ", text_color=color, height=28)
        self._toast_lbl.pack(fill="x", padx=12, pady=(0, 2), before=self._tabs)
        if self._toast_after_id:
            self.after_cancel(self._toast_after_id)
        self._toast_after_id = self.after(4000, lambda: self._toast_lbl.pack_forget())

    # ------------------------------------------------------------------ Refresh

    def _manual_refresh(self):
        self._force_refresh()

    def _force_refresh(self):
        self._refreshing = False
        self._do_refresh()

    def _do_refresh(self):
        if self._refreshing:
            self.after(self.REFRESH_MS, self._do_refresh)
            return
        self._refreshing = True
        threading.Thread(target=self._bg_scan, daemon=True).start()

    def _bg_scan(self):
        try:
            files = scan_json_files()
            svcs = scan_services()
            ports = scan_ports()
            walls = read_walls_json()
            kronos = read_kronos_json()
            gexdoc = read_gex_doctor_json()
            ts = datetime.now().strftime("%I:%M:%S %p")
        except Exception as exc:
            files, svcs, ports, walls, kronos, gexdoc, ts = [], [], [], {"walls": [], "meta": {}}, {"forecast": {}, "path": [], "model": {}, "status_info": {}, "meta": {}}, {"levels": {}, "meta": {"status": "ERROR", "age_str": str(exc), "source": ""}}, f"ERR: {exc}"
        self.after(0, lambda: self._apply(files, svcs, ports, walls, kronos, gexdoc, ts))

    def _apply(self, files, svcs, ports, walls, kronos, gexdoc, ts):
        # Overview tab
        for i, info in enumerate(files):
            if i < len(self._file_rows):
                self._file_rows[i].update_data(info)
        for i, info in enumerate(svcs):
            if i < len(self._svc_rows):
                self._svc_rows[i].update_data(info)
        for i, info in enumerate(ports):
            if i < len(self._port_rows):
                self._port_rows[i].update_data(info)

        # Depth Radar tab - service status
        svc_map = {s["name"]: s for s in svcs}
        dr_live = svc_map.get("Depth Radar", {})

        for dot, status_lbl, detail_lbl, info in [
            (self._dr_live_dot, self._dr_live_status, self._dr_live_detail, dr_live),
        ]:
            running = info.get("running", False)
            dot.set_color(C_LIVE if running else C_DEAD)
            status_lbl.configure(text="RUNNING" if running else "STOPPED", text_color=C_LIVE if running else C_DEAD)
            parts = []
            if info.get("pid"):
                parts.append(f"PID {info['pid']}")
            if info.get("mem_mb"):
                parts.append(f"{info['mem_mb']}MB")
            if info.get("uptime_str"):
                parts.append(info["uptime_str"])
            detail_lbl.configure(text="  ".join(parts))

        # Classification summary
        meta = walls.get("meta", {})
        counts = meta.get("counts", {})
        for tag in ("GENUINE", "SPOOF", "ICEBERG", "STALE"):
            if tag in self._cls_labels:
                self._cls_labels[tag].configure(text=str(counts.get(tag, 0)))

        # Walls meta
        status = meta.get("status", "")
        symbol = meta.get("symbol", "")
        wc = meta.get("wall_count", 0)
        age = meta.get("age_str", "")
        mid = meta.get("mid_price", 0)
        self._walls_meta_lbl.configure(
            text=f"{symbol}  |  {wc} walls  |  mid {mid:.2f}  |  updated {age} ago  |  {status}"
        )

        # Wall rows
        wall_list = walls.get("walls", [])
        for i, row_frame in enumerate(self._wall_rows):
            if i < len(wall_list):
                w = wall_list[i]
                labels = row_frame._labels
                side = w.get("side", "").upper()
                labels["side"].configure(text=side, text_color=C_LIVE if side == "BID" else C_SPOOF)
                labels["price"].configure(text=f"{w.get('price', 0):.2f}")
                labels["size"].configure(text=str(w.get("size", 0)))
                labels["max"].configure(text=str(w.get("max_size", 0)))
                cls = w.get("classification", "?")
                cls_color = {"GENUINE": C_GENUINE, "SPOOF": C_SPOOF, "ICEBERG": C_ICEBERG, "STALE": C_STALE_CLS}.get(cls, C_DIM)
                labels["cls"].configure(text=cls, text_color=cls_color)
                conf = w.get("confidence", 0)
                labels["conf"].configure(text=f"{int(conf * 100)}%")
                dur = w.get("duration_sec", 0)
                if dur < 60:
                    labels["age"].configure(text=f"{dur:.0f}s")
                elif dur < 3600:
                    labels["age"].configure(text=f"{dur / 60:.1f}m")
                else:
                    labels["age"].configure(text=f"{dur / 3600:.1f}h")
                labels["refills"].configure(text=str(w.get("refill_count", 0)))
                if not row_frame.winfo_ismapped():
                    row_frame.pack(fill="x", pady=0, padx=4)
            else:
                if row_frame.winfo_ismapped():
                    row_frame.pack_forget()

        # Kronos tab
        kr_svc = svc_map.get("Kronos Sidecar", {})
        kr_running = kr_svc.get("running", False)
        self._kr_dot.set_color(C_LIVE if kr_running else C_DEAD)
        self._kr_status.configure(text="RUNNING" if kr_running else "STOPPED", text_color=C_LIVE if kr_running else C_DEAD)
        kr_parts = []
        if kr_svc.get("pid"):
            kr_parts.append(f"PID {kr_svc['pid']}")
        if kr_svc.get("mem_mb"):
            kr_parts.append(f"{kr_svc['mem_mb']}MB")
        if kr_svc.get("uptime_str"):
            kr_parts.append(kr_svc["uptime_str"])
        self._kr_detail.configure(text="  ".join(kr_parts))

        fc = kronos.get("forecast", {})
        kr_meta = kronos.get("meta", {})
        direction = fc.get("direction", "--")
        confidence = fc.get("confidence", 0)
        dir_color = C_LIVE if direction == "bullish" else C_DEAD if direction == "bearish" else C_DIM
        arrow = "\u25B2" if direction == "bullish" else "\u25BC" if direction == "bearish" else "\u25C6"
        self._kr_direction.configure(text=f"{arrow} {direction.upper()}", text_color=dir_color)
        self._kr_confidence.configure(text=f"{confidence:.0f}%", text_color=dir_color)
        self._kr_meta_lbl.configure(text=f"{kr_meta.get('symbol', '')}  |  updated {kr_meta.get('age_str', '?')} ago  |  {kr_meta.get('status', '')}")

        move = fc.get("expectedMoveTicks", 0)
        ret = fc.get("expectedReturnPct", 0)
        slope = fc.get("forecastSlope", 0)
        vol = fc.get("forecastVolatility", 0)
        agree = fc.get("pathAgreement", 0)
        uncert = fc.get("uncertainty", 0)
        self._kr_metrics["move"].configure(text=f"{move:+.1f} ticks", text_color=C_LIVE if move > 0 else C_DEAD if move < 0 else C_DIM)
        self._kr_metrics["return"].configure(text=f"{ret:+.3f}%", text_color=C_LIVE if ret > 0 else C_DEAD if ret < 0 else C_DIM)
        self._kr_metrics["slope"].configure(text=f"{slope:+.2f}")
        self._kr_metrics["vol"].configure(text=f"{vol:.1f}")
        self._kr_metrics["agree"].configure(text=f"{agree:.0f}%")
        self._kr_metrics["uncert"].configure(text=f"{uncert:.0f}%")

        model = kronos.get("model", {})
        self._kr_model_lbl.configure(text=f"{model.get('name', '?')}  |  device: {model.get('device', '?')}  |  lookback: {model.get('lookback', 0)} bars  |  context: {model.get('context', 0)}  |  pred: {model.get('pred_bars', 0)} x {model.get('bar_period', '?')}  |  source: {model.get('source', '?')}")

        path_bars = kronos.get("path", [])
        for i, row_f in enumerate(self._kr_path_rows):
            if i < len(path_bars):
                b = path_bars[i]
                labels = row_f._labels
                labels["time"].configure(text=b.get("timestampUtc", "")[:19].replace("T", " "))
                labels["open"].configure(text=f"{b.get('open', 0):.2f}")
                labels["high"].configure(text=f"{b.get('high', 0):.2f}", text_color=C_LIVE)
                labels["low"].configure(text=f"{b.get('low', 0):.2f}", text_color=C_DEAD)
                labels["close"].configure(text=f"{b.get('close', 0):.2f}")
                labels["vol"].configure(text=f"{b.get('volume', 0):.0f}")
                if not row_f.winfo_ismapped():
                    row_f.pack(fill="x", pady=0, padx=4)
            else:
                if row_f.winfo_ismapped():
                    row_f.pack_forget()

        # GEX Doctor tab
        gd_svc = svc_map.get("GEX Doctor", {})
        gd_running = gd_svc.get("running", False)
        self._gd_dot.set_color(C_LIVE if gd_running else C_DEAD)
        self._gd_status.configure(text="RUNNING" if gd_running else "STOPPED", text_color=C_LIVE if gd_running else C_DEAD)
        gd_parts = []
        if gd_svc.get("pid"):
            gd_parts.append(f"PID {gd_svc['pid']}")
        if gd_svc.get("mem_mb"):
            gd_parts.append(f"{gd_svc['mem_mb']}MB")
        if gd_svc.get("uptime_str"):
            gd_parts.append(gd_svc["uptime_str"])
        self._gd_detail.configure(text="  ".join(gd_parts))

        lvl = gexdoc.get("levels", {})
        gd_meta = gexdoc.get("meta", {})
        gd_file_status = gd_meta.get("status", "MISSING")
        file_color = C_LIVE if gd_file_status == "LIVE" else (C_STALE if gd_file_status == "STALE" else C_DEAD)

        magnet = lvl.get("magnet")
        conf = lvl.get("confidence", 0)
        bias = lvl.get("bias", "no_vote")
        bias_color = C_LIVE if bias == "bullish" else (C_DEAD if bias == "bearish" else C_DIM)
        bias_arrow = "^" if bias == "bullish" else ("v" if bias == "bearish" else "-")

        self._gd_magnet.configure(text=f"{magnet:,.2f}" if magnet else "--", text_color=C_ACCENT if magnet else C_DIM)
        self._gd_conf.configure(text=f"{conf * 100:.0f}%" if conf else "", text_color=C_TEXT)
        self._gd_bias.configure(text=f"{bias_arrow} {bias.upper().replace('_', ' ')}", text_color=bias_color)
        self._gd_file_status.configure(text=f"{gd_file_status}  {gd_meta.get('age_str', '')} ago", text_color=file_color)

        level_map = {
            "flip":        (lvl.get("flip"),        C_STALE),
            "call_wall":   (lvl.get("call_wall"),   C_LIVE),
            "put_wall":    (lvl.get("put_wall"),    C_DEAD),
            "invalidation":(lvl.get("invalidation"),C_DIM),
            "pin_risk":    (lvl.get("pin_risk"),    C_TEXT),
        }
        for key, (val, color) in level_map.items():
            if val is not None:
                txt = f"{val:.0f}" if key == "pin_risk" else f"{val:,.2f}"
                self._gd_levels[key].configure(text=txt, text_color=color)
            else:
                self._gd_levels[key].configure(text="--", text_color=C_DIM)

        lean = lvl.get("lean", "")
        caveats = lvl.get("caveats", [])
        self._gd_lean.configure(text=lean or "(no read available)")

        meta_parts = [f"source: {gd_meta.get('source', '?')}"]
        if gd_meta.get("as_of"):
            meta_parts.append(f"as_of: {gd_meta['as_of'][:19].replace('T', ' ')} UTC")
        if caveats:
            meta_parts.append("caveats: " + " | ".join(caveats))
        self._gd_meta.configure(text="  |  ".join(meta_parts))

        # Status bar
        live_c = sum(1 for f in files if f["status"] == "LIVE")
        svc_c = sum(1 for s in svcs if s["running"])
        port_c = sum(1 for p in ports if p["open"])
        self._status_lbl.configure(text=f"{live_c} live  |  {svc_c} svc  |  {port_c} ports  |  {ts}")

        self._refreshing = False
        self.after(self.REFRESH_MS, self._do_refresh)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = DEEP6ControlCenter()
    app.mainloop()

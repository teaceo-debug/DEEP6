"""Create a Windows desktop shortcut for Depth Radar Desktop."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def create_shortcut() -> None:
    desktop = Path.home() / "Desktop"
    project_root = Path(__file__).resolve().parents[1]
    launch_pyw = project_root / "depth_radar_desktop" / "launch.pyw"

    # Find pythonw.exe next to the current interpreter
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = Path(sys.executable)  # fallback to python.exe

    try:
        import winshell

        link_path = os.path.join(str(desktop), "Depth Radar Desktop.lnk")
        icon_path = project_root / "depth_radar_desktop" / "assets" / "icon.ico"
        with winshell.shortcut(link_path) as link:
            link.path = str(pythonw)
            link.arguments = f'"{launch_pyw}"'
            link.working_directory = str(project_root)
            link.description = "Depth Radar Desktop — NQ MBO Wall Monitor"
            if icon_path.exists():
                link.icon_location = (str(icon_path), 0)
        print(f"Created shortcut: {link_path}")
    except ImportError:
        # winshell not installed — create a .bat launcher instead
        bat_path = desktop / "Depth Radar Desktop.bat"
        bat_content = f'@echo off\nstart "" "{pythonw}" "{launch_pyw}"\n'
        bat_path.write_text(bat_content, encoding="utf-8")
        print(f"Created shortcut: {bat_path}")


if __name__ == "__main__":
    create_shortcut()

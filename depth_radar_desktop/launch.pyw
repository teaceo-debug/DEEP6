"""Consoleless launcher for Depth Radar Desktop.

Run this file with pythonw.exe (or double-click on Windows) to launch
the application without a console window.

    pythonw depth_radar_desktop/launch.pyw
"""
import os
import sys

# Ensure the project root is on the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from depth_radar_desktop.__main__ import main

sys.exit(main())

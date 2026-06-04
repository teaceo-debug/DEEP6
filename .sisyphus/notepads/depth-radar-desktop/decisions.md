# depth-radar-desktop — Decisions

## Session: ses_17ea36d88ffe4uTLcVAPoqzP9P | 2026-06-01

### D-01: In-Process Architecture
Use a single Python process with threading.Thread for the engine, NOT a separate service process.
Reason: Simpler deployment (one process), user doesn't manage two services.

### D-02: Standalone Package at Repo Root
depth_radar_desktop/ lives at repo root, NOT inside deep6/ or deep6v2/.
Reason: Keeps engine pure, GUI is a consumer of the engine.

### D-03: Training is CLI-Only
No training controls in GUI. Research tab reads completed training output.
Reason: Training is CPU-intensive (hours), adding progress/abort UI is scope creep for v1.

### D-04: Rithmic Credentials via .env
Loaded from .env at project root. No GUI dialog for v1.
Reason: Matches existing project pattern in live_mbo_radar.py.

### D-05: Markets Closed = Frozen Display + Overlay
Live tab shows last walls with "Markets Closed" overlay message during non-RTH.
Reason: Better than blank screen, preserves context from last session.

### D-06: Touch Alerts = Visual Only
Row highlight + brief flash animation. No OS notifications, no sound.
Reason: Simple, no platform permission issues, v1 scope.

### D-07: Training Data Order
3-day file first (quick validation ~30 min), then 30-day file overnight (~1-4 hours).
Reason: Catch labeling/feature bugs cheaply before committing full dataset.

### D-08: Feature Gauges Selection
Show 4 gauges: Absorption Ratio, Delta Pressure (2s), Approach Speed, Wall Density.
NOT all 44 features. Most actionable for live trading decisions.

### D-09: No matplotlib/plotly in GUI
Pure Qt painting (QPainter, QSS) for all gauges and visualizations.
Reason: Avoid heavy dependencies, maintain native look and feel.

### D-10: PySide6 not qasync
Plain threading.Thread + Signal.emit for async-Qt bridge.
Reason: qasync is undermaintained and fragile on Windows (Metis finding).

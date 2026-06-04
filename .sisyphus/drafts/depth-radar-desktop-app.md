# Draft: Depth Radar V4 Desktop App + MBO Training

## Requirements (confirmed)
- Standalone desktop application (downloadable, lives on computer)
- Visual reference: "GEX Doctor" style software
- Represents all Depth Radar V4 data
- MBO data needs to be trained (V4 models produced)

## Available Resources
- MBO data: 2 Databento files ready (6.4 GB + 897 MB)
- Training pipeline: `scripts/train_depth_radar_v4.py` — fully operational
- MBO Wall Engine: 44 causal features, episode tracking, all tests passing
- Live Radar: supports Databento, Rithmic, and Replay sources
- Existing tech stack: Python 3.11, FastAPI, Next.js dashboard (web-based)

## Technical Decisions
- **Framework**: PySide6/Qt (Python native, lightweight, fast)
- **Scope**: Both Live + Research tabs
- **Training**: 3-day file first (quick model), then full 30-day for production
- **Live Data Source**: Rithmic (async-rithmic) — free, user's existing broker
- **Live Panel Views**: Active Walls Table + Feature Gauges + Touch/Interaction Alerts
- **Research Panel Views**: Episode Browser + Model Performance Dashboard
- TBD: Visual design (dark mode assumed for trading)
- TBD: Test strategy

## Open Questions
- Dark mode assumed? Any visual preferences?
- Test strategy for the app code?

## Scope Boundaries
- INCLUDE: Desktop app (PySide6), V4 model training, live + research modes, Rithmic connection
- EXCLUDE: Databento live feed, Replay mode in app, Training controls in UI, Wall heatmap/DOM ladder, Mini price chart

# Depth Radar Desktop

Standalone PySide6 desktop application for real-time NQ futures wall detection and classification using MBO (Market-by-Order) data from the DEEP6 engine.

## Quick Start

```bash
# From the DEEP6 project root:
pip install PySide6>=6.6 pydantic-settings>=2.0 pyarrow>=14.0 joblib>=1.3

# Launch the app (disconnected mode for testing)
python -m depth_radar_desktop --source none

# Launch with Rithmic live data
python -m depth_radar_desktop --source rithmic

# Dry-run (validate imports without opening window)
python -m depth_radar_desktop --dry-run
```

## Configuration

Create a `.env` file in the DEEP6 project root:

```env
RITHMIC_USER=your_username
RITHMIC_PASSWORD=your_password
RITHMIC_SYSTEM_NAME=Rithmic Paper Trading
RITHMIC_URL=wss://rituz00100.rithmic.com:443
RITHMIC_SYMBOL=NQM6
RITHMIC_EXCHANGE=CME
SOURCE=rithmic
MIN_WALL_SIZE=50
RTH_ONLY=true
```

## Training V4 Models

Before first use, train the V4 wall intent classifier and interaction predictor:

```bash
# Set Python path (Windows PowerShell)
$env:PYTHONPATH = "C:\Users\Tea\DEEP6"

# Quick training using cached parquet data (~30 seconds)
python scripts/train_depth_radar_v4.py \
  --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst \
  --output-dir data/depth_radar_v4 \
  --skip-label

# Full training from raw MBO data (~30-60 minutes)
python scripts/train_depth_radar_v4.py \
  --input data/databento/nq_mbo/raw_dbn/NQ_c_0_mbo_2026-04-08_2026-04-11.dbn.zst \
  --output-dir training_output/depth_radar_v4_3day
```

Models are saved to `deep6/models/intent_classifier_v4.joblib` and `deep6/models/interaction_predictor_v4.joblib`.

## Application Layout

### ⚡ Live Tab
- **Active Walls Table** — real-time wall detection with price, side, size, intent classification, state, confidence, and age
- **Feature Gauges** — absorption ratio, delta pressure, approach speed, and wall density meters
- **Touch Alerts** — notifications when price approaches detected walls

### 📊 Research Tab
- **Episode Browser** — browse historical wall episodes with filtering by intent (PASSIVE_REAL, SPOOF_LIKE, RESERVE_REFRESH, MIGRATORY)
- **Model Dashboard** — training metrics, confusion matrix, per-class precision/recall/F1, and top feature importance

## Command Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--source` | `rithmic` | Data source: `rithmic` (live), `replay` (MBO file), `none` (disconnected) |
| `--dry-run` | — | Validate imports and exit without opening window |

## Architecture

```
depth_radar_desktop/
├── __main__.py          # Entry point
├── main_window.py       # QMainWindow with tab layout
├── engine_bridge.py     # asyncio↔Qt threading bridge
├── config.py            # Pydantic settings from .env
├── theme.py             # Dark trading terminal QSS
├── constants.py         # App constants (tick size, intervals)
├── live/
│   ├── engine_worker.py # Manages EngineBridge lifecycle
│   ├── live_tab.py      # Assembles live panel widgets
│   ├── walls_table.py   # Active Walls QTableView
│   ├── feature_gauges.py# QPainter arc gauges
│   └── alerts_panel.py  # Touch/interaction alert log
├── research/
│   ├── research_tab.py  # Assembles research panel
│   ├── episode_browser.py # Parquet episode viewer
│   └── model_dashboard.py # Training metrics display
└── widgets/
    └── status_bar.py    # Connection/model status bar
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: PySide6` | `pip install PySide6>=6.6` |
| `Models: ✗ Not Loaded` | Run the training pipeline (see Training section) |
| `Disconnected` status | Configure Rithmic credentials in `.env` |
| App won't start | Run `python -m depth_radar_desktop --dry-run` to diagnose |

## Requirements

- Python 3.11+
- PySide6 >= 6.6
- pandas, numpy, pyarrow (for parquet data)
- pydantic-settings (for .env configuration)
- joblib (for model loading)
- DEEP6 project with trained V4 models

## Defaults

- App name: `Depth Radar Desktop`
- Version: `0.1.0`
- Default symbol: `NQ`
- Tick size: `0.25`
- UI refresh interval: `500 ms`
- Default window size: `1400 x 900`
- Minimum window size: `1000 x 600`
- Touch alert band: `4 ticks`
- Max queued touch alerts: `50`
- Markets-closed timeout: `60 seconds`

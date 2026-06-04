# P2 Learnings

## 2026-05-12 Linux/WSL import fix
- deep6/copilot/vision.py previously initialized ctypes.windll.user32 at module import time, which crashes on Linux/WSL because windll is Windows-only.
- Fixed by moving ctypes/wintypes import and user32 initialization inside ScreenCapture.find_nt8_window() behind a sys.platform == 'win32' guard, allowing copilot tests to import and run cross-platform.

## 2026-05-12 token_budget migration issue
- The canonical `budget.py` tracker lacked `can_make_call`, `get_status`, and `record_usage(call_type=...)`, so the delete/swap caused runtime breaks until a compatibility patch was added in `deep6/copilot/__init__.py`.


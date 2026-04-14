#!/usr/bin/env bash
# deep6_up.sh — Bring up the entire DEEP6 stack
# Usage: ./scripts/deep6_up.sh [--demo] [--force]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$REPO_ROOT/.deep6"
LOG_DIR="$REPO_ROOT/logs"
DEMO=0
FORCE=0

# ── arg parse ──────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --demo)  DEMO=1  ;;
    --force) FORCE=1 ;;
  esac
done

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── colors ─────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'; BLD='\033[1m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YEL}!${RST} $*"; }
err()  { echo -e "  ${RED}✗${RST} $*"; }
die()  { err "$*"; exit 1; }

# ── helpers ────────────────────────────────────────────────────────────────
pid_running() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }

wait_http() {
  local url="$1" max="$2" i=0
  while [ $i -lt "$max" ]; do
    if curl -fsS --max-time 1 "$url" >/dev/null 2>&1; then return 0; fi
    sleep 1; i=$((i+1))
  done
  return 1
}

kill_port() {
  local port="$1"
  local pids
  if [[ "$OSTYPE" == darwin* ]]; then
    pids=$(lsof -ti tcp:"$port" 2>/dev/null || true)
  else
    pids=$(fuser "$port/tcp" 2>/dev/null | tr ' ' '\n' | grep -v '^$' || true)
  fi
  [ -z "$pids" ] && return 0
  for p in $pids; do
    warn "Port $port in use by PID $p"
    if [ "$FORCE" -eq 0 ]; then
      read -rp "    Kill it? [y/N] " ans
      [[ "$ans" =~ ^[Yy]$ ]] || die "Aborted — port $port blocked"
    fi
    kill -TERM "$p" 2>/dev/null || true
    local i=0
    while kill -0 "$p" 2>/dev/null && [ $i -lt 5 ]; do sleep 1; i=$((i+1)); done
    kill -0 "$p" 2>/dev/null && kill -KILL "$p" 2>/dev/null || true
    ok "Cleared port $port (killed PID $p)"
  done
}

# ════════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BLD}DEEP6 startup sequence${RST}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── pre-flight ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BLD}Pre-flight checks${RST}"

# Python 3.12+
PYTHON="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then PYTHON="$(command -v python3 || command -v python)"; fi
PY_VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
PY_MAJOR="${PY_VER%%.*}"
PY_MINOR="${PY_VER#*.}"
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 12 ]; }; then
  die "Python 3.12+ required (found $PY_VER). Install from python.org"
fi
ok "Python $PY_VER"

# .venv
VENV_PYTHON="$REPO_ROOT/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
  err ".venv not found"
  echo "    Run: python3.12 -m venv $REPO_ROOT/.venv && $REPO_ROOT/.venv/bin/pip install -r $REPO_ROOT/requirements.txt"
  die ".venv required"
fi
UVICORN="$REPO_ROOT/.venv/bin/uvicorn"
[ -x "$UVICORN" ] || die "uvicorn not in .venv — run: .venv/bin/pip install uvicorn"
ok ".venv present"

# Node + npm
command -v node >/dev/null 2>&1 || die "Node.js not found — install via nvm or brew"
command -v npm  >/dev/null 2>&1 || die "npm not found"
NODE_VER=$(node --version)
ok "Node $NODE_VER"

# dashboard/node_modules
DASH="$REPO_ROOT/dashboard"
if [ ! -d "$DASH/node_modules" ]; then
  warn "node_modules missing — running npm install..."
  (cd "$DASH" && npm install) || die "npm install failed"
  ok "npm install complete"
else
  ok "dashboard/node_modules present"
fi

# ports free / clearable
echo ""
echo -e "${BLD}Port checks${RST}"
kill_port 8000
kill_port 3000

# ── idempotency — already running? ──────────────────────────────────────────
if pid_running "$PID_DIR/backend.pid" && pid_running "$PID_DIR/frontend.pid"; then
  echo ""
  warn "DEEP6 is already running."
  BE_PID=$(cat "$PID_DIR/backend.pid")
  FE_PID=$(cat "$PID_DIR/frontend.pid")
  echo ""
  echo -e "${BLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RST}"
  echo -e "${BLD} DEEP6 ALREADY UP${RST}"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo -e "  Backend   :8000  (PID $BE_PID)"
  echo -e "  Frontend  :3000  (PID $FE_PID)"
  echo ""
  echo -e "  Dashboard → http://localhost:3000"
  echo -e "  Stop      → ./scripts/deep6_down.sh"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  exit 0
fi

# ── start backend ───────────────────────────────────────────────────────────
echo ""
echo -e "${BLD}Starting backend${RST}"
cd "$REPO_ROOT"
"$UVICORN" deep6.api.app:app --port 8000 \
  > "$LOG_DIR/uvicorn.log" 2>&1 &
BE_PID=$!
echo "$BE_PID" > "$PID_DIR/backend.pid"

echo -n "  Waiting for :8000"
if wait_http "http://localhost:8000/api/session/status" 10; then
  echo ""
  ok "Backend up (PID $BE_PID)"
else
  echo ""
  err "Backend did not respond in 10s — check $LOG_DIR/uvicorn.log"
  tail -20 "$LOG_DIR/uvicorn.log" | sed 's/^/    /'
  die "Backend startup failed"
fi

# ── start frontend ──────────────────────────────────────────────────────────
echo ""
echo -e "${BLD}Starting frontend${RST}"
cd "$DASH"
npx next dev -p 3000 \
  > "$LOG_DIR/next.log" 2>&1 &
FE_PID=$!
echo "$FE_PID" > "$PID_DIR/frontend.pid"
cd "$REPO_ROOT"

echo -n "  Waiting for :3000"
if wait_http "http://localhost:3000/" 20; then
  echo ""
  ok "Frontend up (PID $FE_PID)"
else
  echo ""
  err "Frontend did not respond in 20s — check $LOG_DIR/next.log"
  tail -20 "$LOG_DIR/next.log" | sed 's/^/    /'
  die "Frontend startup failed"
fi

# ── start demo broadcaster (optional) ───────────────────────────────────────
DEMO_PID=""
if [ "$DEMO" -eq 1 ]; then
  echo ""
  echo -e "${BLD}Starting demo broadcaster${RST}"
  cd "$REPO_ROOT"
  "$VENV_PYTHON" scripts/demo_broadcast.py --rate 2.0 \
    > "$LOG_DIR/demo.log" 2>&1 &
  DEMO_PID=$!
  echo "$DEMO_PID" > "$PID_DIR/demo.pid"
  sleep 1
  if kill -0 "$DEMO_PID" 2>/dev/null; then
    ok "Demo broadcaster up (PID $DEMO_PID)"
  else
    err "Demo broadcaster exited immediately — check $LOG_DIR/demo.log"
  fi
fi

# ── report ───────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${BLD}${GRN} DEEP6 IS UP${RST}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "  Backend   :8000  (PID $BE_PID)"
echo -e "  Frontend  :3000  (PID $FE_PID)"
if [ -n "$DEMO_PID" ]; then
  echo -e "  Demo      :      (PID $DEMO_PID)"
else
  echo -e "  Demo      :      (not started — use --demo)"
fi
echo ""
echo -e "  Dashboard → http://localhost:3000"
echo -e "  Stop      → ./scripts/deep6_down.sh"
echo -e "  Status    → ./scripts/deep6_status.sh"
echo -e "  Logs      → tail -f logs/*.log"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

#!/usr/bin/env bash
# deep6_down.sh — Gracefully stop the DEEP6 stack
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$REPO_ROOT/.deep6"

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[0;33m'; BLD='\033[1m'; RST='\033[0m'
ok()   { echo -e "  ${GRN}✓${RST} $*"; }
warn() { echo -e "  ${YEL}!${RST} $*"; }

stop_pid_file() {
  local label="$1"
  local pidfile="$2"

  if [ ! -f "$pidfile" ]; then
    warn "$label  — no PID file (already stopped?)"
    return
  fi

  local pid
  pid=$(cat "$pidfile")

  if ! kill -0 "$pid" 2>/dev/null; then
    warn "$label  — PID $pid not running (stale PID file)"
    rm -f "$pidfile"
    return
  fi

  echo -n "  Stopping $label (PID $pid)..."
  kill -TERM "$pid" 2>/dev/null || true

  local i=0
  while kill -0 "$pid" 2>/dev/null && [ $i -lt 5 ]; do
    sleep 1; i=$((i+1))
    echo -n "."
  done

  if kill -0 "$pid" 2>/dev/null; then
    kill -KILL "$pid" 2>/dev/null || true
    echo ""
    ok "$label  — force-killed (PID $pid)"
  else
    echo ""
    ok "$label  — stopped (PID $pid)"
  fi

  rm -f "$pidfile"
}

echo ""
echo -e "${BLD}Stopping DEEP6${RST}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

stop_pid_file "Demo       " "$PID_DIR/demo.pid"
stop_pid_file "Frontend   " "$PID_DIR/frontend.pid"
stop_pid_file "Backend    " "$PID_DIR/backend.pid"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  DEEP6 is ${BLD}down${RST}."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

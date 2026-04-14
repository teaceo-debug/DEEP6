#!/usr/bin/env bash
# deep6_status.sh — Show state of each DEEP6 process
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_DIR="$REPO_ROOT/.deep6"

GRN='\033[0;32m'; RED='\033[0;31m'; YEL='\033[0;33m'; DIM='\033[2m'; BLD='\033[1m'; RST='\033[0m'

uptime_str() {
  local pid="$1"
  if [[ "$OSTYPE" == darwin* ]]; then
    local started
    started=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs -I{} date -j -f "%a %b %d %T %Y" "{}" "+%s" 2>/dev/null || echo "")
    [ -z "$started" ] && { echo "?"; return; }
    local now; now=$(date +%s)
    local secs=$(( now - started ))
    printf "%dh %02dm" $((secs/3600)) $(( (secs%3600)/60 ))
  else
    local started
    started=$(ps -o lstart= -p "$pid" 2>/dev/null | xargs -I{} date -d "{}" "+%s" 2>/dev/null || echo "")
    [ -z "$started" ] && { echo "?"; return; }
    local now; now=$(date +%s)
    local secs=$(( now - started ))
    printf "%dh %02dm" $((secs/3600)) $(( (secs%3600)/60 ))
  fi
}

check_http() {
  local url="$1"
  curl -fsS --max-time 2 "$url" >/dev/null 2>&1 && echo "OK" || echo "NO RESPONSE"
}

status_line() {
  local label="$1"
  local pidfile="$2"
  local port="$3"
  local health_url="$4"

  if [ ! -f "$pidfile" ]; then
    printf "  %-12s ${YEL}[STOPPED]${RST}\n" "$label"
    return
  fi

  local pid; pid=$(cat "$pidfile")

  if ! kill -0 "$pid" 2>/dev/null; then
    printf "  %-12s ${RED}[DEAD]${RST}    PID $pid (stale)\n" "$label"
    return
  fi

  local up; up=$(uptime_str "$pid")
  local http_status=""
  if [ -n "$health_url" ]; then
    local resp; resp=$(check_http "$health_url")
    if [ "$resp" = "OK" ]; then
      http_status=" ${DIM}http ${GRN}${resp}${RST}"
    else
      http_status=" ${DIM}http ${RED}${resp}${RST}"
    fi
  fi

  if [ -n "$port" ]; then
    printf "  %-12s ${GRN}[RUNNING]${RST} :%-5s (PID %s, uptime %s)%b\n" \
      "$label" "$port" "$pid" "$up" "$http_status"
  else
    printf "  %-12s ${GRN}[RUNNING]${RST}        (PID %s, uptime %s)\n" \
      "$label" "$pid" "$up"
  fi
}

echo ""
echo -e "${BLD}DEEP6 Status${RST}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
status_line "Backend"  "$PID_DIR/backend.pid"  "8000" "http://localhost:8000/api/session/status"
status_line "Frontend" "$PID_DIR/frontend.pid" "3000" "http://localhost:3000/"
status_line "Demo"     "$PID_DIR/demo.pid"     ""     ""
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

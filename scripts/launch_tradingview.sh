#!/bin/bash
# Launch TradingView Desktop with Chrome DevTools Protocol debugging enabled.
# Required for tradingview-mcp (Claude ↔ TradingView bridge).
#
# Usage:
#   ./scripts/launch_tradingview.sh
#
# After launch, verify in Claude Code:
#   "Use tv_health_check to verify TradingView is connected"

PORT=9222

# macOS path
TV_APP="/Applications/TradingView.app/Contents/MacOS/TradingView"

if [ ! -f "$TV_APP" ]; then
    echo "TradingView Desktop not found at $TV_APP"
    echo "Download from: https://www.tradingview.com/desktop/"
    exit 1
fi

echo "Launching TradingView with --remote-debugging-port=$PORT..."
"$TV_APP" --remote-debugging-port=$PORT &

echo "TradingView launched (PID: $!)"
echo "CDP endpoint: http://localhost:$PORT"
echo ""
echo "Verify in Claude Code:"
echo '  "Use tv_health_check to verify TradingView is connected"'

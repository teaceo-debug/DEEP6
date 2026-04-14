"use client"

/**
 * LiveTab — full LIVE tab layout.
 *
 * Layout per D-07, D-09, D-10, D-11, D-12:
 *
 * ┌─────────────────────────────────────────────────────────┐
 * │ CHART AREA (flex-1, ~70%)    │ RIGHT PANEL (w-80, 320px) │
 * │ id="footprint-chart-mount"   │ <RegimePanel />           │
 * │ Plan 04 mounts LW Charts here│ <SignalFeed />            │
 * ├─────────────────────────────────────────────────────────┤
 * │ BOTTOM PANEL — <PositionPanel />                        │
 * └─────────────────────────────────────────────────────────┘
 *
 * Chart mount div: exact id="footprint-chart-mount" required by Plan 04.
 */

import RegimePanel from "@/components/RegimePanel"
import SignalFeed from "@/components/SignalFeed"
import PositionPanel from "@/components/PositionPanel"

export default function LiveTab() {
  return (
    <div className="flex flex-col h-full p-3 gap-3">
      {/* Main row: chart + right panel */}
      <div className="flex flex-1 gap-3 min-h-0">
        {/* Chart area — Plan 04 mounts Lightweight Charts here */}
        <div
          id="footprint-chart-mount"
          className="flex-1 bg-zinc-900 rounded-lg min-h-[500px] relative border border-zinc-800"
        >
          {/* Placeholder text — Plan 04 will replace with LW Charts canvas */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-zinc-700">
              <div className="text-xs tracking-widest mb-1">FOOTPRINT CHART</div>
              <div className="text-[10px]">Plan 04 — Lightweight Charts mount point</div>
            </div>
          </div>
        </div>

        {/* Right panel: RegimePanel + SignalFeed */}
        <div className="w-80 flex flex-col gap-3 overflow-y-auto">
          <RegimePanel />
          <SignalFeed />
        </div>
      </div>

      {/* Bottom panel: PositionPanel */}
      <div className="h-48 border-t border-zinc-800 pt-2 flex-shrink-0">
        <PositionPanel />
      </div>
    </div>
  )
}

"use client"

/**
 * LiveTab — full LIVE tab layout.
 *
 * Layout per D-07, D-09, D-10, D-11, D-12:
 *
 * ┌─────────────────────────────────────────────────────────┐
 * │ CHART AREA (flex-1, ~70%)    │ RIGHT PANEL (w-80, 320px) │
 * │ <FootprintChart />           │ <RegimePanel />           │
 * │ LW Charts v5.1 custom series │ <SignalFeed />            │
 * ├─────────────────────────────────────────────────────────┤
 * │ BOTTOM PANEL — <PositionPanel />                        │
 * └─────────────────────────────────────────────────────────┘
 *
 * FootprintChart uses dynamic import with ssr: false — LW Charts requires
 * browser APIs (ResizeObserver, canvas) unavailable during SSR.
 */

import dynamic from "next/dynamic"
import RegimePanel from "@/components/RegimePanel"
import SignalFeed from "@/components/SignalFeed"
import PositionPanel from "@/components/PositionPanel"

// ssr: false required — LW Charts uses ResizeObserver and canvas (browser-only)
const FootprintChart = dynamic(() => import("./FootprintChart"), {
  ssr: false,
  loading: () => (
    <div className="absolute inset-0 flex items-center justify-center">
      <div className="text-center text-zinc-700">
        <div className="text-xs tracking-widest mb-1">FOOTPRINT CHART</div>
        <div className="text-[10px]">Loading Lightweight Charts...</div>
      </div>
    </div>
  ),
})

export default function LiveTab() {
  return (
    <div className="flex flex-col h-full p-3 gap-3">
      {/* Main row: chart + right panel */}
      <div className="flex flex-1 gap-3 min-h-0">
        {/* Chart area — FootprintChart mounts LW Charts canvas here */}
        <div className="flex-1 bg-zinc-900 rounded-lg min-h-[500px] relative border border-zinc-800">
          <FootprintChart />
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

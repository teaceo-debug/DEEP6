"use client"

/**
 * RegimePanel — shows GEX regime badge, Kronos bias gauge, signal quality.
 *
 * Per D-11: Right panel with Kronos bias gauge.
 * Reads useLiveStore for regime + latest signal data.
 * Threat T-10-09: categories_firing truncated before render.
 */

import { useLiveStore } from "@/store/live"
import KronosBiasGauge from "@/components/KronosBiasGauge"

// Simple progress bar component (Tremor not available — use Tailwind)
function ProgressBar({ value, className }: { value: number; className?: string }) {
  const pct = Math.max(0, Math.min(100, value * 100))
  return (
    <div className={`h-2 bg-zinc-700 rounded-full overflow-hidden ${className ?? ""}`}>
      <div
        className="h-full rounded-full bg-amber-400 transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

function regimeStyles(regime: string): { textColor: string; label: string; borderColor: string } {
  if (regime.startsWith("POSITIVE")) {
    return { textColor: "text-green-400", label: "MEAN REVERTING", borderColor: "border-green-600" }
  }
  if (regime.startsWith("NEGATIVE")) {
    return { textColor: "text-red-400", label: "AMPLIFYING", borderColor: "border-red-600" }
  }
  return { textColor: "text-zinc-400", label: "NEUTRAL", borderColor: "border-zinc-600" }
}

export default function RegimePanel() {
  const regime = useLiveStore((s) => s.regime)
  const signals = useLiveStore((s) => s.signals)

  const latest = signals[0] ?? null
  const kronosBias = latest?.kronos_bias ?? 50
  const engineAgreement = latest?.engine_agreement ?? 0
  const categoryCount = latest?.category_count ?? 0

  const { textColor, label, borderColor } = regimeStyles(regime)

  return (
    <div className="flex flex-col gap-4 p-3 bg-zinc-900 rounded-lg border border-zinc-800">
      {/* GEX Regime */}
      <div>
        <div className="text-[10px] text-zinc-500 tracking-widest mb-1">GEX REGIME</div>
        <div className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-xs font-semibold ${textColor} ${borderColor} bg-zinc-800/50`}>
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${regime.startsWith("POSITIVE") ? "bg-green-400" : regime.startsWith("NEGATIVE") ? "bg-red-400" : "bg-zinc-400"}`} />
          {regime}
        </div>
        <div className={`text-[10px] mt-0.5 ${textColor} opacity-70`}>{label}</div>
      </div>

      {/* Kronos Bias Gauge */}
      <div className="flex flex-col items-center">
        <KronosBiasGauge value={kronosBias} />
      </div>

      {/* Signal Quality */}
      <div>
        <div className="text-[10px] text-zinc-500 tracking-widest mb-1.5">SIGNAL QUALITY</div>
        <div className="flex items-center justify-between text-xs text-zinc-400 mb-1">
          <span>Engine agreement</span>
          <span className="font-mono">{(engineAgreement * 100).toFixed(0)}%</span>
        </div>
        <ProgressBar value={engineAgreement} />

        <div className="flex items-center justify-between text-xs text-zinc-400 mt-2">
          <span>Categories active</span>
          <span className="font-mono text-amber-400">
            {categoryCount}/8
          </span>
        </div>
        <div className="h-2 bg-zinc-700 rounded-full overflow-hidden mt-1">
          <div
            className="h-full rounded-full bg-amber-400 transition-all duration-300"
            style={{ width: `${(categoryCount / 8) * 100}%` }}
          />
        </div>
      </div>

      {/* Latest signal timestamp */}
      {latest && (
        <div className="text-[9px] text-zinc-600 border-t border-zinc-800 pt-2">
          Last signal: {new Date(latest.ts * 1000).toLocaleTimeString()}
          {" · "} Bar #{latest.bar_index_in_session}
        </div>
      )}
      {!latest && (
        <div className="text-[9px] text-zinc-600">No signals yet</div>
      )}
    </div>
  )
}

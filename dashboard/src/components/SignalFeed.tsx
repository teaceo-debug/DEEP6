"use client"

/**
 * SignalFeed — scrollable list of live signal events with tier color coding.
 *
 * Per D-11: Right panel signal feed (TYPE_A/B/C alerts with category breakdown).
 * Threat T-10-09: categories_firing truncated to 60 chars before render — no innerHTML.
 */

import { useLiveStore } from "@/store/live"
import type { SignalEvent } from "@/store/live"

function tierStyles(tier: string): {
  bg: string
  border: string
  badge: string
  badgeText: string
} {
  if (tier === "TYPE_A") {
    return {
      bg: "bg-amber-950/50",
      border: "border-amber-500",
      badge: "bg-amber-500/20 border-amber-500/40",
      badgeText: "text-amber-300",
    }
  }
  if (tier === "TYPE_B") {
    return {
      bg: "bg-orange-950/50",
      border: "border-orange-600",
      badge: "bg-orange-500/20 border-orange-600/40",
      badgeText: "text-orange-300",
    }
  }
  // TYPE_C and anything else
  return {
    bg: "bg-zinc-800",
    border: "border-zinc-600",
    badge: "bg-zinc-700/50 border-zinc-600/40",
    badgeText: "text-zinc-300",
  }
}

function DirectionArrow({ direction }: { direction: number }) {
  if (direction > 0) return <span className="text-green-400 text-lg leading-none">▲</span>
  if (direction < 0) return <span className="text-red-400 text-lg leading-none">▼</span>
  return <span className="text-zinc-500 text-lg leading-none">—</span>
}

function SignalCard({ signal }: { signal: SignalEvent }) {
  const styles = tierStyles(signal.tier)
  // T-10-09: truncate categories_firing to 60 chars; React escapes strings automatically
  const categoriesText = signal.categories_firing.join(", ").slice(0, 60)
  const timeStr = new Date(signal.ts * 1000).toLocaleTimeString()

  return (
    <div className={`rounded border p-2.5 ${styles.bg} ${styles.border} flex flex-col gap-1.5`}>
      {/* Header row: badge + score + direction */}
      <div className="flex items-center justify-between">
        <span
          className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${styles.badge} ${styles.badgeText}`}
        >
          {signal.tier}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-zinc-200 font-mono text-base font-semibold">
            {signal.total_score.toFixed(1)}
          </span>
          <DirectionArrow direction={signal.direction} />
        </div>
      </div>

      {/* Categories firing */}
      <div className="text-[10px] text-zinc-400 leading-tight truncate">
        {categoriesText || "—"}
      </div>

      {/* Bottom row: GEX regime + engine agreement + time */}
      <div className="flex items-center justify-between text-[9px] text-zinc-500">
        <span>{signal.gex_regime}</span>
        <span>{(signal.engine_agreement * 100).toFixed(0)}% agree</span>
        <span>{timeStr}</span>
      </div>
    </div>
  )
}

export default function SignalFeed() {
  const signals = useLiveStore((s) => s.signals)

  return (
    <div className="flex flex-col bg-zinc-900 rounded-lg border border-zinc-800">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800">
        <span className="text-[10px] font-semibold tracking-widest text-zinc-400">SIGNAL FEED</span>
        {signals.length > 0 && (
          <span className="inline-flex items-center px-1.5 py-0.5 rounded bg-amber-500/20 border border-amber-500/30 text-amber-300 text-[10px] font-mono">
            {signals.length}
          </span>
        )}
      </div>

      {/* Scrollable list */}
      <div className="flex flex-col gap-2 p-2 max-h-[400px] overflow-y-auto">
        {signals.length === 0 ? (
          <div className="py-8 text-center text-xs text-zinc-500">
            Waiting for live data...
          </div>
        ) : (
          signals.map((sig, i) => <SignalCard key={`${sig.ts}-${i}`} signal={sig} />)
        )}
      </div>
    </div>
  )
}

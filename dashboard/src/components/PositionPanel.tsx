"use client"

/**
 * PositionPanel — open positions, daily P&L, closed trades, signal performance summary.
 *
 * Per D-12: Bottom panel with P&L, closed trades, per-tier win rate stats.
 * Per D-03: green/red ONLY for P&L column — not used as direction indicators.
 */

import { useLiveStore } from "@/store/live"
import type { TradeEvent } from "@/store/live"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

// Per-tier stats computed from trades array
interface TierStats {
  count: number
  wins: number
  winRate: number
  avgPnl: number
}

function computeTierStats(trades: TradeEvent[]): Record<string, TierStats> {
  const tiers = ["TYPE_A", "TYPE_B", "TYPE_C"]
  const result: Record<string, TierStats> = {}
  for (const tier of tiers) {
    const t = trades.filter((tr) => tr.signal_tier === tier)
    const wins = t.filter((tr) => tr.pnl > 0).length
    const avgPnl = t.length > 0 ? t.reduce((s, tr) => s + tr.pnl, 0) / t.length : 0
    result[tier] = {
      count: t.length,
      wins,
      winRate: t.length > 0 ? (wins / t.length) * 100 : 0,
      avgPnl,
    }
  }
  return result
}

function formatPnl(pnl: number): string {
  const sign = pnl >= 0 ? "+" : ""
  return `${sign}$${Math.abs(pnl).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function EventTypeBadge({ eventType }: { eventType: string }) {
  if (eventType === "TARGET_HIT") {
    return (
      <span className="inline-flex px-1 py-0.5 rounded text-[9px] font-semibold bg-green-500/20 border border-green-500/30 text-green-300">
        TGT
      </span>
    )
  }
  if (eventType === "STOP_HIT") {
    return (
      <span className="inline-flex px-1 py-0.5 rounded text-[9px] font-semibold bg-red-500/20 border border-red-500/30 text-red-300">
        STP
      </span>
    )
  }
  return (
    <span className="inline-flex px-1 py-0.5 rounded text-[9px] font-semibold bg-zinc-700 text-zinc-400">
      {eventType.slice(0, 3)}
    </span>
  )
}

// Signal performance summary per tier
function SignalPerformanceSummary({ stats }: { stats: Record<string, TierStats> }) {
  const tiers = ["TYPE_A", "TYPE_B", "TYPE_C"]
  const tierColors: Record<string, string> = {
    TYPE_A: "text-amber-400",
    TYPE_B: "text-orange-400",
    TYPE_C: "text-zinc-400",
  }

  return (
    <div className="flex gap-2">
      {tiers.map((tier) => {
        const s = stats[tier]
        return (
          <div
            key={tier}
            className="flex-1 bg-zinc-800/60 rounded border border-zinc-700 px-2 py-1.5"
          >
            <div className={`text-[9px] font-bold tracking-wide mb-1 ${tierColors[tier]}`}>
              {tier}
            </div>
            {s.count === 0 ? (
              <div className="text-[9px] text-zinc-600">No trades</div>
            ) : (
              <>
                <div className="text-[10px] font-mono text-zinc-300">
                  {s.winRate.toFixed(0)}% WR
                </div>
                <div className="text-[9px] text-zinc-500">{s.count} trades</div>
                <div
                  className={`text-[9px] font-mono ${s.avgPnl >= 0 ? "text-green-400" : "text-red-400"}`}
                >
                  avg {s.avgPnl >= 0 ? "+" : ""}{s.avgPnl.toFixed(2)}
                </div>
              </>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function PositionPanel() {
  const trades = useLiveStore((s) => s.trades)
  const dailyPnl = useLiveStore((s) => s.dailyPnl)

  const recentTrades = trades.slice(0, 10)
  const closedCount = trades.length
  const winCount = trades.filter((t) => t.pnl > 0).length
  const winRate = closedCount > 0 ? (winCount / closedCount) * 100 : 0

  const tierStats = computeTierStats(trades)

  const pnlColor = dailyPnl >= 0 ? "text-green-400" : "text-red-400"

  return (
    <div className="flex flex-col h-full gap-2">
      {/* Header */}
      <div className="text-[10px] font-semibold tracking-widest text-zinc-400">POSITIONS</div>

      <div className="flex gap-3 min-h-0 flex-1">
        {/* Left: P&L + signal performance summary */}
        <div className="flex flex-col gap-2 w-56 flex-shrink-0">
          {/* Today's P&L */}
          <div className="bg-zinc-900 rounded border border-zinc-800 px-3 py-2">
            <div className="text-[9px] text-zinc-500 tracking-widest mb-0.5">TODAY&apos;S P&amp;L</div>
            <div className={`text-xl font-bold font-mono leading-tight ${pnlColor}`}>
              {formatPnl(dailyPnl)}
            </div>
            <div className="text-[9px] text-zinc-500 mt-0.5">
              {closedCount > 0
                ? `${winRate.toFixed(0)}% WR · ${closedCount} trades`
                : "No trades today"}
            </div>
          </div>

          {/* Per-tier performance */}
          <SignalPerformanceSummary stats={tierStats} />
        </div>

        {/* Right: Recent trades table */}
        <div className="flex-1 overflow-auto">
          <div className="text-[9px] text-zinc-600 mb-1">RECENT TRADES (last 10)</div>
          {recentTrades.length === 0 ? (
            <div className="flex items-center justify-center h-16 text-xs text-zinc-600">
              No trades today
            </div>
          ) : (
            <Table className="text-[10px]">
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0 pl-1">Time</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">Side</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">Entry</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">Exit</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">P&L</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">Bars</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">Tier</TableHead>
                  <TableHead className="h-6 text-[9px] text-zinc-500 py-0">Type</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {recentTrades.map((trade) => {
                  const pnlCls = trade.pnl >= 0 ? "text-green-400" : "text-red-400"
                  // Side: LONG/SHORT text — green/red text per spec (side display, not direction prediction)
                  const sideCls = trade.side === "LONG" ? "text-green-400" : "text-red-400"
                  const timeStr = new Date(trade.ts * 1000).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })
                  return (
                    <TableRow
                      key={trade.position_id}
                      className="border-zinc-800/50 hover:bg-zinc-800/30"
                    >
                      <TableCell className="py-0.5 pl-1 text-zinc-500">{timeStr}</TableCell>
                      <TableCell className={`py-0.5 font-semibold ${sideCls}`}>
                        {trade.side}
                      </TableCell>
                      <TableCell className="py-0.5 font-mono text-zinc-300">
                        {trade.entry_price.toFixed(2)}
                      </TableCell>
                      <TableCell className="py-0.5 font-mono text-zinc-300">
                        {trade.exit_price > 0 ? trade.exit_price.toFixed(2) : "—"}
                      </TableCell>
                      <TableCell className={`py-0.5 font-mono font-semibold ${pnlCls}`}>
                        {formatPnl(trade.pnl)}
                      </TableCell>
                      <TableCell className="py-0.5 text-zinc-400">{trade.bars_held}</TableCell>
                      <TableCell className="py-0.5 text-zinc-500">{trade.signal_tier}</TableCell>
                      <TableCell className="py-0.5">
                        <EventTypeBadge eventType={trade.event_type} />
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          )}
        </div>
      </div>
    </div>
  )
}

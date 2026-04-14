"use client"

/**
 * BacktestTab — full BACKTEST tab with three subtabs: Results, Sweep, Signals.
 *
 * Per D-08: BACKTEST tab layout.
 * Per D-13: Left column 320px config form + main area (flex-1).
 * Per D-14/15: Equity curve + trade table in results subtab.
 * Per D-16: Optuna sweep in sweep subtab.
 * Per DASH-02: Signal win rate / P&L breakdown by tier in signals subtab.
 * Per DASH-04: Parameter evolution note in sweep subtab.
 */

import { useRef } from "react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import BacktestConfig from "@/components/BacktestConfig"
import EquityCurve, { type BacktestRow } from "@/components/EquityCurve"
import TradeTable from "@/components/TradeTable"
import OptunaSweepPanel from "@/components/OptunaSweepPanel"
import { useBacktestStore } from "@/store/backtest"

interface Props {
  isActive?: boolean
}

function SignalStats({ rows }: { rows: BacktestRow[] }) {
  // Group by tier
  const tierGroups: Record<string, BacktestRow[]> = {}
  for (const r of rows) {
    if (!tierGroups[r.tier]) tierGroups[r.tier] = []
    tierGroups[r.tier].push(r)
  }

  const tiers = ["TYPE_A", "TYPE_B", "TYPE_C", "QUIET"].filter(
    (t) => tierGroups[t]?.length
  )

  if (tiers.length === 0) {
    return (
      <div className="py-8 text-center text-zinc-500 text-sm">
        Run a backtest to see signal performance by tier
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-zinc-800">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-zinc-800">
            <th className="px-3 py-2 text-left text-zinc-500 font-medium">Tier</th>
            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Count</th>
            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Win Rate</th>
            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Avg P&L 1b</th>
            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Avg P&L 3b</th>
            <th className="px-3 py-2 text-right text-zinc-500 font-medium">Avg P&L 5b</th>
          </tr>
        </thead>
        <tbody>
          {tiers.map((tier) => {
            const group = tierGroups[tier]!
            const count = group.length
            const wins = group.filter((r) => r.pnl_3bar > 0).length
            const winRate = ((wins / count) * 100).toFixed(1)
            const avg1 = (group.reduce((s, r) => s + r.pnl_1bar, 0) / count).toFixed(2)
            const avg3 = (group.reduce((s, r) => s + r.pnl_3bar, 0) / count).toFixed(2)
            const avg5 = (group.reduce((s, r) => s + r.pnl_5bar, 0) / count).toFixed(2)
            const avg3Val = parseFloat(avg3)
            return (
              <tr key={tier} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                <td className="px-3 py-2 font-medium text-zinc-200">{tier}</td>
                <td className="px-3 py-2 text-right text-zinc-300 font-mono">{count}</td>
                <td className="px-3 py-2 text-right text-zinc-300 font-mono">{winRate}%</td>
                <td className="px-3 py-2 text-right font-mono text-zinc-400">{avg1}</td>
                <td className={`px-3 py-2 text-right font-mono ${avg3Val >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {avg3Val >= 0 ? "+" : ""}{avg3}
                </td>
                <td className="px-3 py-2 text-right font-mono text-zinc-400">{avg5}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function BacktestTab({ isActive = false }: Props) {
  const status = useBacktestStore((s) => s.status)
  const rows = useBacktestStore((s) => s.rows) as unknown as BacktestRow[]
  const summary = useBacktestStore((s) => s.summary)

  // Ref so BacktestConfig can expose its run trigger upward (for 'R' shortcut in page.tsx)
  const runRef = useRef<(() => void) | null>(null)

  return (
    <div className="flex h-full min-h-0 gap-0">
      {/* Left config column */}
      <div className="w-72 shrink-0 p-4 border-r border-zinc-800 overflow-y-auto">
        <BacktestConfig
          isActive={isActive}
          onRunRef={(fn) => { runRef.current = fn }}
        />

        {/* Summary card when complete */}
        {status === "complete" && summary && (
          <Card className="mt-4 bg-zinc-900 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs text-zinc-400 uppercase tracking-wider">
                Job Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1.5">
              {Object.entries(summary).map(([k, v]) => (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-zinc-500">{k}</span>
                  <span className="text-zinc-200 font-mono">{String(v)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
      </div>

      {/* Main area with subtabs */}
      <div className="flex-1 min-w-0 flex flex-col p-4">
        <Tabs defaultValue="results" className="flex-1 flex flex-col">
          <TabsList className="w-fit bg-zinc-800 mb-4">
            <TabsTrigger value="results" className="text-xs px-4">
              Results
            </TabsTrigger>
            <TabsTrigger value="sweep" className="text-xs px-4">
              Sweep
            </TabsTrigger>
            <TabsTrigger value="signals" className="text-xs px-4">
              Signals
            </TabsTrigger>
          </TabsList>

          {/* Results: equity curve + trade table */}
          <TabsContent value="results" className="flex-1 flex flex-col gap-4 overflow-auto">
            {rows.length === 0 && status !== "running" ? (
              <div className="flex h-48 items-center justify-center text-zinc-500 text-sm">
                {status === "idle"
                  ? "Configure and run a backtest to see results"
                  : "No results yet"}
              </div>
            ) : (
              <>
                <EquityCurve rows={rows} />
                <div className="border-t border-zinc-800 pt-4">
                  <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
                    Trade Log
                  </p>
                  <TradeTable rows={rows} />
                </div>
              </>
            )}
          </TabsContent>

          {/* Sweep: Optuna sweep panel */}
          <TabsContent value="sweep" className="flex-1 overflow-auto">
            <div className="mb-4 rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-3">
              <p className="text-xs text-zinc-500">
                <span className="text-zinc-300 font-medium">Parameter Evolution</span> — run
                an Optuna sweep to discover optimal signal thresholds. Best parameters are
                displayed below and available for comparison after each sweep.
              </p>
            </div>
            <OptunaSweepPanel />
          </TabsContent>

          {/* Signals: win rate per tier */}
          <TabsContent value="signals" className="flex-1 overflow-auto">
            <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3">
              Signal Performance by Tier
            </p>
            <SignalStats rows={rows} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

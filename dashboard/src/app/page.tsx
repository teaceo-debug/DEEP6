"use client"

/**
 * DEEP6 Dashboard — two-tab shell (LIVE | BACKTEST).
 *
 * Per D-06: Two primary tabs at top.
 * Per D-09: Top bar with connection status, regime badge, daily P&L.
 * Keyboard shortcuts: L → live tab, B → backtest tab.
 */

import { useEffect, useState } from "react"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { useLiveStore } from "@/store/live"
import LiveTab from "@/components/LiveTab"
import BacktestTab from "@/components/BacktestTab"
import type { WsStatus } from "@/lib/ws"

type TabValue = "live" | "backtest"

function StatusDot({ status }: { status: WsStatus }) {
  const colorMap: Record<WsStatus, string> = {
    live: "bg-emerald-400",
    connecting: "bg-yellow-400 animate-pulse",
    stale: "bg-yellow-400",
    disconnected: "bg-red-500",
  }
  return (
    <span
      className={`inline-block w-2.5 h-2.5 rounded-full ${colorMap[status]}`}
      title={status}
    />
  )
}

function RegimeBadge({ regime }: { regime: string }) {
  const variantMap: Record<string, string> = {
    POSITIVE: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
    NEGATIVE: "bg-red-500/20 text-red-300 border-red-500/30",
    NEUTRAL: "bg-zinc-600/40 text-zinc-300 border-zinc-600/30",
  }
  const cls = variantMap[regime] ?? variantMap["NEUTRAL"]
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-medium border ${cls}`}
    >
      {regime} GEX
    </span>
  )
}

export default function DashboardPage() {
  const [tab, setTab] = useState<TabValue>("live")
  const status = useLiveStore((s) => s.status)
  const regime = useLiveStore((s) => s.regime)
  const dailyPnl = useLiveStore((s) => s.dailyPnl)

  // Keyboard shortcuts: L → live, B → backtest
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Skip if focus is in an input/textarea
      const tag = (e.target as HTMLElement).tagName
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return
      if (e.key === "l" || e.key === "L") setTab("live")
      if (e.key === "b" || e.key === "B") setTab("backtest")
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  const pnlColor = dailyPnl >= 0 ? "text-emerald-400" : "text-red-400"
  const pnlSign = dailyPnl >= 0 ? "+" : ""

  return (
    <div className="flex flex-col min-h-screen bg-zinc-950">
      {/* Top bar — always visible */}
      <header className="flex items-center gap-4 px-4 py-2 border-b border-zinc-800 bg-zinc-900">
        <span className="text-amber-400 font-bold tracking-widest text-sm">
          DEEP6
        </span>
        <div className="flex items-center gap-1.5">
          <StatusDot status={status} />
          <span className="text-xs text-zinc-400 capitalize">{status}</span>
        </div>
        <RegimeBadge regime={regime} />
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">P&amp;L</span>
          <span className={`text-xs font-mono font-semibold ${pnlColor}`}>
            {pnlSign}{dailyPnl.toFixed(2)}
          </span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">CB</span>
          <Badge className="h-4 text-[10px] bg-emerald-500/20 text-emerald-300 border-emerald-500/30 border">
            ACTIVE
          </Badge>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-zinc-500">VPIN</span>
          <span className="text-xs text-zinc-400">N/A</span>
        </div>
        <div className="ml-auto text-[10px] text-zinc-600">
          [L] Live&nbsp;&nbsp;[B] Backtest
        </div>
      </header>

      {/* Main content with tabs */}
      <main className="flex-1 flex flex-col">
        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as TabValue)}
          className="flex-1 flex flex-col"
        >
          <TabsList
            className="mx-4 mt-3 w-fit bg-zinc-800"
            variant="default"
          >
            <TabsTrigger value="live" className="text-sm px-6">
              LIVE
            </TabsTrigger>
            <TabsTrigger value="backtest" className="text-sm px-6">
              BACKTEST
            </TabsTrigger>
          </TabsList>
          <TabsContent value="live" className="flex-1 mt-0">
            <LiveTab />
          </TabsContent>
          <TabsContent value="backtest" className="flex-1 mt-0">
            <BacktestTab />
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}

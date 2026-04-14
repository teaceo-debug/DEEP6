"use client"

/**
 * TradeTable — filterable + sortable backtest trade results table.
 *
 * Per D-15: Full trade table with filters (tier, narrative, P&L range).
 * Tier badges: TYPE_A → amber, TYPE_B → orange, TYPE_C → zinc, QUIET → slate.
 * P&L coloring: positive → emerald, negative → red.
 * Per D-03: Direction shown as text (LONG/SHORT), NOT colored green/red.
 * Paginated at 50 rows.
 */

import { useState, useMemo } from "react"
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from "@/components/ui/table"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import type { BacktestRow } from "./EquityCurve"

type TierFilter = "ALL" | "TYPE_A" | "TYPE_B" | "TYPE_C"
type SortKey = "pnl_3bar" | "score" | "bar_index"
type SortDir = "asc" | "desc"

const PAGE_SIZE = 50

const TIER_BADGE_CLASS: Record<string, string> = {
  TYPE_A: "bg-amber-900/60 text-amber-300 border border-amber-700/40",
  TYPE_B: "bg-orange-900/60 text-orange-300 border border-orange-700/40",
  TYPE_C: "bg-zinc-800 text-zinc-300 border border-zinc-700",
  QUIET: "bg-slate-800 text-slate-400 border border-slate-700",
}

function formatTime(ts?: number): string {
  if (!ts) return "--"
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })
}

function pnlClass(val: number): string {
  if (val > 0) return "text-emerald-400 font-mono"
  if (val < 0) return "text-red-400 font-mono"
  return "text-zinc-500 font-mono"
}

interface Props {
  rows: BacktestRow[]
}

export default function TradeTable({ rows }: Props) {
  const [tierFilter, setTierFilter] = useState<TierFilter>("ALL")
  const [sortBy, setSortBy] = useState<SortKey>("bar_index")
  const [sortDir, setSortDir] = useState<SortDir>("asc")
  const [page, setPage] = useState(0)

  const filtered = useMemo(() => {
    let data = tierFilter === "ALL" ? rows : rows.filter((r) => r.tier === tierFilter)
    data = [...data].sort((a, b) => {
      const av = a[sortBy] as number
      const bv = b[sortBy] as number
      return sortDir === "asc" ? av - bv : bv - av
    })
    return data
  }, [rows, tierFilter, sortBy, sortDir])

  const totalTrades = filtered.length
  const wins = filtered.filter((r) => r.pnl_3bar > 0).length
  const winRate = totalTrades > 0 ? ((wins / totalTrades) * 100).toFixed(1) : "0.0"
  const totalPnl = filtered.reduce((s, r) => s + r.pnl_3bar, 0)
  const avgScore =
    totalTrades > 0
      ? (filtered.reduce((s, r) => s + r.score, 0) / totalTrades).toFixed(2)
      : "0"

  const pageStart = page * PAGE_SIZE
  const pageEnd = pageStart + PAGE_SIZE
  const pageRows = filtered.slice(pageStart, pageEnd)
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE)

  const toggleSort = (key: SortKey) => {
    if (sortBy === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortBy(key)
      setSortDir("desc")
    }
    setPage(0)
  }

  return (
    <div className="flex flex-col gap-3">
      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Tier:</span>
          <Select
            value={tierFilter}
            onValueChange={(v) => { setTierFilter(v as TierFilter); setPage(0) }}
          >
            <SelectTrigger className="h-7 text-xs border-zinc-700 bg-zinc-800 text-zinc-200 w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">ALL</SelectItem>
              <SelectItem value="TYPE_A">TYPE_A</SelectItem>
              <SelectItem value="TYPE_B">TYPE_B</SelectItem>
              <SelectItem value="TYPE_C">TYPE_C</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Sort:</span>
          <Select
            value={sortBy}
            onValueChange={(v) => { setSortBy(v as SortKey); setPage(0) }}
          >
            <SelectTrigger className="h-7 text-xs border-zinc-700 bg-zinc-800 text-zinc-200 w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="bar_index">Bar #</SelectItem>
              <SelectItem value="pnl_3bar">P&L 3bar</SelectItem>
              <SelectItem value="score">Score</SelectItem>
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="xs"
            className="text-zinc-500 hover:text-zinc-200 px-2"
            onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
          >
            {sortDir === "asc" ? "↑" : "↓"}
          </Button>
        </div>
      </div>

      {/* Summary row */}
      <div className="text-xs text-zinc-500 bg-zinc-900/50 rounded px-3 py-2 border border-zinc-800">
        <span className="text-zinc-300 font-medium">{totalTrades}</span> trades&nbsp;&nbsp;|&nbsp;&nbsp;
        Win rate: <span className="text-zinc-300 font-medium">{winRate}%</span>&nbsp;&nbsp;|&nbsp;&nbsp;
        Total P&L:{" "}
        <span className={totalPnl >= 0 ? "text-emerald-400 font-medium" : "text-red-400 font-medium"}>
          {totalPnl >= 0 ? "+" : ""}{totalPnl.toFixed(2)} pts
        </span>&nbsp;&nbsp;|&nbsp;&nbsp;
        Avg score: <span className="text-zinc-300 font-medium">{avgScore}</span>
      </div>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="py-8 text-center text-zinc-500 text-sm">No trades match filter</div>
      ) : (
        <>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <Table>
              <TableHeader>
                <TableRow className="border-zinc-800 hover:bg-transparent">
                  <TableHead
                    className="text-zinc-500 cursor-pointer hover:text-zinc-300 text-xs"
                    onClick={() => toggleSort("bar_index")}
                  >
                    Bar # {sortBy === "bar_index" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                  </TableHead>
                  <TableHead className="text-zinc-500 text-xs">Time</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Tier</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Narrative</TableHead>
                  <TableHead
                    className="text-zinc-500 cursor-pointer hover:text-zinc-300 text-xs"
                    onClick={() => toggleSort("score")}
                  >
                    Score {sortBy === "score" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                  </TableHead>
                  <TableHead className="text-zinc-500 text-xs">Dir</TableHead>
                  <TableHead className="text-zinc-500 text-xs">P&L 1b</TableHead>
                  <TableHead
                    className="text-zinc-500 cursor-pointer hover:text-zinc-300 text-xs"
                    onClick={() => toggleSort("pnl_3bar")}
                  >
                    P&L 3b {sortBy === "pnl_3bar" ? (sortDir === "asc" ? "↑" : "↓") : ""}
                  </TableHead>
                  <TableHead className="text-zinc-500 text-xs">P&L 5b</TableHead>
                  <TableHead className="text-zinc-500 text-xs">Cats</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageRows.map((row, i) => (
                  <TableRow
                    key={`${row.bar_index}-${i}`}
                    className="border-zinc-800/50 hover:bg-zinc-800/30"
                  >
                    <TableCell className="text-zinc-400 text-xs">{row.bar_index}</TableCell>
                    <TableCell className="text-zinc-400 text-xs">{formatTime(row.timestamp)}</TableCell>
                    <TableCell>
                      <span
                        className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${TIER_BADGE_CLASS[row.tier] ?? TIER_BADGE_CLASS["QUIET"]}`}
                      >
                        {row.tier}
                      </span>
                    </TableCell>
                    <TableCell className="text-zinc-400 text-xs max-w-[120px] truncate" title={row.narrative}>
                      {row.narrative}
                    </TableCell>
                    <TableCell className="text-zinc-300 text-xs font-mono">{row.score.toFixed(1)}</TableCell>
                    <TableCell className="text-zinc-300 text-xs">
                      {row.direction > 0 ? "▲ LONG" : "▼ SHORT"}
                    </TableCell>
                    <TableCell className={`text-xs ${pnlClass(row.pnl_1bar)}`}>
                      {row.pnl_1bar >= 0 ? "+" : ""}{row.pnl_1bar.toFixed(2)}
                    </TableCell>
                    <TableCell className={`text-xs ${pnlClass(row.pnl_3bar)}`}>
                      {row.pnl_3bar >= 0 ? "+" : ""}{row.pnl_3bar.toFixed(2)}
                    </TableCell>
                    <TableCell className={`text-xs ${pnlClass(row.pnl_5bar)}`}>
                      {row.pnl_5bar >= 0 ? "+" : ""}{row.pnl_5bar.toFixed(2)}
                    </TableCell>
                    <TableCell className="text-zinc-500 text-xs">{row.categories}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center gap-2 text-xs text-zinc-500">
              <Button
                variant="outline"
                size="xs"
                className="border-zinc-700 text-zinc-400 hover:text-zinc-200"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                Prev 50
              </Button>
              <span>
                {pageStart + 1}–{Math.min(pageEnd, filtered.length)} of {filtered.length}
              </span>
              <Button
                variant="outline"
                size="xs"
                className="border-zinc-700 text-zinc-400 hover:text-zinc-200"
                disabled={pageEnd >= filtered.length}
                onClick={() => setPage((p) => p + 1)}
              >
                Next 50
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

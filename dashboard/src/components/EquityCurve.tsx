"use client"

/**
 * EquityCurve — equity curve chart + tier distribution donut.
 *
 * Per D-14: Main area: Equity curve + tier distribution pie chart.
 * Uses Recharts AreaChart (cumulative pnl_3bar) + PieChart (tier distribution).
 * Filters out QUIET bars for equity curve (only scored signals).
 */

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from "recharts"
import { PieChart, Pie, Cell, Legend, Tooltip as PieTooltip } from "recharts"

export interface BacktestRow {
  bar_index: number
  timestamp?: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  delta: number
  cvd: number
  poc: number
  narrative: string
  narrative_label?: string
  score: number
  tier: string
  direction: number
  categories: number
  categories_list: string
  pnl_1bar: number
  pnl_3bar: number
  pnl_5bar: number
  confluence_mult?: number
  zone_bonus?: number
}

interface Props {
  rows: BacktestRow[]
}

const TIER_COLORS: Record<string, string> = {
  TYPE_A: "#f59e0b",  // amber
  TYPE_B: "#f97316",  // orange
  TYPE_C: "#71717a",  // zinc
  QUIET: "#475569",   // slate
}

function formatTimestamp(ts?: number): string {
  if (!ts) return ""
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false })
}

export default function EquityCurve({ rows }: Props) {
  // Build equity curve from non-QUIET bars only
  const scored = rows.filter((r) => r.tier !== "QUIET")
  let cumulative = 0
  const equityData = scored.map((r) => {
    cumulative += r.pnl_3bar
    return {
      bar: r.bar_index,
      label: r.timestamp ? formatTimestamp(r.timestamp) : String(r.bar_index),
      equity: Math.round(cumulative * 100) / 100,
    }
  })

  // Tier distribution
  const tierCounts: Record<string, number> = {}
  for (const r of rows) {
    tierCounts[r.tier] = (tierCounts[r.tier] ?? 0) + 1
  }
  const pieData = Object.entries(tierCounts).map(([name, value]) => ({ name, value }))

  if (rows.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-zinc-500 text-sm">
        Run a backtest to see results
      </div>
    )
  }

  const lastEquity = equityData.length > 0 ? equityData[equityData.length - 1].equity : 0
  const areaColor = lastEquity >= 0 ? "#10b981" : "#ef4444"
  const areaFill = lastEquity >= 0 ? "#10b98120" : "#ef444420"

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      {/* Equity Curve */}
      <div className="flex-1 min-w-0">
        <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
          Equity Curve (3-bar exit)
        </p>
        {equityData.length === 0 ? (
          <div className="flex h-40 items-center justify-center text-zinc-500 text-xs">
            No scored signals in this backtest
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={equityData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={areaColor} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={areaColor} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "#71717a" }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10, fill: "#71717a" }}
                tickLine={false}
                axisLine={false}
                width={48}
                tickFormatter={(v) => v.toFixed(1)}
              />
              <ReferenceLine y={0} stroke="#52525b" strokeDasharray="3 3" />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#18181b",
                  border: "1px solid #3f3f46",
                  borderRadius: "6px",
                  fontSize: "11px",
                  color: "#d4d4d8",
                }}
                formatter={(value) => [`${(value as number).toFixed(2)} pts`, "P&L"]}
                labelStyle={{ color: "#71717a" }}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke={areaColor}
                strokeWidth={1.5}
                fill="url(#equityGradient)"
                dot={false}
                activeDot={{ r: 3, stroke: areaColor, fill: areaColor }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Tier Distribution */}
      <div className="w-full lg:w-48 shrink-0">
        <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
          Signal Distribution
        </p>
        <ResponsiveContainer width="100%" height={200}>
          <PieChart>
            <Pie
              data={pieData}
              cx="50%"
              cy="45%"
              innerRadius={40}
              outerRadius={65}
              dataKey="value"
              paddingAngle={2}
              strokeWidth={0}
            >
              {pieData.map((entry) => (
                <Cell
                  key={entry.name}
                  fill={TIER_COLORS[entry.name] ?? "#52525b"}
                />
              ))}
            </Pie>
            <PieTooltip
              contentStyle={{
                backgroundColor: "#18181b",
                border: "1px solid #3f3f46",
                borderRadius: "6px",
                fontSize: "11px",
                color: "#d4d4d8",
              }}
              formatter={(value, name) => {
                const v = value as number
                const total = rows.length
                const pct = total > 0 ? ((v / total) * 100).toFixed(1) : "0"
                return [`${v} (${pct}%)`, name as string]
              }}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: "10px", color: "#71717a" }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

"use client"

/**
 * ParamImportanceChart — bar chart showing % deviation of Optuna best_params
 * from hardcoded default thresholds.
 *
 * Per D-16 / DASH-04: Parameter evolution view.
 * Deviation = |optimized - default| / default * 100 (% change).
 * Only shows params present in bestParams dict.
 * Color: deviation > 30% → amber, else zinc.
 */

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  CartesianGrid,
} from "recharts"

const DEFAULT_THRESHOLDS: Record<string, number> = {
  absorption_ratio: 0.3,
  exhaustion_vol_mult: 2.0,
  imbalance_ratio: 3.0,
  stacked_min_levels: 3,
  delta_divergence_pct: 0.05,
  cvd_window: 10,
  zone_min_score: 20,
  confluence_min_categories: 5,
}

interface Props {
  bestParams: Record<string, number> | null
}

export default function ParamImportanceChart({ bestParams }: Props) {
  if (!bestParams) {
    return (
      <div className="flex h-32 items-center justify-center text-zinc-500 text-xs">
        Run Optuna sweep to see parameter importance
      </div>
    )
  }

  // Build deviation data for params that exist in both bestParams and defaults
  const data = Object.entries(DEFAULT_THRESHOLDS)
    .filter(([key]) => key in bestParams)
    .map(([key, defaultVal]) => {
      const optimized = bestParams[key]!
      const deviation = Math.abs((optimized - defaultVal) / defaultVal) * 100
      return {
        name: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        key,
        deviation: Math.round(deviation * 10) / 10,
        optimized,
        default: defaultVal,
      }
    })
    .sort((a, b) => b.deviation - a.deviation)

  // Also include any bestParams keys not in default thresholds (show with a placeholder default)
  for (const [key, value] of Object.entries(bestParams)) {
    if (!(key in DEFAULT_THRESHOLDS)) {
      data.push({
        name: key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
        key,
        deviation: 0, // unknown default — show 0 deviation
        optimized: value,
        default: 0,
      })
    }
  }

  if (data.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-zinc-500 text-xs">
        No known parameters in sweep result
      </div>
    )
  }

  return (
    <div>
      <p className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">
        Parameter Deviation from Defaults (%)
      </p>
      <ResponsiveContainer width="100%" height={Math.max(120, data.length * 28)}>
        <BarChart
          layout="vertical"
          data={data}
          margin={{ top: 0, right: 40, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
          <XAxis
            type="number"
            tick={{ fontSize: 10, fill: "#71717a" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="name"
            tick={{ fontSize: 10, fill: "#a1a1aa" }}
            tickLine={false}
            axisLine={false}
            width={160}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "#18181b",
              border: "1px solid #3f3f46",
              borderRadius: "6px",
              fontSize: "11px",
              color: "#d4d4d8",
            }}
            formatter={(value) => [`${Number(value).toFixed(1)}%`, "Deviation"]}
            labelStyle={{ color: "#71717a" }}
          />
          <Bar dataKey="deviation" radius={[0, 3, 3, 0]} maxBarSize={18}>
            {data.map((entry) => (
              <Cell
                key={entry.key}
                fill={entry.deviation > 30 ? "#f59e0b" : "#52525b"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

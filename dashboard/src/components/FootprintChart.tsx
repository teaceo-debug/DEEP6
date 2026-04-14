/**
 * FootprintChart — Lightweight Charts v5.1 custom series footprint renderer.
 *
 * Mounts into the footprint-chart-mount div created by Plan 03 (LiveTab).
 * Uses dynamic import (ssr: false) because LW Charts requires browser APIs
 * (ResizeObserver, canvas). This component itself is the dynamically imported module.
 *
 * Per D-25: custom series renders bid/ask cells per price level.
 * Per D-26: zone overlays (LVN gray, HVN blue, absorption red, exhaustion orange, GEX dashed).
 * T-10-10: ResizeObserver cleaned up in useEffect return to prevent memory leaks.
 */

"use client"

import { useEffect, useRef } from "react"
import { createChart, IChartApi, UTCTimestamp } from "lightweight-charts"
import { FootprintSeriesPlugin, FootprintData } from "@/lib/footprint-series"
import { addZoneOverlays } from "@/lib/chart-overlays"

export default function FootprintChart() {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    // Create chart with institutional dark theme (D-01 dark theme)
    const chart = createChart(containerRef.current, {
      width: containerRef.current.offsetWidth,
      height: containerRef.current.offsetHeight || 500,
      layout: {
        background: { color: "#09090b" },
        textColor: "#a1a1aa",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#27272a" },
        horzLines: { color: "#27272a" },
      },
      crosshair: { mode: 1 },
      rightPriceScale: {
        borderColor: "#3f3f46",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: "#3f3f46",
        timeVisible: true,
        secondsVisible: false,
      },
    })
    chartRef.current = chart

    // Add custom footprint series
    const footprintSeries = chart.addCustomSeries(
      new FootprintSeriesPlugin(),
      {
        cellHeight: 10,
        bidColor: "#2563eb",
        askColor: "#dc2626",
        pocColor: "#f59e0b",
        maxVolumeWidth: 0.45,
        showVolume: true,
        fontSize: 9,
      }
    )

    // Seed with 5 synthetic demo bars (visible on load)
    const seedBars = generateDemoBars(5)
    footprintSeries.setData(seedBars)

    // Add demo GEX overlays (real data injected from signal events in Phase 11)
    const removeOverlays = addZoneOverlays(chart, {
      gexLevels: {
        gammaFlip: 17000,
        callWall: 17200,
        putWall: 16800,
      },
      lvnBands: [{ high: 17050, low: 17040, label: "LVN1" }],
      hvnBands: [{ high: 16950, low: 16930, label: "HVN1" }],
    })

    // T-10-10: ResizeObserver cleanup prevents memory leak on unmount
    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({
          width: containerRef.current.offsetWidth,
          height: containerRef.current.offsetHeight || 500,
        })
      }
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      removeOverlays()
      chart.remove()
    }
  }, [])

  // TODO (Phase 11): subscribe to useLiveStore footprint bar events and call
  // footprintSeries.update(bar) on each bar close — real Rithmic feed data.

  return (
    <div
      ref={containerRef}
      id="footprint-chart-mount"
      className="w-full h-full min-h-[500px]"
    />
  )
}

// ─── Demo data generator ──────────────────────────────────────────────────────

/**
 * Generates realistic-looking NQ footprint bars for demo display on load.
 * Base price ~17000, each bar ±20pt range, 10 price levels in 5pt increments.
 */
function generateDemoBars(count: number): FootprintData[] {
  const now = Math.floor(Date.now() / 1000)
  const bars: FootprintData[] = []
  let basePrice = 17000

  const tiers: Array<"TYPE_A" | "TYPE_B" | "TYPE_C" | "QUIET"> = [
    "TYPE_A",
    "TYPE_B",
    "TYPE_C",
    "QUIET",
    "TYPE_B",
  ]

  for (let i = 0; i < count; i++) {
    const open = basePrice + (Math.random() - 0.5) * 10
    const close = open + (Math.random() - 0.5) * 20
    const high = Math.max(open, close) + Math.random() * 10
    const low = Math.min(open, close) - Math.random() * 10

    // 10 price levels in 5pt increments spanning the bar range
    const levelBase = Math.floor(low / 5) * 5
    let maxVol = 0
    let pocPrice = levelBase

    const levels = Array.from({ length: 10 }, (_, j) => {
      const price = levelBase + j * 5
      const bid = Math.floor(Math.random() * 1900 + 100)
      const ask = Math.floor(Math.random() * 1900 + 100)
      if (bid + ask > maxVol) {
        maxVol = bid + ask
        pocPrice = price
      }
      return { price, bid, ask }
    })

    const delta = levels.reduce((s, l) => s + l.ask - l.bid, 0)
    const cvd = delta + (i > 0 ? bars[i - 1].cvd : 0)

    bars.push({
      time: (now - (count - 1 - i) * 60) as UTCTimestamp,
      open,
      high,
      low,
      close,
      levels,
      poc: pocPrice,
      delta,
      cvd,
      tier: tiers[i % tiers.length],
    })

    basePrice = close
  }

  return bars
}

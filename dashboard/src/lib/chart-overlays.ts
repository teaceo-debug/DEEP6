/**
 * Helpers to add LVN/HVN/GEX/absorption/exhaustion overlays to IChartApi.
 *
 * Per D-26: absorption zones (red), exhaustion zones (orange),
 * LVN (gray bands), HVN (blue bands), GEX levels (dashed lines).
 *
 * Strategy: use price lines on a single invisible baseline series.
 * For bands (LVN/HVN/absorption/exhaustion): two price lines per band (high/low)
 * with fill color implied by label color.
 * For GEX point levels: single dashed price line per level.
 */

import {
  IChartApi,
  ISeriesApi,
  LineSeries,
  LineStyle,
} from "lightweight-charts"

export interface ZoneBand {
  high: number
  low: number
  label?: string
}

export interface ZoneLevel {
  price: number
  label?: string
}

export interface ZoneOverlayOptions {
  /** Gray translucent horizontal bands — low volume nodes */
  lvnBands?: ZoneBand[]
  /** Blue translucent horizontal bands — high volume nodes */
  hvnBands?: ZoneBand[]
  /** Red semi-transparent bands — absorption signal zones */
  absorptionZones?: ZoneBand[]
  /** Orange semi-transparent bands — exhaustion signal zones */
  exhaustionZones?: ZoneBand[]
  /** GEX point levels as dashed lines */
  gexLevels?: {
    callWall?: number
    putWall?: number
    gammaFlip?: number
    hvl?: number
  }
}

/**
 * Adds zone overlays to the chart using price lines on invisible line series.
 * Returns cleanup function — call on chart removal to remove all series.
 *
 * Uses the "anchor series + createPriceLine" pattern:
 * Each overlay category gets one invisible anchor series; price lines are
 * attached to it for each band edge or point level.
 */
export function addZoneOverlays(
  chart: IChartApi,
  options: ZoneOverlayOptions
): () => void {
  const seriesRefs: Array<ISeriesApi<"Line">> = []

  // Helper: create an invisible anchor series + attach price lines
  function makeAnchorSeries(color: string): ISeriesApi<"Line"> {
    const s = chart.addSeries(LineSeries, {
      color: "transparent",
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    })
    // Anchor at a distant time so it doesn't interfere with chart scale
    // Using empty data — series is invisible but can host price lines
    void color
    seriesRefs.push(s)
    return s
  }

  // ── LVN bands (gray #52525b at ~20% opacity) ─────────────────────────────
  if (options.lvnBands?.length) {
    const s = makeAnchorSeries("#52525b")
    for (const band of options.lvnBands) {
      s.createPriceLine({
        price: band.high,
        color: "rgba(82,82,91,0.20)",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `LVN ${band.label} H` : "LVN H",
      })
      s.createPriceLine({
        price: band.low,
        color: "rgba(82,82,91,0.20)",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `LVN ${band.label} L` : "LVN L",
      })
    }
  }

  // ── HVN bands (blue #1d4ed8 at ~20% opacity) ─────────────────────────────
  if (options.hvnBands?.length) {
    const s = makeAnchorSeries("#1d4ed8")
    for (const band of options.hvnBands) {
      s.createPriceLine({
        price: band.high,
        color: "rgba(29,78,216,0.20)",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `HVN ${band.label} H` : "HVN H",
      })
      s.createPriceLine({
        price: band.low,
        color: "rgba(29,78,216,0.20)",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `HVN ${band.label} L` : "HVN L",
      })
    }
  }

  // ── Absorption zones (red #7f1d1d at ~30% opacity) ───────────────────────
  if (options.absorptionZones?.length) {
    const s = makeAnchorSeries("#7f1d1d")
    for (const band of options.absorptionZones) {
      s.createPriceLine({
        price: band.high,
        color: "rgba(127,29,29,0.30)",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `ABS ${band.label} H` : "ABS H",
      })
      s.createPriceLine({
        price: band.low,
        color: "rgba(127,29,29,0.30)",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `ABS ${band.label} L` : "ABS L",
      })
    }
  }

  // ── Exhaustion zones (orange #7c2d12 at ~30% opacity) ────────────────────
  if (options.exhaustionZones?.length) {
    const s = makeAnchorSeries("#7c2d12")
    for (const band of options.exhaustionZones) {
      s.createPriceLine({
        price: band.high,
        color: "rgba(124,45,18,0.30)",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `EXH ${band.label} H` : "EXH H",
      })
      s.createPriceLine({
        price: band.low,
        color: "rgba(124,45,18,0.30)",
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: false,
        title: band.label ? `EXH ${band.label} L` : "EXH L",
      })
    }
  }

  // ── GEX point levels (dashed lines) ──────────────────────────────────────
  if (options.gexLevels) {
    const gex = options.gexLevels
    const s = makeAnchorSeries("#a1a1aa")

    if (gex.callWall !== undefined) {
      s.createPriceLine({
        price: gex.callWall,
        color: "#22c55e", // green
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Call Wall",
      })
    }
    if (gex.putWall !== undefined) {
      s.createPriceLine({
        price: gex.putWall,
        color: "#ef4444", // red
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Put Wall",
      })
    }
    if (gex.gammaFlip !== undefined) {
      s.createPriceLine({
        price: gex.gammaFlip,
        color: "#f59e0b", // amber
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Gamma Flip",
      })
    }
    if (gex.hvl !== undefined) {
      s.createPriceLine({
        price: gex.hvl,
        color: "#a855f7", // purple
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "HVL",
      })
    }
  }

  // Return cleanup: remove all anchor series from chart
  return () => {
    for (const s of seriesRefs) {
      try {
        chart.removeSeries(s)
      } catch {
        // Series may already be removed if chart was destroyed
      }
    }
  }
}

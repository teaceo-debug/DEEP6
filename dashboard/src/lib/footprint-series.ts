/**
 * Lightweight Charts v5.1 custom series plugin for footprint chart rendering.
 *
 * Implements ICustomSeriesPaneView<UTCTimestamp, FootprintData, FootprintOptions>
 * to render bid/ask volume as colored cells at each price level per bar.
 *
 * Per D-25: custom LW Charts series plugin renders bid/ask volume cells.
 * Bid cells: left half of bar column in blue (#2563eb).
 * Ask cells: right half of bar column in red (#dc2626).
 * POC level: amber outline (#f59e0b).
 * TYPE_A bars: amber glow border.
 */

import {
  ICustomSeriesPaneView,
  ICustomSeriesPaneRenderer,
  PriceToCoordinateConverter,
  CustomSeriesPricePlotValues,
  UTCTimestamp,
  PaneRendererCustomData,
  customSeriesDefaultOptions,
  CustomSeriesOptions,
} from "lightweight-charts"
import type { CanvasRenderingTarget2D } from "fancy-canvas"
import type { BitmapCoordinatesRenderingScope } from "fancy-canvas"

export interface FootprintLevel {
  price: number
  bid: number
  ask: number
}

export interface FootprintData {
  time: UTCTimestamp
  open: number
  high: number
  low: number
  close: number
  levels: FootprintLevel[]
  poc: number
  delta: number
  cvd: number
  tier: "TYPE_A" | "TYPE_B" | "TYPE_C" | "QUIET"
}

/**
 * FootprintOptions extends CustomSeriesOptions so LW Charts accepts it.
 * CustomSeriesOptions = CustomStyleOptions & SeriesOptionsCommon,
 * where CustomStyleOptions requires `color: string`.
 */
export interface FootprintOptions extends CustomSeriesOptions {
  cellHeight: number
  bidColor: string
  askColor: string
  pocColor: string
  maxVolumeWidth: number
  showVolume: boolean
  fontSize: number
}

// ─── Renderer ─────────────────────────────────────────────────────────────────

class FootprintSeriesRenderer implements ICustomSeriesPaneRenderer {
  private _data: PaneRendererCustomData<UTCTimestamp, FootprintData> | null = null
  private _options: FootprintOptions | null = null

  update(
    data: PaneRendererCustomData<UTCTimestamp, FootprintData>,
    options: FootprintOptions
  ): void {
    this._data = data
    this._options = options
  }

  draw(
    target: CanvasRenderingTarget2D,
    priceConverter: PriceToCoordinateConverter
  ): void {
    if (!this._data || !this._options) return

    const { bars, barSpacing, visibleRange, conflationFactor } = this._data
    if (!visibleRange || bars.length === 0) return

    const opts = this._options
    const effectiveBarSpacing = conflationFactor * barSpacing

    target.useBitmapCoordinateSpace(
      (scope: BitmapCoordinatesRenderingScope) => {
        const ctx = scope.context
        const pixelRatio = scope.bitmapSize.width / scope.mediaSize.width

        for (let i = visibleRange.from; i <= visibleRange.to; i++) {
          const bar = bars[i]
          if (!bar) continue

          const barData = bar.originalData
          if (!barData.levels || barData.levels.length === 0) continue

          const xCenter = bar.x * pixelRatio
          const halfBarWidth = (effectiveBarSpacing / 2) * pixelRatio * 0.9

          // Max volume across all levels for proportional cell widths
          const maxVol = Math.max(
            ...barData.levels.map((l) => Math.max(l.bid + l.ask, 1))
          )
          const maxCellHalf = halfBarWidth * opts.maxVolumeWidth

          for (const level of barData.levels) {
            const yRaw = priceConverter(level.price)
            if (yRaw === null) continue
            const y = yRaw * pixelRatio

            const cellH = Math.max(opts.cellHeight * pixelRatio, 2)
            const halfCell = cellH / 2
            const isPoc = level.price === barData.poc

            // Bid cell (left half, blue)
            const bidWidth = (level.bid / maxVol) * maxCellHalf
            if (bidWidth > 0) {
              ctx.fillStyle = hexWithAlpha(opts.bidColor, isPoc ? 0.9 : 0.7)
              ctx.fillRect(xCenter - bidWidth, y - halfCell, bidWidth, cellH)
            }

            // Ask cell (right half, red)
            const askWidth = (level.ask / maxVol) * maxCellHalf
            if (askWidth > 0) {
              ctx.fillStyle = hexWithAlpha(opts.askColor, isPoc ? 0.9 : 0.7)
              ctx.fillRect(xCenter, y - halfCell, askWidth, cellH)
            }

            // POC amber outline
            if (isPoc) {
              ctx.strokeStyle = opts.pocColor
              ctx.lineWidth = 1.5 * pixelRatio
              ctx.strokeRect(
                xCenter - maxCellHalf,
                y - halfCell,
                maxCellHalf * 2,
                cellH
              )
            }

            // Volume text labels
            if (opts.showVolume) {
              const minWidth = 20 * pixelRatio
              if (bidWidth > minWidth && level.bid > 0) {
                ctx.fillStyle = "#ffffff"
                ctx.font = `${opts.fontSize * pixelRatio}px monospace`
                ctx.textAlign = "right"
                ctx.textBaseline = "middle"
                ctx.fillText(formatVol(level.bid), xCenter - 2 * pixelRatio, y)
              }
              if (askWidth > minWidth && level.ask > 0) {
                ctx.fillStyle = "#ffffff"
                ctx.font = `${opts.fontSize * pixelRatio}px monospace`
                ctx.textAlign = "left"
                ctx.textBaseline = "middle"
                ctx.fillText(formatVol(level.ask), xCenter + 2 * pixelRatio, y)
              }
            }
          }

          // OHLC candle wick + body
          const yOpen = priceConverter(barData.open)
          const yClose = priceConverter(barData.close)
          const yHigh = priceConverter(barData.high)
          const yLow = priceConverter(barData.low)

          if (yOpen !== null && yClose !== null) {
            const bullish = barData.close >= barData.open
            ctx.strokeStyle = bullish ? "#22c55e" : "#ef4444"
            ctx.lineWidth = pixelRatio

            // Wick
            if (yHigh !== null && yLow !== null) {
              ctx.beginPath()
              ctx.moveTo(xCenter, yHigh * pixelRatio)
              ctx.lineTo(xCenter, yLow * pixelRatio)
              ctx.stroke()
            }

            // Body
            const bodyTop = Math.min(yOpen, yClose) * pixelRatio
            const bodyHeight = Math.max(
              Math.abs(yClose - yOpen) * pixelRatio,
              pixelRatio
            )
            ctx.fillStyle = bullish ? "#22c55e" : "#ef4444"
            ctx.fillRect(
              xCenter - 1.5 * pixelRatio,
              bodyTop,
              3 * pixelRatio,
              bodyHeight
            )
          }

          // TYPE_A amber glow border
          if (barData.tier === "TYPE_A") {
            const yH = priceConverter(barData.high)
            const yL = priceConverter(barData.low)
            if (yH !== null && yL !== null) {
              ctx.strokeStyle = "rgba(245,158,11,0.6)"
              ctx.lineWidth = 2 * pixelRatio
              const top = yH * pixelRatio - 2 * pixelRatio
              const height = (yL - yH) * pixelRatio + 4 * pixelRatio
              ctx.strokeRect(
                xCenter - halfBarWidth,
                top,
                halfBarWidth * 2,
                height
              )
            }
          }
        }
      }
    )
  }
}

// ─── Plugin ───────────────────────────────────────────────────────────────────

export class FootprintSeriesPlugin
  implements ICustomSeriesPaneView<UTCTimestamp, FootprintData, FootprintOptions>
{
  private _renderer = new FootprintSeriesRenderer()

  priceValueBuilder(plotRow: FootprintData): CustomSeriesPricePlotValues {
    return [plotRow.low, plotRow.high, plotRow.close]
  }

  isWhitespace(
    data: FootprintData | { time: UTCTimestamp }
  ): data is { time: UTCTimestamp } {
    const fd = data as FootprintData
    return !fd.levels || fd.levels.length === 0
  }

  renderer(): ICustomSeriesPaneRenderer {
    return this._renderer
  }

  update(
    data: PaneRendererCustomData<UTCTimestamp, FootprintData>,
    seriesOptions: FootprintOptions
  ): void {
    this._renderer.update(data, seriesOptions)
  }

  defaultOptions(): FootprintOptions {
    return {
      ...customSeriesDefaultOptions,
      color: "#f59e0b",
      cellHeight: 10,
      bidColor: "#2563eb",
      askColor: "#dc2626",
      pocColor: "#f59e0b",
      maxVolumeWidth: 0.45,
      showVolume: true,
      fontSize: 9,
    }
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function hexWithAlpha(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function formatVol(v: number): string {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(v)
}

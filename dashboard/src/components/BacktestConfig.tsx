"use client"

/**
 * BacktestConfig — left column config form for the BACKTEST tab.
 *
 * Per D-13: Left column config form (date range, bar duration, run/stop controls).
 * Per T-10-12: date inputs use type="date" to enforce format; validated by FastAPI Pydantic.
 * Per T-10-14: LAUNCH disabled while status=running (409 prevention complement).
 */

import { useEffect, useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useBacktestStore } from "@/store/backtest"
import { Loader2, Play, Square, CheckCircle2, AlertCircle } from "lucide-react"

export interface BacktestConfigRef {
  triggerRun: () => void
}

interface Props {
  isActive: boolean
  onRunRef?: (fn: () => void) => void
}

export default function BacktestConfig({ isActive, onRunRef }: Props) {
  const [startDate, setStartDate] = useState("2026-04-07")
  const [endDate, setEndDate] = useState("2026-04-10")
  const [barSeconds, setBarSeconds] = useState<number>(60)

  const status = useBacktestStore((s) => s.status)
  const error = useBacktestStore((s) => s.error)
  const rows = useBacktestStore((s) => s.rows)
  const runJob = useBacktestStore((s) => s.runJob)
  const reset = useBacktestStore((s) => s.reset)

  const handleRun = () => {
    runJob({ start_date: startDate, end_date: endDate, bar_seconds: barSeconds })
  }

  // Expose run trigger to parent for keyboard shortcut 'R'
  const runRef = useRef(handleRun)
  runRef.current = handleRun
  useEffect(() => {
    if (onRunRef) onRunRef(() => runRef.current())
  }, [onRunRef])

  // Keyboard shortcut R → run (only when this tab is active)
  useEffect(() => {
    if (!isActive) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return
      if ((e.key === "r" || e.key === "R") && status !== "running") {
        handleRun()
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isActive, status, startDate, endDate, barSeconds])

  return (
    <Card className="w-full bg-zinc-900 border-zinc-800">
      <CardHeader className="border-b border-zinc-800 pb-3">
        <CardTitle className="text-xs font-semibold tracking-widest text-zinc-400 uppercase">
          Backtest Config
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pt-4">
        {/* Start Date */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-zinc-400">Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-8 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 text-sm text-zinc-100 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30"
            disabled={status === "running"}
          />
        </div>

        {/* End Date */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-zinc-400">End Date</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-8 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 text-sm text-zinc-100 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30"
            disabled={status === "running"}
          />
        </div>

        {/* Bar Duration */}
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-zinc-400">Bar Duration</label>
          <Select
            value={String(barSeconds)}
            onValueChange={(v) => setBarSeconds(Number(v))}
            disabled={status === "running"}
          >
            <SelectTrigger className="w-full border-zinc-700 bg-zinc-800 text-zinc-100">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="60">1 min (60s)</SelectItem>
              <SelectItem value="300">5 min (300s)</SelectItem>
              <SelectItem value="900">15 min (900s)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          <Button
            className="flex-1 bg-amber-600 text-white hover:bg-amber-500 disabled:opacity-50"
            disabled={status === "running"}
            onClick={handleRun}
          >
            {status === "running" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : (
              <Play className="size-3.5" />
            )}
            {status === "running" ? "Running..." : "RUN BACKTEST"}
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="border-zinc-700 text-zinc-400 hover:text-zinc-200"
            disabled={status !== "running"}
            onClick={reset}
            title="Stop / Reset"
          >
            <Square className="size-3.5" />
          </Button>
        </div>

        {/* Status display */}
        <div className="min-h-[40px]">
          {status === "idle" && (
            <p className="text-xs text-zinc-500">Configure and run a backtest</p>
          )}
          {status === "running" && (
            <div className="flex items-center gap-2">
              <Loader2 className="size-3.5 animate-spin text-amber-400" />
              <p className="text-xs text-amber-400">
                Running... (this may take 30-60s)
              </p>
            </div>
          )}
          {status === "error" && (
            <div className="flex items-start gap-2">
              <AlertCircle className="size-3.5 text-red-400 mt-0.5 shrink-0" />
              <p className="text-xs text-red-400 break-words">{error}</p>
            </div>
          )}
          {status === "complete" && (
            <div className="flex items-center gap-2">
              <CheckCircle2 className="size-3.5 text-emerald-400" />
              <p className="text-xs text-emerald-400">
                {rows.length} bars processed
              </p>
            </div>
          )}
        </div>

        {/* Keyboard hint */}
        {isActive && (
          <p className="text-[10px] text-zinc-600">[R] Run Backtest</p>
        )}
      </CardContent>
    </Card>
  )
}

"use client"

/**
 * OptunaSweepPanel — Optuna sweep trigger, status polling, and results display.
 *
 * Per D-16: Sweep trigger + status polling + best_params display + param importance.
 * Per T-10-13: clearInterval on status===complete/error; STOP POLLING button.
 * Per T-10-14: 409 response shows "A sweep is already running" warning.
 * Polls GET /ml/sweep/{job_id} every 3s after 202 response from POST /ml/sweep.
 */

import { useState, useRef, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import ParamImportanceChart from "@/components/ParamImportanceChart"
import { Loader2, Play, StopCircle, ChevronDown, ChevronRight, AlertCircle, CheckCircle2 } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765"
const POLL_INTERVAL_MS = 3000

type SweepStatus = "idle" | "running" | "complete" | "error"

interface SweepResult {
  status: string
  best_params?: Record<string, number>
  best_pnl?: number
  n_trials_completed?: number
}

export default function OptunaSweepPanel() {
  const [startDate, setStartDate] = useState("2026-04-07")
  const [endDate, setEndDate] = useState("2026-04-10")
  const [trials, setTrials] = useState(50)
  const [barSeconds, setBarSeconds] = useState<number>(60)

  const [jobId, setJobId] = useState<string | null>(null)
  const [status, setStatus] = useState<SweepStatus>("idle")
  const [nTrialsCompleted, setNTrialsCompleted] = useState<number>(0)
  const [bestParams, setBestParams] = useState<Record<string, number> | null>(null)
  const [bestPnl, setBestPnl] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [paramsExpanded, setParamsExpanded] = useState(false)

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Per T-10-13: always clear interval on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [])

  const stopPolling = () => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }

  const startPolling = (id: string) => {
    stopPolling()
    intervalRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/ml/sweep/${id}`)
        if (!res.ok) {
          stopPolling()
          setStatus("error")
          setError(`Poll error: HTTP ${res.status}`)
          return
        }
        const data = (await res.json()) as SweepResult
        if (data.n_trials_completed != null) {
          setNTrialsCompleted(data.n_trials_completed)
        }
        if (data.status === "complete") {
          stopPolling()
          setStatus("complete")
          setBestParams(data.best_params ?? null)
          setBestPnl(data.best_pnl ?? null)
          setNTrialsCompleted(data.n_trials_completed ?? trials)
          if (data.best_params) setParamsExpanded(true)
        } else if (data.status === "error") {
          stopPolling()
          setStatus("error")
          setError("Sweep job failed on server")
        }
        // "running" / "pending" → keep polling
      } catch (err) {
        stopPolling()
        setStatus("error")
        setError(String(err))
      }
    }, POLL_INTERVAL_MS)
  }

  const handleLaunch = async () => {
    setStatus("running")
    setError(null)
    setBestParams(null)
    setBestPnl(null)
    setNTrialsCompleted(0)
    setJobId(null)

    try {
      const res = await fetch(`${API_BASE}/ml/sweep`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          trials,
          bar_seconds: barSeconds,
        }),
      })

      if (res.status === 409) {
        // Per T-10-14: warn user, don't launch
        setStatus("idle")
        setError("A sweep is already running. Wait for it to complete before launching another.")
        return
      }

      if (!res.ok) {
        const text = await res.text()
        setStatus("error")
        setError(`HTTP ${res.status}: ${text}`)
        return
      }

      const data = (await res.json()) as { job_id: string; status: string }
      setJobId(data.job_id)
      startPolling(data.job_id)
    } catch (err) {
      setStatus("error")
      setError(String(err))
    }
  }

  const isLaunching = status === "running"
  const pnlColor = bestPnl != null && bestPnl >= 0 ? "text-emerald-400" : "text-red-400"

  return (
    <div className="flex flex-col gap-4 max-w-3xl">
      {/* Config form */}
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="border-b border-zinc-800 pb-3">
          <CardTitle className="text-xs font-semibold tracking-widest text-zinc-400 uppercase">
            Launch Optuna Sweep
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {/* Start Date */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-zinc-500">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="h-8 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 text-sm text-zinc-100 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30"
                disabled={isLaunching}
              />
            </div>
            {/* End Date */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-zinc-500">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="h-8 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 text-sm text-zinc-100 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30"
                disabled={isLaunching}
              />
            </div>
            {/* Trials */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-zinc-500">Trials</label>
              <input
                type="number"
                min={10}
                max={500}
                value={trials}
                onChange={(e) => setTrials(Number(e.target.value))}
                className="h-8 rounded-lg border border-zinc-700 bg-zinc-800 px-2.5 text-sm text-zinc-100 outline-none focus:border-amber-500 focus:ring-1 focus:ring-amber-500/30"
                disabled={isLaunching}
              />
            </div>
            {/* Bar Duration */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-zinc-500">Bar Duration</label>
              <Select
                value={String(barSeconds)}
                onValueChange={(v) => setBarSeconds(Number(v))}
                disabled={isLaunching}
              >
                <SelectTrigger className="h-8 border-zinc-700 bg-zinc-800 text-zinc-100 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="60">1 min</SelectItem>
                  <SelectItem value="300">5 min</SelectItem>
                  <SelectItem value="900">15 min</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center gap-3 mt-4">
            <Button
              className="bg-amber-600 text-white hover:bg-amber-500 disabled:opacity-50"
              disabled={isLaunching}
              onClick={handleLaunch}
            >
              {isLaunching ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : (
                <Play className="size-3.5" />
              )}
              {isLaunching ? "Sweep running..." : "LAUNCH SWEEP"}
            </Button>
            {isLaunching && (
              <Button
                variant="outline"
                size="sm"
                className="border-zinc-700 text-zinc-400 hover:text-zinc-200"
                onClick={() => { stopPolling(); setStatus("idle") }}
              >
                <StopCircle className="size-3.5 mr-1" />
                STOP POLLING
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Status display */}
      {error && (
        <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <AlertCircle className="size-4 text-red-400 shrink-0 mt-0.5" />
          <p className="text-sm text-red-300">{error}</p>
        </div>
      )}

      {isLaunching && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <Loader2 className="size-4 animate-spin text-amber-400 shrink-0" />
          <p className="text-sm text-amber-300">
            Running sweep... {nTrialsCompleted}/{trials} trials
          </p>
        </div>
      )}

      {status === "complete" && bestPnl != null && (
        <div className="flex items-center gap-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-4 py-3">
          <CheckCircle2 className="size-4 text-emerald-400 shrink-0" />
          <div>
            <p className="text-xs text-zinc-400">Sweep complete</p>
            <p className={`text-lg font-mono font-semibold ${pnlColor}`}>
              {bestPnl >= 0 ? "+" : ""}{bestPnl.toFixed(2)} pts best P&L
            </p>
          </div>
          {jobId && (
            <p className="ml-auto text-xs text-zinc-600 font-mono truncate max-w-[200px]">
              job: {jobId}
            </p>
          )}
        </div>
      )}

      {/* Best params collapsible */}
      {bestParams && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardHeader
            className="border-b border-zinc-800 pb-3 cursor-pointer select-none"
            onClick={() => setParamsExpanded((e) => !e)}
          >
            <CardTitle className="flex items-center gap-2 text-xs font-semibold tracking-widest text-zinc-300 uppercase">
              {paramsExpanded ? (
                <ChevronDown className="size-3.5" />
              ) : (
                <ChevronRight className="size-3.5" />
              )}
              Best Parameters ({Object.keys(bestParams).length})
            </CardTitle>
          </CardHeader>
          {paramsExpanded && (
            <CardContent className="pt-3">
              <div className="overflow-x-auto rounded border border-zinc-800">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800">
                      <th className="px-3 py-2 text-left text-zinc-500 font-medium">Parameter</th>
                      <th className="px-3 py-2 text-right text-zinc-500 font-medium">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(bestParams)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([key, value]) => (
                        <tr key={key} className="border-b border-zinc-800/50 hover:bg-zinc-800/20">
                          <td className="px-3 py-1.5 font-mono text-zinc-400">{key}</td>
                          <td className="px-3 py-1.5 text-right font-mono text-zinc-200">
                            {typeof value === "number" ? value.toFixed(4) : String(value)}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Param importance chart */}
      {status === "complete" && (
        <Card className="bg-zinc-900 border-zinc-800">
          <CardContent className="pt-4">
            <ParamImportanceChart bestParams={bestParams} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

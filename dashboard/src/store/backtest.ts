/**
 * Zustand store for backtest job state.
 *
 * Per D-05: Zustand for state management.
 * Per T-10-07: pollJob uses clearInterval on complete/error — no runaway polling.
 * runJob: POST /backtest/run → get job_id → start polling every 2s.
 * pollJob: GET /backtest/results/{jobId} → update rows + summary on complete.
 */

import { create } from "zustand"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8765"
const POLL_INTERVAL_MS = 2000

export interface BacktestParams {
  start_date: string
  end_date: string
  bar_seconds: number
}

interface BacktestState {
  jobId: string | null
  status: "idle" | "running" | "complete" | "error"
  rows: Record<string, unknown>[]
  summary: Record<string, unknown> | null
  error: string | null
  runJob: (params: BacktestParams) => Promise<void>
  pollJob: (jobId: string) => void
  reset: () => void
}

export const useBacktestStore = create<BacktestState>()((set, get) => ({
  jobId: null,
  status: "idle",
  rows: [],
  summary: null,
  error: null,

  runJob: async (params) => {
    set({ status: "running", error: null, rows: [], summary: null })
    try {
      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      })
      if (!res.ok) {
        const text = await res.text()
        set({ status: "error", error: `HTTP ${res.status}: ${text}` })
        return
      }
      const data = (await res.json()) as { job_id: string; status: string }
      set({ jobId: data.job_id })
      get().pollJob(data.job_id)
    } catch (err) {
      set({ status: "error", error: String(err) })
    }
  },

  pollJob: (jobId) => {
    // Per T-10-07: always clear interval on terminal states
    const intervalId = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/backtest/results/${jobId}`)
        if (!res.ok) {
          clearInterval(intervalId)
          set({ status: "error", error: `HTTP ${res.status}` })
          return
        }
        const data = (await res.json()) as {
          status: string
          rows?: Record<string, unknown>[]
          summary?: Record<string, unknown>
        }
        if (data.status === "complete") {
          clearInterval(intervalId)
          set({
            status: "complete",
            rows: data.rows ?? [],
            summary: data.summary ?? null,
          })
        } else if (data.status === "error") {
          clearInterval(intervalId)
          set({ status: "error", error: "Backtest job failed on server" })
        }
        // "running" / "pending" → keep polling
      } catch (err) {
        clearInterval(intervalId)
        set({ status: "error", error: String(err) })
      }
    }, POLL_INTERVAL_MS)
  },

  reset: () =>
    set({ jobId: null, status: "idle", rows: [], summary: null, error: null }),
}))

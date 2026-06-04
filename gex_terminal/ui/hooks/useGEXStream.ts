'use client'

import { useEffect, useRef } from 'react'
import { useGEXStore } from '@/store/gexStore'
import type { GEXTerminalSnapshot } from '@/types/gex'

// Use NEXT_PUBLIC_API_URL if set; empty string means same-origin (served by FastAPI on :8780)
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? ''
const MOCK_DATA = process.env.NEXT_PUBLIC_MOCK_DATA === 'true'

/** Exponential backoff delays (ms). */
const BACKOFF = [500, 1000, 2000, 4000, 8000]

export function useGEXStream() {
  const { setSnapshot, setConnected } = useGEXStore()
  const retryCount = useRef(0)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (MOCK_DATA) {
      fetch('/mock-snapshot-bullish.json')
        .then(r => r.json())
        .then((data: GEXTerminalSnapshot) => {
          setSnapshot(data)
          setConnected(true)
        })
        .catch(console.error)
      return
    }

    function connect() {
      const es = new EventSource(`${API_URL}/stream`)
      esRef.current = es

      es.onopen = () => {
        setConnected(true)
        retryCount.current = 0
      }

      es.onmessage = (event) => {
        try {
          const data: GEXTerminalSnapshot = JSON.parse(event.data)
          setSnapshot(data)
        } catch (e) {
          console.error('Failed to parse SSE data:', e)
        }
      }

      es.onerror = () => {
        setConnected(false)
        es.close()
        esRef.current = null

        const delay = BACKOFF[Math.min(retryCount.current, BACKOFF.length - 1)]
        retryCount.current++
        setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      esRef.current?.close()
      esRef.current = null
    }
  }, [setSnapshot, setConnected])
}

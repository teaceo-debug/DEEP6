"use client"

/**
 * WsProvider: initializes WebSocket connection on mount.
 *
 * Per D-23: Token from localStorage; prompt on first load if absent.
 * Per T-10-06: Token validated server-side; client prompt is UX convenience only.
 * Routes incoming messages to Zustand live store.
 */

import { useEffect } from "react"
import { wsClient } from "@/lib/ws"
import { getToken, setToken } from "@/lib/auth"
import { useLiveStore } from "@/store/live"
import type { SignalEvent, TradeEvent } from "@/store/live"

interface WsMessage {
  type: "signal" | "trade" | string
}

function isSignalEvent(d: WsMessage): d is WsMessage & SignalEvent {
  return d.type === "signal"
}

function isTradeEvent(d: WsMessage): d is WsMessage & TradeEvent {
  return d.type === "trade"
}

export function WsProvider({ children }: { children: React.ReactNode }) {
  const setStatus = useLiveStore((s) => s.setStatus)
  const addSignal = useLiveStore((s) => s.addSignal)
  const addTrade = useLiveStore((s) => s.addTrade)

  useEffect(() => {
    let token = getToken()
    if (!token) {
      const prompted = window.prompt(
        "Enter DEEP6 WebSocket token (default: deep6-dev):",
        "deep6-dev"
      )
      token = prompted ?? "deep6-dev"
      setToken(token)
    }

    wsClient.onStatusChange = setStatus
    wsClient.onMessage = (data) => {
      const msg = data as WsMessage
      if (isSignalEvent(msg)) {
        addSignal(msg as unknown as SignalEvent)
      } else if (isTradeEvent(msg)) {
        addTrade(msg as unknown as TradeEvent)
      }
    }

    wsClient.connect(token)

    return () => {
      wsClient.disconnect()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <>{children}</>
}

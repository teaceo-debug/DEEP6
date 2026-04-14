/**
 * WebSocket client with exponential backoff reconnect + token auth.
 *
 * Per D-04: Native WebSocket API (no Socket.io).
 * Per D-18: Exponential backoff — retryDelay doubles on each failure, capped at 30s.
 * Per D-23: Bearer token sent as ?token= query param.
 * Per T-10-06: Token validated server-side in /ws; client prompt is UX convenience.
 */

export type WsStatus = "connecting" | "live" | "stale" | "disconnected"

export class WsClient {
  private ws: WebSocket | null = null
  private retryDelay = 1000      // start at 1s
  private readonly maxDelay = 30000   // cap at 30s
  private shouldReconnect = true
  private retryTimer: ReturnType<typeof setTimeout> | null = null

  onMessage: (data: unknown) => void = () => {}
  onStatusChange: (s: WsStatus) => void = () => {}

  connect(token: string, url = "ws://localhost:8000/ws"): void {
    if (!this.shouldReconnect) return
    this.onStatusChange("connecting")

    try {
      this.ws = new WebSocket(`${url}?token=${encodeURIComponent(token)}`)
    } catch {
      this._scheduleReconnect(token, url)
      return
    }

    this.ws.onopen = () => {
      this.retryDelay = 1000  // reset backoff on successful connection
      this.onStatusChange("live")
    }

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const parsed = JSON.parse(event.data as string)
        this.onMessage(parsed)
      } catch {
        // ignore malformed messages
      }
    }

    this.ws.onclose = () => {
      this.onStatusChange("stale")
      this._scheduleReconnect(token, url)
    }

    this.ws.onerror = () => {
      // onerror always followed by onclose; status update handled there
    }
  }

  disconnect(): void {
    this.shouldReconnect = false
    if (this.retryTimer !== null) {
      clearTimeout(this.retryTimer)
      this.retryTimer = null
    }
    this.ws?.close()
    this.ws = null
    this.onStatusChange("disconnected")
  }

  send(data: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data))
    }
  }

  private _scheduleReconnect(token: string, url: string): void {
    if (!this.shouldReconnect) return
    this.retryTimer = setTimeout(() => {
      this.retryDelay = Math.min(this.retryDelay * 2, this.maxDelay)
      this.connect(token, url)
    }, this.retryDelay)
  }
}

// Module-level singleton — imported by WsProvider
export const wsClient = new WsClient()

"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Signal {
  signal_id: string;
  direction: string;
  strength: number;
  detail: string;
  price: number;
  timestamp: string;
}

export function SignalFeed() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const es = new EventSource(`${API_BASE}/signals/stream`);

    es.onopen = () => setConnected(true);
    es.onmessage = (event) => {
      const signal: Signal = JSON.parse(event.data);
      setSignals((prev) => [signal, ...prev].slice(0, 50));
    };
    es.onerror = () => setConnected(false);

    return () => es.close();
  }, []);

  const directionColor = (dir: string) => {
    if (dir === "BULLISH") return "text-deep6-green";
    if (dir === "BEARISH") return "text-deep6-red";
    return "text-deep6-muted";
  };

  return (
    <div className="bg-deep6-panel border border-deep6-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Signal Feed
        </h2>
        <span className={`text-xs ${connected ? "text-deep6-green" : "text-deep6-muted"}`}>
          {connected ? "LIVE" : "DISCONNECTED"}
        </span>
      </div>

      {signals.length === 0 ? (
        <p className="text-sm text-deep6-muted">Waiting for signals...</p>
      ) : (
        <div className="space-y-2 max-h-96 overflow-y-auto">
          {signals.map((s, i) => (
            <div
              key={`${s.signal_id}-${i}`}
              className="flex items-center justify-between text-sm py-1.5 px-2 rounded bg-deep6-bg"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs text-deep6-accent">{s.signal_id}</span>
                <span className={`font-semibold ${directionColor(s.direction)}`}>
                  {s.direction}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-deep6-muted">
                <span>{(s.strength * 100).toFixed(0)}%</span>
                <span>{s.price.toFixed(2)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

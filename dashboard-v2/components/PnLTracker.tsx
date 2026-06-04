"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Position {
  symbol: string;
  size: number;
  avg_price: number;
  unrealized_pnl: number;
}

export function PnLTracker() {
  const [position, setPosition] = useState<Position | null>(null);

  useEffect(() => {
    const fetchPosition = async () => {
      try {
        const res = await fetch(`${API_BASE}/position`);
        if (res.ok) setPosition(await res.json());
      } catch {
        /* API not available */
      }
    };

    fetchPosition();
    const interval = setInterval(fetchPosition, 2000);
    return () => clearInterval(interval);
  }, []);

  const pnl = position?.unrealized_pnl ?? 0;
  const pnlColor = pnl > 0 ? "text-deep6-green" : pnl < 0 ? "text-deep6-red" : "text-slate-300";

  return (
    <div className="bg-deep6-panel border border-deep6-border rounded-lg p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-400 mb-4">
        P&L Tracker
      </h2>

      <div className="space-y-3">
        {/* Unrealized P&L */}
        <div className="bg-deep6-bg rounded p-3">
          <div className="text-xs text-deep6-muted mb-1">Unrealized P&L</div>
          <div className={`text-2xl font-bold font-mono ${pnlColor}`}>
            ${pnl.toFixed(2)}
          </div>
        </div>

        {/* Position */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-deep6-bg rounded p-3">
            <div className="text-xs text-deep6-muted mb-1">Position</div>
            <div className="text-lg font-mono text-slate-200">
              {position?.size ?? 0}
            </div>
          </div>
          <div className="bg-deep6-bg rounded p-3">
            <div className="text-xs text-deep6-muted mb-1">Avg Price</div>
            <div className="text-lg font-mono text-slate-200">
              {position?.avg_price?.toFixed(2) ?? "—"}
            </div>
          </div>
        </div>

        {/* Symbol */}
        <div className="text-xs text-deep6-muted text-center">
          {position?.symbol ?? "NQ"} Futures
        </div>
      </div>
    </div>
  );
}

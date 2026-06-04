"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Health {
  status: string;
  system_status: string;
  rithmic_connected: boolean;
  bars_processed: number;
}

export function ConnectionStatus() {
  const [health, setHealth] = useState<Health | null>(null);
  const [apiReachable, setApiReachable] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`);
        if (res.ok) {
          setHealth(await res.json());
          setApiReachable(true);
          setLastUpdate(new Date());
        }
      } catch {
        setApiReachable(false);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 3000);
    return () => clearInterval(interval);
  }, []);

  const statusColor = (status: string) => {
    if (status === "killed") return "bg-deep6-red";
    if (status === "running") return "bg-deep6-green";
    return "bg-deep6-yellow";
  };

  return (
    <div className="flex items-center gap-4">
      {/* API status */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${apiReachable ? "bg-deep6-green" : "bg-deep6-red"}`} />
        <span className="text-xs text-deep6-muted">API</span>
      </div>

      {/* Rithmic status */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${health?.rithmic_connected ? "bg-deep6-green" : "bg-deep6-red"}`} />
        <span className="text-xs text-deep6-muted">Rithmic</span>
      </div>

      {/* System state */}
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${statusColor(health?.system_status ?? "idle")}`} />
        <span className="text-xs text-deep6-muted uppercase">
          {health?.system_status ?? "unknown"}
        </span>
      </div>

      {/* Bars processed */}
      <span className="text-xs text-deep6-muted ml-2">
        {health?.bars_processed ?? 0} bars
      </span>

      {/* Last update */}
      {lastUpdate && (
        <span className="text-xs text-deep6-muted">
          {lastUpdate.toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}

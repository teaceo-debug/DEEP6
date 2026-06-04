"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function KillSwitch() {
  const [confirming, setConfirming] = useState(false);
  const [killed, setKilled] = useState(false);

  const handleClick = async () => {
    if (!confirming) {
      setConfirming(true);
      // Auto-cancel confirmation after 3s
      setTimeout(() => setConfirming(false), 3000);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/kill-switch`, { method: "POST" });
      if (res.ok) setKilled(true);
    } catch {
      /* API unreachable */
    }
    setConfirming(false);
  };

  if (killed) {
    return (
      <div className="px-4 py-2 rounded bg-deep6-red/20 border border-deep6-red text-deep6-red text-sm font-semibold">
        SYSTEM KILLED
      </div>
    );
  }

  return (
    <button
      onClick={handleClick}
      className={`px-4 py-2 rounded text-sm font-semibold transition-colors ${
        confirming
          ? "bg-deep6-red text-white animate-pulse"
          : "bg-deep6-red/20 border border-deep6-red text-deep6-red hover:bg-deep6-red hover:text-white"
      }`}
    >
      {confirming ? "CONFIRM KILL" : "KILL SWITCH"}
    </button>
  );
}

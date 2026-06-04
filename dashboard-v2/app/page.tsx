"use client";

import { SignalFeed } from "../components/SignalFeed";
import { PnLTracker } from "../components/PnLTracker";
import { ConnectionStatus } from "../components/ConnectionStatus";
import { KillSwitch } from "../components/KillSwitch";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      {/* Top bar: connection + kill switch */}
      <div className="flex items-center justify-between">
        <ConnectionStatus />
        <KillSwitch />
      </div>

      {/* Main grid: signals + P&L */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Signal feed — takes 2 cols */}
        <div className="lg:col-span-2">
          <SignalFeed />
        </div>

        {/* P&L tracker — right column */}
        <div>
          <PnLTracker />
        </div>
      </div>
    </div>
  );
}

'use client';
import { useEffect } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useReplayController } from '@/hooks/useReplayController';
import { HeaderStrip } from '@/components/layout/HeaderStrip';
import { FootprintChart } from '@/components/footprint/FootprintChart';
import { SignalFeed } from '@/components/signals/SignalFeed';
import { TapeScroll } from '@/components/tape/TapeScroll';
import { ScoreWidget } from '@/components/score/ScoreWidget';
import { ReplayControls } from '@/components/replay/ReplayControls';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';

// Feed-stale threshold per UI-SPEC §Copywriting "no updates in 10s".
const FEED_STALE_SECONDS = 10;

/**
 * useFeedStaleWatcher — polls status.lastTs vs wall clock every second in live
 * mode. Flips tradingStore.status.feedStale when >10s elapsed since last
 * message. Replay mode never triggers staleness.
 */
function useFeedStaleWatcher() {
  useEffect(() => {
    const interval = setInterval(() => {
      const mode = useReplayStore.getState().mode;
      const s = useTradingStore.getState().status;
      const now = Date.now() / 1000;

      const shouldStale =
        mode === 'live' &&
        s.connected &&
        s.lastTs > 0 &&
        now - s.lastTs > FEED_STALE_SECONDS;

      if (shouldStale !== s.feedStale) {
        useTradingStore.setState((prev) => ({
          status: { ...prev.status, feedStale: shouldStale },
        }));
      }
    }, 1000);
    return () => clearInterval(interval);
  }, []);
}

export default function Home() {
  useWebSocket(
    process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/live',
  );
  useReplayController();
  useFeedStaleWatcher();

  return (
    <main className="h-screen w-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      {/* Header strip — 40px — driven by store */}
      <HeaderStrip />

      {/* Error banner — surfaces connection loss, feed stall, replay errors */}
      <ErrorBanner />

      {/* Main 3-column region */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Footprint chart — flex 1, min 600px */}
        <FootprintChart />

        {/* Signal feed + T&S — 320px fixed */}
        <section
          className="flex flex-col shrink-0"
          style={{
            width: '320px',
            background: 'var(--bg-surface)',
            borderRight: '1px solid var(--border-subtle)',
          }}
        >
          <SignalFeed />
          <TapeScroll />
        </section>

        {/* Score widget — 240px fixed */}
        <ScoreWidget />
      </div>

      {/* Replay controls strip — 48px */}
      <ReplayControls />
    </main>
  );
}

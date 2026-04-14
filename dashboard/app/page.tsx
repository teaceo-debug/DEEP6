'use client';
import { useEffect } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useReplayController } from '@/hooks/useReplayController';
import { HeaderStrip } from '@/components/layout/HeaderStrip';
import { FootprintChart } from '@/components/footprint/FootprintChart';
import { SignalFeed } from '@/components/signals/SignalFeed';
import { TapeScroll } from '@/components/tape/TapeScroll';
import { ReplayControls } from '@/components/replay/ReplayControls';
import { ErrorBanner } from '@/components/common/ErrorBanner';
import { useTradingStore } from '@/store/tradingStore';
import { useReplayStore } from '@/store/replayStore';
import { ConfluencePulse } from '@/components/score/ConfluencePulse';
import { KronosBar } from '@/components/score/KronosBar';
import { ZoneList } from '@/components/zones/ZoneList';

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
    <div
      style={{
        height: '100dvh',
        width: '100vw',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--void)',
        color: 'var(--text)',
        overflow: 'hidden',
      }}
    >
      {/* Header strip — 44px */}
      <HeaderStrip />

      {/* Error banner — surfaces connection loss, feed stall, replay errors */}
      <ErrorBanner />

      {/* Main 3-column asymmetric region — flex-1 | 320px hero | 300px right */}
      <main
        style={{
          flex: 1,
          display: 'flex',
          minHeight: 0,
        }}
      >
        {/* Footprint chart — flex-1, min-w-0 */}
        <section
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            borderRight: '1px solid var(--rule)',
          }}
        >
          <FootprintChart />
        </section>

        {/* Hero column — 320px fixed (Confluence Pulse + Kronos + Zone List) */}
        <aside
          style={{
            width: '320px',
            flexShrink: 0,
            borderRight: '1px solid var(--rule)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Confluence Pulse — 360px tall, centered */}
          <div
            style={{
              height: '360px',
              borderBottom: '1px solid var(--rule)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
            }}
          >
            <ConfluencePulse />
          </div>

          {/* Kronos E10 bar */}
          <div
            style={{
              height: '88px',
              borderBottom: '1px solid var(--rule)',
              flexShrink: 0,
            }}
          >
            <KronosBar />
          </div>

          {/* Zone list — fills remaining space */}
          <div
            style={{
              flex: 1,
              minHeight: 0,
              overflow: 'hidden',
            }}
          >
            <ZoneList />
          </div>
        </aside>

        {/* Right column — 300px fixed (Signal Feed + T&S Tape) */}
        <aside
          style={{
            width: '300px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Signal feed — top half */}
          <div
            style={{
              flex: 1,
              minHeight: 0,
              borderBottom: '1px solid var(--rule)',
            }}
          >
            <SignalFeed />
          </div>
          {/* T&S tape — bottom half */}
          <div
            style={{
              flex: 1,
              minHeight: 0,
            }}
          >
            <TapeScroll />
          </div>
        </aside>
      </main>

      {/* Replay strip — 52px */}
      <footer
        style={{
          height: '52px',
          flexShrink: 0,
          borderTop: '1px solid var(--rule)',
        }}
      >
        <ReplayControls />
      </footer>
    </div>
  );
}

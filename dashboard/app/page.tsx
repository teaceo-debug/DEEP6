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

// ── Column separator — 1px --rule gradient that fades at top+bottom ──────────

function ColSep() {
  return (
    <div
      aria-hidden
      style={{
        width: 1,
        flexShrink: 0,
        alignSelf: 'stretch',
        background:
          'linear-gradient(to bottom, transparent 0%, var(--rule) 12%, var(--rule) 88%, transparent 100%)',
        pointerEvents: 'none',
      }}
    />
  );
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
        position: 'relative',
      }}
    >
      {/* Header strip — 44px */}
      <HeaderStrip />

      {/* Error banner — absolute overlay at top:44px, does NOT push content */}
      <ErrorBanner />

      {/* Main 3-column asymmetric region — flex-1 | 340px hero | 320px right */}
      <main
        style={{
          flex: 1,
          display: 'flex',
          minHeight: 0,
          position: 'relative',
        }}
      >
        {/* Footprint chart — flex-1, min-w-0 */}
        <section
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
          }}
        >
          <FootprintChart />
        </section>

        {/* Gradient column separator — chart / hero */}
        <ColSep />

        {/* Hero column — 340px fixed (Confluence Pulse + Kronos + Zone List) */}
        <aside
          style={{
            width: '340px',
            flexShrink: 0,
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

        {/* Gradient column separator — hero / right */}
        <ColSep />

        {/* Right column — 320px fixed (Signal Feed + T&S Tape) */}
        <aside
          style={{
            width: '320px',
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

      {/* Replay strip — variable height (52px + optional 4px scrubber) */}
      <ReplayControls />
    </div>
  );
}

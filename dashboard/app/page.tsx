'use client';
import { useEffect } from 'react';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useInBrowserDemo } from '@/hooks/useInBrowserDemo';
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

// ── Column separator — "well" pattern: 4px surface-1 gutter on each side of
//    the 1px rule. The rule itself reaches 100% opacity at centre, fading at
//    the top (0–8%) and bottom (92–100%) so it never hard-stops. The flanking
//    4px gutters add a hair of depth that separates the column surfaces. ────────

function ColSep() {
  return (
    <div
      aria-hidden
      style={{
        // 9px total: 4px left-gutter + 1px rule + 4px right-gutter
        width: 9,
        flexShrink: 0,
        alignSelf: 'stretch',
        display: 'flex',
        alignItems: 'stretch',
        pointerEvents: 'none',
        // flanking gutter — surface-1 bands that "catch" the column edges
        background:
          'linear-gradient(to right, var(--surface-1) 0px, var(--surface-1) 4px, transparent 4px, transparent 5px, var(--surface-1) 5px, var(--surface-1) 9px)',
      }}
    >
      {/* The 1px rule itself — fades at top and bottom, full opacity at mid */}
      <div
        style={{
          width: 1,
          marginLeft: 4,
          flexShrink: 0,
          alignSelf: 'stretch',
          background:
            'linear-gradient(to bottom, transparent 0%, var(--rule) 8%, var(--rule-bright) 40%, var(--rule-bright) 60%, var(--rule) 92%, transparent 100%)',
        }}
      />
    </div>
  );
}

const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
const WS_URL = DEMO_MODE ? '' : (process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/live');

export default function Home() {
  // useWebSocket is a no-op when url is '' (demo mode skips backend connection)
  const { reconnectNow } = useWebSocket(WS_URL);
  // useInBrowserDemo is a no-op when enabled=false (live mode)
  useInBrowserDemo(DEMO_MODE);
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
      <ErrorBanner reconnectNow={reconnectNow} />

      {/* Main 3-column asymmetric region — flex-1 | 360px hero | 320px right */}
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

        {/* Hero column — 360px fixed (Confluence Pulse + Kronos + Zone List)
             Widened from 340 → 360 to give the compass column enough presence
             to act as a visual anchor, not a sidebar. Background lifted one
             surface level above --void so it reads as a distinct pane. */}
        <aside
          style={{
            width: '360px',
            flexShrink: 0,
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--surface-1)',
          }}
        >
          {/* Confluence Pulse — 360px tall, centered */}
          <div
            style={{
              height: '360px',
              // Gradient rule rendered as absolute child below — no hard border.
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            {/* Fade-rule underline — gradient so it doesn't hard-stop at edges */}
            <div
              aria-hidden
              style={{
                position: 'absolute',
                bottom: 0,
                left: '8%',
                right: '8%',
                height: 1,
                background:
                  'linear-gradient(to right, transparent 0%, var(--rule) 10%, var(--rule-bright) 40%, var(--rule-bright) 60%, var(--rule) 90%, transparent 100%)',
                pointerEvents: 'none',
              }}
            />
            <ConfluencePulse />
          </div>

          {/* Kronos E10 bar — 88px (well under 150px threshold, no compression needed) */}
          <div
            style={{
              height: '88px',
              flexShrink: 0,
              position: 'relative',
            }}
          >
            {/* Fade-rule underline */}
            <div
              aria-hidden
              style={{
                position: 'absolute',
                bottom: 0,
                left: '8%',
                right: '8%',
                height: 1,
                background:
                  'linear-gradient(to right, transparent 0%, var(--rule) 10%, var(--rule-bright) 40%, var(--rule-bright) 60%, var(--rule) 90%, transparent 100%)',
                pointerEvents: 'none',
              }}
            />
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
              position: 'relative',
            }}
          >
            <SignalFeed />
            {/* Fade-rule separator between SignalFeed and TapeScroll */}
            <div
              aria-hidden
              style={{
                position: 'absolute',
                bottom: 0,
                left: '8%',
                right: '8%',
                height: 1,
                background:
                  'linear-gradient(to right, transparent 0%, var(--rule) 10%, var(--rule-bright) 40%, var(--rule-bright) 60%, var(--rule) 90%, transparent 100%)',
                pointerEvents: 'none',
              }}
            />
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

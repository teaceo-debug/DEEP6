'use client';
import { useWebSocket } from '@/hooks/useWebSocket';
import { HeaderStrip } from '@/components/layout/HeaderStrip';
import { FootprintChart } from '@/components/footprint/FootprintChart';
import { SignalFeed } from '@/components/signals/SignalFeed';
import { TapeScroll } from '@/components/tape/TapeScroll';
import { ScoreWidget } from '@/components/score/ScoreWidget';

export default function Home() {
  useWebSocket(
    process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/live',
  );

  return (
    <main className="h-screen w-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      {/* Header strip — 40px — driven by store */}
      <HeaderStrip />

      {/* Main 3-column region */}
      <div className="flex-1 flex min-h-0">
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

      {/* Replay controls strip — 48px (Wave 3 replaces this) */}
      <footer
        className="flex items-center px-4 gap-2 text-[13px] shrink-0"
        style={{
          height: '48px',
          background: 'var(--bg-surface)',
          borderTop: '1px solid var(--border-subtle)',
          color: 'var(--muted)',
        }}
      >
        Replay (Wave 3)
      </footer>
    </main>
  );
}

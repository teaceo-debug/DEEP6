'use client';
import { useWebSocket } from '@/hooks/useWebSocket';
import { HeaderStrip } from '@/components/layout/HeaderStrip';

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
        {/* Footprint chart — flex 1 (Task 2 replaces this) */}
        <section
          className="flex-1 flex items-center justify-center text-[13px]"
          style={{
            minWidth: '600px',
            background: 'var(--bg-base)',
            borderRight: '1px solid var(--border-subtle)',
            color: 'var(--muted)',
          }}
          id="footprint-placeholder"
        >
          Footprint (Wave 2)
        </section>

        {/* Signal feed + T&S — 320px (Task 3 replaces this) */}
        <section
          className="flex flex-col shrink-0"
          style={{
            width: '320px',
            background: 'var(--bg-surface)',
            borderRight: '1px solid var(--border-subtle)',
          }}
        >
          <div className="flex-1 p-4 text-[13px]" style={{ color: 'var(--muted)' }}>
            Signals (Wave 2)
          </div>
          <div
            className="p-4 text-[13px]"
            style={{
              height: '200px',
              borderTop: '1px solid var(--border-subtle)',
              color: 'var(--muted)',
            }}
          >
            Tape &amp; Sales (Wave 2)
          </div>
        </section>

        {/* Score widget — 240px (Task 3 replaces this) */}
        <section
          className="shrink-0 p-4 text-[13px]"
          style={{
            width: '240px',
            background: 'var(--bg-surface)',
            color: 'var(--muted)',
          }}
        >
          Confluence (Wave 2)
        </section>
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

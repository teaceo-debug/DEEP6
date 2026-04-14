export default function Home() {
  return (
    <main className="h-screen w-screen flex flex-col" style={{ background: 'var(--bg-base)' }}>
      {/* Header strip — 40px */}
      <header
        className="flex items-center px-4 gap-4 text-[13px] shrink-0"
        style={{
          height: '40px',
          background: 'var(--bg-surface)',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <span className="font-semibold" style={{ color: 'var(--foreground-strong)', fontFamily: 'var(--font-sans)' }}>DEEP6</span>
        <span className="font-semibold" style={{ color: 'var(--foreground)' }}>NQ</span>
        <span className="font-semibold" style={{ fontFamily: 'var(--font-mono)', color: 'var(--foreground-strong)' }}>—</span>
        <span style={{ color: 'var(--muted)' }}>|</span>
        <span style={{ color: 'var(--muted)' }}>E10</span>
        <span className="font-semibold" style={{ color: 'var(--foreground)' }}>—</span>
        <span style={{ color: 'var(--muted)' }}>|</span>
        <span style={{ color: 'var(--muted)' }}>GEX</span>
        <span className="font-semibold" style={{ color: 'var(--foreground)' }}>—</span>
        <span
          className="ml-auto rounded-full"
          style={{ width: '8px', height: '8px', background: 'var(--muted)' }}
          aria-label="connection status"
        />
      </header>

      {/* Main 3-column region */}
      <div className="flex-1 flex min-h-0">
        {/* Footprint chart — flex 1 */}
        <section
          className="flex-1 flex items-center justify-center text-[13px]"
          style={{
            minWidth: '600px',
            background: 'var(--bg-base)',
            borderRight: '1px solid var(--border-subtle)',
            color: 'var(--muted)',
          }}
        >
          Footprint (Wave 2)
        </section>

        {/* Signal feed + T&S — 320px */}
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

        {/* Score widget — 240px */}
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

      {/* Replay controls strip — 48px */}
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

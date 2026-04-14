/**
 * ReplayControls.tsx — per UI-SPEC v2 §4.8
 *
 * 52px strip: session selector | ⏮ ▶/⏸ ⏭ | bar# input | pos display | speed | LIVE pill
 *
 * Improvements over v1:
 *  - Timeline scrubber (4px, full width, above controls, replay-only)
 *  - Keyboard shortcuts: J=prev, K=play/pause, L=next, 1/2/5=speed
 *  - Bar input width 72px, focus --lime glow (box-shadow)
 *  - Bar position: "142 / 512 (27.7%)" with muted slash + percentage
 *  - Speed selector: 0.5×, 1×, 2×, 5×, auto; selected value in --lime
 *  - Play button shows Pause icon + --lime when playing
 *  - Transport section hint "(J K L)" on hover
 */
'use client';
import { useEffect, useRef, useState } from 'react';
import { SkipBack, Play, Pause, SkipForward } from 'lucide-react';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { useReplayStore, type ReplaySpeed } from '@/store/replayStore';
import { SessionSelector } from './SessionSelector';
import { ReturnToLivePill } from './ReturnToLivePill';

// ── Icon style override per UI-SPEC §7 ───────────────────────────────────────

const ICON_STYLE = { strokeWidth: 1.25, width: 16, height: 16 } as const;

// ── Transport button ──────────────────────────────────────────────────────────

function TransportBtn({
  label,
  disabled,
  active,
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  active?: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      style={{
        width: 36,
        height: 36,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'transparent',
        border: 'none',
        borderRadius: 4,
        cursor: disabled ? 'default' : 'pointer',
        color: active ? 'var(--lime)' : disabled ? 'var(--text-mute)' : 'var(--text)',
        flexShrink: 0,
        transition: 'background 150ms ease, color 150ms ease',
      }}
      onMouseEnter={(e) => {
        if (!disabled) (e.currentTarget as HTMLButtonElement).style.background = 'var(--surface-2)';
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
      }}
    >
      {children}
    </button>
  );
}

// ── Timeline scrubber ─────────────────────────────────────────────────────────

function TimelineScrubber({
  currentBarIndex,
  totalBars,
}: {
  currentBarIndex: number;
  totalBars: number;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [hoverPct, setHoverPct] = useState<number | null>(null);

  const fillPct = totalBars > 0 ? (currentBarIndex / (totalBars - 1)) * 100 : 0;

  function getBarAtX(clientX: number): number {
    const el = trackRef.current;
    if (!el || totalBars === 0) return 0;
    const rect = el.getBoundingClientRect();
    const pct = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return Math.round(pct * (totalBars - 1));
  }

  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    const bar = getBarAtX(e.clientX);
    useReplayStore.getState().jumpToBar(bar);
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = trackRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    setHoverPct(Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100)));
  }

  const hoverBar = hoverPct !== null && totalBars > 0
    ? Math.round((hoverPct / 100) * (totalBars - 1))
    : null;

  return (
    <div
      ref={trackRef}
      onClick={handleClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setHoverPct(null)}
      title={hoverBar !== null ? `Timeline — click to jump · Bar ${hoverBar + 1} of ${totalBars}` : 'Timeline — click to jump'}
      style={{
        width: '100%',
        height: 4,
        background: 'var(--rule)',
        cursor: 'pointer',
        position: 'relative',
        flexShrink: 0,
      }}
    >
      {/* Fill */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          height: '100%',
          width: `${fillPct}%`,
          background: 'var(--lime)',
          transition: 'width 80ms linear',
        }}
      />
      {/* Hover position indicator */}
      {hoverPct !== null && (
        <div
          style={{
            position: 'absolute',
            left: `${hoverPct}%`,
            top: 0,
            height: '100%',
            width: 1,
            background: 'var(--text-dim)',
            pointerEvents: 'none',
          }}
        />
      )}
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ReplayControls() {
  const mode = useReplayStore((s) => s.mode);
  const currentBarIndex = useReplayStore((s) => s.currentBarIndex);
  const totalBars = useReplayStore((s) => s.totalBars);
  const speed = useReplayStore((s) => s.speed);
  const playing = useReplayStore((s) => s.playing);

  const replayDisabled = mode !== 'replay';

  // Bar input local state — controlled, clamped on blur
  const [barInputValue, setBarInputValue] = useState('');
  const [transportHovered, setTransportHovered] = useState(false);

  // Sync input to store when not focused
  const inputFocusedRef = useRef(false);
  useEffect(() => {
    if (!inputFocusedRef.current) {
      setBarInputValue(String(currentBarIndex + 1));
    }
  }, [currentBarIndex]);

  // Keyboard shortcuts: J=prev, K=play/pause, L=next, 1/2/5=speed
  useEffect(() => {
    if (replayDisabled) return;

    function handleKey(e: KeyboardEvent) {
      // Don't intercept when typing in an input/textarea
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      const actions = useReplayStore.getState();
      switch (e.key) {
        case 'j':
        case 'J':
          actions.rewindBar();
          break;
        case 'k':
        case 'K':
          actions.playing ? actions.pause() : actions.play();
          break;
        case 'l':
        case 'L':
          actions.advanceBar();
          break;
        case '1':
          actions.setSpeed('1x');
          break;
        case '2':
          actions.setSpeed('2x');
          break;
        case '5':
          actions.setSpeed('5x');
          break;
      }
    }

    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [replayDisabled]);

  // Bar position display
  const displayIndex = currentBarIndex + 1;
  const pct = totalBars > 0 ? ((currentBarIndex / Math.max(1, totalBars - 1)) * 100).toFixed(1) : '0.0';

  const actions = useReplayStore.getState;

  return (
    <footer
      style={{
        flexShrink: 0,
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--surface-1)',
        borderTop: '1px solid var(--rule)',
      }}
    >
      {/* Timeline scrubber — only in replay mode */}
      {!replayDisabled && (
        <TimelineScrubber
          currentBarIndex={currentBarIndex}
          totalBars={totalBars}
        />
      )}

      {/* Main controls row — 52px */}
      <div
        style={{
          height: 52,
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '0 16px',
        }}
      >
        {/* Session selector — always interactive */}
        <SessionSelector />

        {/* Transport controls — dimmed in live mode */}
        <div
          onMouseEnter={() => setTransportHovered(true)}
          onMouseLeave={() => setTransportHovered(false)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            opacity: replayDisabled ? 0.3 : 1,
            pointerEvents: replayDisabled ? 'none' : 'auto',
            position: 'relative',
          }}
        >
          <TransportBtn
            label="Previous bar (J)"
            disabled={replayDisabled}
            onClick={() => actions().rewindBar()}
          >
            <SkipBack style={ICON_STYLE} />
          </TransportBtn>

          {playing ? (
            <TransportBtn
              label="Pause replay (K)"
              disabled={replayDisabled}
              active={true}
              onClick={() => actions().pause()}
            >
              <Pause style={ICON_STYLE} />
            </TransportBtn>
          ) : (
            <TransportBtn
              label="Play replay (K)"
              disabled={replayDisabled}
              onClick={() => actions().play()}
            >
              <Play style={ICON_STYLE} />
            </TransportBtn>
          )}

          <TransportBtn
            label="Next bar (L)"
            disabled={replayDisabled}
            onClick={() => actions().advanceBar()}
          >
            <SkipForward style={ICON_STYLE} />
          </TransportBtn>

          {/* Keyboard hint — visible on transport hover */}
          {transportHovered && !replayDisabled && (
            <span
              className="text-xs"
              style={{
                position: 'absolute',
                bottom: -14,
                left: '50%',
                transform: 'translateX(-50%)',
                color: 'var(--text-mute)',
                whiteSpace: 'nowrap',
                pointerEvents: 'none',
                letterSpacing: '0.04em',
              }}
            >
              (J K L)
            </span>
          )}
        </div>

        {/* Bar index input */}
        <input
          type="number"
          aria-label="Jump to bar"
          title="Jump to bar #"
          placeholder="bar #"
          min={1}
          max={totalBars}
          value={barInputValue}
          disabled={replayDisabled}
          onChange={(e) => setBarInputValue(e.target.value)}
          onFocus={(e) => {
            inputFocusedRef.current = true;
            (e.currentTarget as HTMLInputElement).style.borderColor = 'var(--lime)';
            (e.currentTarget as HTMLInputElement).style.boxShadow = '0 0 0 2px color-mix(in srgb, var(--lime) 25%, transparent)';
          }}
          onBlur={(e) => {
            inputFocusedRef.current = false;
            (e.currentTarget as HTMLInputElement).style.borderColor = 'var(--rule)';
            (e.currentTarget as HTMLInputElement).style.boxShadow = 'none';
            const n = parseInt((e.target as HTMLInputElement).value, 10);
            if (!Number.isNaN(n)) {
              actions().jumpToBar(n - 1); // UI is 1-based, store is 0-based
            } else {
              setBarInputValue(String(currentBarIndex + 1));
            }
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const n = parseInt((e.target as HTMLInputElement).value, 10);
              if (!Number.isNaN(n)) actions().jumpToBar(n - 1);
              (e.target as HTMLInputElement).blur();
            }
          }}
          style={{
            width: 72,
            height: 36,
            background: 'var(--surface-2)',
            border: '1px solid var(--rule)',
            borderRadius: 4,
            color: replayDisabled ? 'var(--text-mute)' : 'var(--text)',
            fontSize: 13,
            fontVariantNumeric: 'tabular-nums',
            fontFamily: 'var(--font-jetbrains-mono)',
            textAlign: 'center',
            padding: '0 4px',
            outline: 'none',
            opacity: replayDisabled ? 0.4 : 1,
          }}
        />

        {/* Bar position readout */}
        <span
          className="text-sm tnum"
          style={{
            color: 'var(--text-dim)',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'baseline',
            gap: 2,
          }}
        >
          {displayIndex}
          <span style={{ color: 'var(--text-mute)', margin: '0 2px' }}>/</span>
          {totalBars}
          <span
            className="text-xs"
            style={{ color: 'var(--text-mute)', marginLeft: 4 }}
          >
            ({pct}%)
          </span>
        </span>

        {/* Speed selector */}
        <Select
          value={speed}
          disabled={replayDisabled}
          onValueChange={(v) => actions().setSpeed(v as ReplaySpeed)}
        >
          <SelectTrigger
            className="text-sm tnum"
            title="Playback speed (0.5×–5× or auto)"
            style={{
              height: 36,
              width: 80,
              background: 'var(--surface-2)',
              border: '1px solid var(--rule-bright)',
              color: 'var(--text)',
              borderRadius: 4,
              fontFamily: 'var(--font-jetbrains-mono)',
              opacity: replayDisabled ? 0.4 : 1,
            }}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent
            style={{
              background: 'var(--surface-1)',
              border: '1px solid var(--rule-bright)',
              borderRadius: 4,
            }}
          >
            {(['0.5x', '1x', '2x', '5x', 'auto'] as const).map((opt) => (
              <SelectItem
                key={opt}
                value={opt === '0.5x' ? '1x' : opt} // map 0.5x display to nearest stored value
                className="text-sm"
                style={{
                  fontFamily: 'var(--font-jetbrains-mono)',
                  color: speed === opt ? 'var(--lime)' : 'var(--text-dim)',
                }}
              >
                <span style={{ color: 'var(--lime)' }}>×</span>
                {opt.replace('x', '')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* LIVE pill */}
        <ReturnToLivePill />
      </div>
    </footer>
  );
}

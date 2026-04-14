/**
 * ReplayControls.tsx — per UI-SPEC v2 §4.8
 *
 * 52px strip: session selector | ⏮ ▶/⏸ ⏭ | bar# input | pos display | speed | LIVE pill
 * Transport buttons: 36×36, no border, --surface-2 on hover, lucide icons stroke-width 1.25
 * Bar input: 56×36, --surface-2 bg, --rule border, focus --lime border
 * Wiring to useReplayController unchanged — only visual restyle.
 */
'use client';
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
  onClick,
  children,
}: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      aria-label={label}
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
        color: disabled ? 'var(--text-mute)' : 'var(--text)',
        flexShrink: 0,
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

// ── Component ─────────────────────────────────────────────────────────────────

export function ReplayControls() {
  const mode = useReplayStore((s) => s.mode);
  const currentBarIndex = useReplayStore((s) => s.currentBarIndex);
  const totalBars = useReplayStore((s) => s.totalBars);
  const speed = useReplayStore((s) => s.speed);
  const playing = useReplayStore((s) => s.playing);

  const actions = useReplayStore.getState;
  const replayDisabled = mode !== 'replay';

  return (
    <footer
      style={{
        height: 52,
        flexShrink: 0,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '0 16px',
        background: 'var(--surface-1)',
        borderTop: '1px solid var(--rule)',
      }}
    >
      {/* Session selector — always interactive */}
      <SessionSelector />

      {/* Transport controls — dimmed in live mode */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          opacity: replayDisabled ? 0.3 : 1,
          pointerEvents: replayDisabled ? 'none' : 'auto',
        }}
      >
        <TransportBtn
          label="Previous bar"
          disabled={replayDisabled}
          onClick={() => actions().rewindBar()}
        >
          <SkipBack style={ICON_STYLE} />
        </TransportBtn>

        {playing ? (
          <TransportBtn
            label="Pause replay"
            disabled={replayDisabled}
            onClick={() => actions().pause()}
          >
            <Pause style={ICON_STYLE} />
          </TransportBtn>
        ) : (
          <TransportBtn
            label="Play replay"
            disabled={replayDisabled}
            onClick={() => actions().play()}
          >
            <Play style={ICON_STYLE} />
          </TransportBtn>
        )}

        <TransportBtn
          label="Next bar"
          disabled={replayDisabled}
          onClick={() => actions().advanceBar()}
        >
          <SkipForward style={ICON_STYLE} />
        </TransportBtn>

        {/* Bar index input */}
        <input
          type="number"
          aria-label="Jump to bar"
          style={{
            width: 56,
            height: 36,
            background: 'var(--surface-2)',
            border: '1px solid var(--rule)',
            borderRadius: 4,
            color: 'var(--text)',
            fontSize: 13,
            fontVariantNumeric: 'tabular-nums',
            textAlign: 'center',
            padding: '0 4px',
            outline: 'none',
          }}
          onFocus={(e) => {
            (e.currentTarget as HTMLInputElement).style.borderColor = 'var(--lime)';
          }}
          onBlur={(e) => {
            (e.currentTarget as HTMLInputElement).style.borderColor = 'var(--rule)';
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              const n = parseInt((e.target as HTMLInputElement).value, 10);
              if (!Number.isNaN(n)) actions().jumpToBar(n);
            }
          }}
        />

        {/* Bar position display */}
        <span
          className="text-sm tnum"
          style={{ color: 'var(--text-dim)', flexShrink: 0 }}
        >
          {currentBarIndex + 1}/{totalBars}
        </span>

        {/* Speed selector */}
        <Select
          value={speed}
          onValueChange={(v) => actions().setSpeed(v as ReplaySpeed)}
        >
          <SelectTrigger
            className="text-sm tnum"
            style={{
              height: 36,
              width: 72,
              background: 'var(--surface-2)',
              border: '1px solid var(--rule-bright)',
              color: 'var(--text)',
              borderRadius: 4,
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
            <SelectItem value="1x" className="text-sm">1x</SelectItem>
            <SelectItem value="2x" className="text-sm">2x</SelectItem>
            <SelectItem value="5x" className="text-sm">5x</SelectItem>
            <SelectItem value="auto" className="text-sm">auto</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* LIVE pill */}
      <ReturnToLivePill />
    </footer>
  );
}

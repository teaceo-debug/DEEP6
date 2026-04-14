'use client';
/**
 * TapeRow.tsx — per UI-SPEC v2 §4.4 (11.3 upgrade)
 *
 * Upgrades from 11.2 baseline:
 * - 20px rows (up from 18px) for readability
 * - Columns: Time 78px | Price 64px | Side 28px (B/A) | Size right-aligned | Marker 16px
 * - Side label shortened to "B"/"A" (not "BID"/"ASK")
 * - Sizes ≥ 100 get --amber bg pulse (400ms) in addition to side-color flash
 * - Marker glyphs: ★ sweep | ⊟ iceberg | ⓘ kronos
 * - All animations respect prefers-reduced-motion
 */
import { motion, useReducedMotion } from 'motion/react';
import type { TapeEntry } from '@/types/deep6';

// ── Types ─────────────────────────────────────────────────────────────────────

export type TapeMarker = 'sweep' | 'iceberg' | 'kronos' | null;

interface TapeRowProps {
  entry: TapeEntry;
  marker?: TapeMarker;
  /** Sizes ≥ this show bold --text (default 50) */
  oversizeThreshold?: number;
  /** Sizes ≥ this get --amber bg pulse (default 100) */
  largeThreshold?: number;
  /** True if this row just mounted (drives pulse-in animation) */
  isNew?: boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatTime(tsSeconds: number): string {
  const d = new Date(tsSeconds * 1000);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  const ms = String(d.getMilliseconds()).padStart(3, '0');
  return `${hh}:${mm}:${ss}.${ms}`;
}

const MARKER_GLYPH: Record<NonNullable<TapeMarker>, string> = {
  sweep:   '★',
  iceberg: '⊟',
  kronos:  'ⓘ',
};

const MARKER_COLOR: Record<NonNullable<TapeMarker>, string> = {
  sweep:   'var(--amber)',
  iceberg: 'var(--cyan)',
  kronos:  'var(--magenta)',
};

// ── Component ─────────────────────────────────────────────────────────────────

export function TapeRow({
  entry,
  marker = null,
  oversizeThreshold = 50,
  largeThreshold = 100,
  isNew = false,
}: TapeRowProps) {
  const reduced = useReducedMotion();
  const isOversized = entry.size >= oversizeThreshold;
  const isLarge = entry.size >= largeThreshold;

  const sideColor = entry.side === 'ASK' ? 'var(--ask)' : 'var(--bid)';
  // Short label per spec: "B" or "A"
  const sideLabel = entry.side === 'ASK' ? 'A' : 'B';

  const timeStr = formatTime(entry.ts);

  // Determine pulse background:
  // large (≥100) → amber pulse, else side-color pulse at 25%
  const sidePulseBg = entry.side === 'ASK'
    ? 'rgba(0,255,136,0.25)'
    : 'rgba(255,46,99,0.25)';
  const largePulseBg = 'rgba(255,214,10,0.25)'; // --amber at 25%

  const pulseBg = isLarge ? largePulseBg : sidePulseBg;
  const pulseDuration = isLarge ? 0.4 : 0.3;

  return (
    <motion.div
      initial={isNew && !reduced ? { backgroundColor: pulseBg, opacity: 0 } : { backgroundColor: 'transparent', opacity: 1 }}
      animate={{ backgroundColor: 'transparent', opacity: 1 }}
      transition={
        isNew && !reduced
          ? { backgroundColor: { duration: pulseDuration, ease: 'easeOut' }, opacity: { duration: 0.1, ease: 'easeOut' } }
          : { duration: 0 }
      }
      style={{
        height: 20,
        display: 'flex',
        alignItems: 'center',
        padding: '0 8px',
        flexShrink: 0,
        gap: 0,
      }}
    >
      {/* Time — 78px */}
      <span
        className="tnum"
        style={{
          color: 'var(--text-dim)',
          flexShrink: 0,
          width: 78,
          fontSize: 11,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {timeStr}
      </span>

      {/* Price — 64px, right-aligned */}
      <span
        className="tnum"
        style={{
          color: 'var(--text)',
          fontWeight: 600,
          flexShrink: 0,
          width: 64,
          textAlign: 'right',
          fontSize: 11,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {entry.price.toFixed(2)}
      </span>

      {/* Side — 28px centered, shortened to B/A */}
      <span
        style={{
          color: sideColor,
          fontWeight: 600,
          flexShrink: 0,
          width: 28,
          textAlign: 'center',
          fontSize: 11,
        }}
      >
        {sideLabel}
      </span>

      {/* Size — flex fill, right-aligned */}
      <span
        className="tnum"
        style={{
          color: isOversized ? 'var(--text)' : 'var(--text-dim)',
          fontWeight: isOversized ? 600 : 400,
          flex: 1,
          textAlign: 'right',
          fontSize: 11,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {entry.size}
      </span>

      {/* Marker — 16px right-padded */}
      <span
        style={{
          width: 16,
          flexShrink: 0,
          textAlign: 'right',
          fontSize: 11,
          color: marker ? MARKER_COLOR[marker] : 'transparent',
          paddingRight: 0,
        }}
      >
        {marker ? MARKER_GLYPH[marker] : ''}
      </span>
    </motion.div>
  );
}

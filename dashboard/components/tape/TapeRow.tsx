'use client';
/**
 * TapeRow.tsx — per UI-SPEC v2 §4.4
 *
 * 18px row: time | price | side | size | marker
 * New-row pulse: 100ms side-color bg flash + 200ms fade (GPU: opacity only).
 * Marker glyphs: ★ sweep | ⊟ iceberg | ⓘ kronos | blank
 */
import { useEffect, useRef } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { TapeEntry } from '@/types/deep6';

// ── Types ─────────────────────────────────────────────────────────────────────

export type TapeMarker = 'sweep' | 'iceberg' | 'kronos' | null;

interface TapeRowProps {
  entry: TapeEntry;
  marker?: TapeMarker;
  /** Sizes ≥ this threshold get --text weight 600 per UI-SPEC §4.4 */
  oversizeThreshold?: number;
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

// ── Component ─────────────────────────────────────────────────────────────────

export function TapeRow({
  entry,
  marker = null,
  oversizeThreshold = 50,
  isNew = false,
}: TapeRowProps) {
  const reduced = useReducedMotion();
  const isOversized = entry.size >= oversizeThreshold;

  const sideColor = entry.side === 'ASK' ? 'var(--ask)' : 'var(--bid)';
  const sideLabel = entry.side === 'ASK' ? 'ASK' : 'BID';

  // Side-color at 25% opacity for the pulse bg
  const pulseBg = entry.side === 'ASK'
    ? 'rgba(0,255,136,0.25)'   // --ask at 25%
    : 'rgba(255,46,99,0.25)';  // --bid at 25%

  const timeStr = formatTime(entry.ts);

  return (
    <motion.div
      initial={isNew && !reduced ? { backgroundColor: pulseBg } : { backgroundColor: 'transparent' }}
      animate={{ backgroundColor: 'transparent' }}
      transition={isNew && !reduced ? { duration: 0.3, ease: 'easeOut' } : { duration: 0 }}
      style={{
        height: 18,
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '0 8px',
        flexShrink: 0,
      }}
    >
      {/* Time */}
      <span
        className="text-xs tnum"
        style={{ color: 'var(--text-dim)', flexShrink: 0, minWidth: 72 }}
      >
        {timeStr}
      </span>

      {/* Price */}
      <span
        className="text-xs tnum"
        style={{ color: 'var(--text)', flexShrink: 0, minWidth: 64 }}
      >
        {entry.price.toFixed(2)}
      </span>

      {/* Side */}
      <span
        className="text-xs"
        style={{
          color: sideColor,
          fontWeight: 500,
          flexShrink: 0,
          width: 28,
          textAlign: 'center',
        }}
      >
        {sideLabel}
      </span>

      {/* Size */}
      <span
        className="text-xs tnum"
        style={{
          color: isOversized ? 'var(--text)' : 'var(--text-dim)',
          fontWeight: isOversized ? 600 : 400,
          flexShrink: 0,
          minWidth: 28,
          textAlign: 'right',
        }}
      >
        {entry.size}
      </span>

      {/* Marker column — 14px fixed */}
      <span
        className="text-xs"
        style={{
          width: 14,
          flexShrink: 0,
          textAlign: 'right',
          color: 'var(--text-dim)',
        }}
      >
        {marker ? MARKER_GLYPH[marker] : ''}
      </span>
    </motion.div>
  );
}

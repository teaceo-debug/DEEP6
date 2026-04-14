'use client';
/**
 * TapeRow.tsx — per UI-SPEC v2 §4.4 (11.3-r8 upgrade)
 *
 * Upgrades from 11.3 baseline:
 * - Size-tier visual hierarchy: 1-49 muted | 50-99 bright + 2px border | 100-249 600w + 3px border | 250+ side-color bold + bg tint + 4px border
 * - Marker glyph polish: ★ sweep amber glow | ⊟ iceberg cyan pulse | ⓘ kronos magenta
 * - Marker column widened to 18px
 * - Hover expand to 40px: shows running volume at price + direction bias label
 * - All numeric columns use tabular-nums
 * - All animations respect prefers-reduced-motion
 */
import { motion, useReducedMotion } from 'motion/react';
import { useState } from 'react';
import type { TapeEntry } from '@/types/deep6';
import { DURATION } from '@/lib/animations';

// ── Types ─────────────────────────────────────────────────────────────────────

export type TapeMarker = 'sweep' | 'iceberg' | 'kronos' | null;

interface TapeRowProps {
  entry: TapeEntry;
  marker?: TapeMarker;
  /** True if this row just mounted (drives pulse-in animation) */
  isNew?: boolean;
  /** Running total volume at this price level (last 30s) */
  runningVolumeAtPrice?: number;
  /** Direction bias label to show on hover */
  directionBias?: 'BUY AGGRESSION' | 'SELL AGGRESSION' | null;
}

// ── Size-tier helpers ─────────────────────────────────────────────────────────

type SizeTier = 'small' | 'medium' | 'large' | 'whale';

function getSizeTier(size: number): SizeTier {
  if (size >= 250) return 'whale';
  if (size >= 100) return 'large';
  if (size >= 50)  return 'medium';
  return 'small';
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

// Glow / shadow effects per marker type
const MARKER_SHADOW: Record<NonNullable<TapeMarker>, string> = {
  sweep:   '0 0 6px var(--amber)',
  iceberg: '0 0 4px var(--cyan)',
  kronos:  'none',
};

// ── Component ─────────────────────────────────────────────────────────────────

export function TapeRow({
  entry,
  marker = null,
  isNew = false,
  runningVolumeAtPrice,
  directionBias,
}: TapeRowProps) {
  const reduced = useReducedMotion();
  const [hovered, setHovered] = useState(false);

  const tier = getSizeTier(entry.size);
  const sideColor = entry.side === 'ASK' ? 'var(--ask)' : 'var(--bid)';
  const sideColorRaw = entry.side === 'ASK' ? '0,255,136' : '255,46,99';
  const sideLabel = entry.side === 'ASK' ? 'A' : 'B';
  const timeStr = formatTime(entry.ts);

  // ── Size-tier derived styles ────────────────────────────────────────────────

  // Left border width per tier
  const borderWidth = tier === 'whale' ? 4 : tier === 'large' ? 3 : tier === 'medium' ? 2 : 0;

  // Size text color per tier
  const sizeColor = tier === 'whale'
    ? sideColor                    // side-color bold
    : tier === 'large' || tier === 'medium'
      ? 'var(--text)'              // bright
      : 'var(--text-dim)';         // muted

  // Size font weight per tier
  const sizeFontWeight = tier === 'whale' ? 700 : tier === 'large' ? 600 : 400;

  // Whale row: 8% side-color background tint
  const whaleBgTint = tier === 'whale'
    ? `rgba(${sideColorRaw},0.08)`
    : undefined;

  // ── Entry pulse animation ───────────────────────────────────────────────────

  const pulseBg = tier === 'large' || tier === 'whale'
    ? 'rgba(255,214,10,0.25)'                // amber for large/whale
    : `rgba(${sideColorRaw},0.25)`;          // side-color for small/medium

  const pulseDuration = tier === 'whale' ? 0.5 : tier === 'large' ? 0.4 : 0.3;

  // ── Row height via hover ────────────────────────────────────────────────────

  const rowHeight = hovered ? 40 : 20;

  return (
    <motion.div
      initial={isNew && !reduced ? { backgroundColor: pulseBg, opacity: 0 } : { backgroundColor: whaleBgTint ?? 'transparent', opacity: 1 }}
      animate={{ backgroundColor: whaleBgTint ?? 'transparent', opacity: 1 }}
      transition={
        isNew && !reduced
          ? {
              backgroundColor: { duration: pulseDuration, ease: 'easeOut' },
              opacity: { duration: DURATION.fast / 1000, ease: 'easeOut' },
            }
          : { duration: 0 }
      }
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        height: rowHeight,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        padding: '0 8px',
        paddingLeft: borderWidth > 0 ? `${8 - borderWidth}px` : '8px',
        borderLeft: borderWidth > 0 ? `${borderWidth}px solid ${sideColor}` : 'none',
        flexShrink: 0,
        background: hovered ? 'var(--surface-1)' : (whaleBgTint ?? 'transparent'),
        transition: 'height 120ms ease, background 80ms ease',
        overflow: 'hidden',
        cursor: 'default',
      }}
    >
      {/* Main row — always visible */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 0,
          flexShrink: 0,
          height: 20,
        }}
      >
        {/* Time — 78px */}
        <span
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

        {/* Side — 28px centered */}
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

        {/* Size — flex fill, right-aligned, tier-colored */}
        <span
          style={{
            color: sizeColor,
            fontWeight: sizeFontWeight,
            flex: 1,
            textAlign: 'right',
            fontSize: 11,
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {entry.size}
        </span>

        {/* Marker — 18px (up from 16px) */}
        <span
          style={{
            width: 18,
            flexShrink: 0,
            textAlign: 'right',
            fontSize: 11,
            color: marker ? MARKER_COLOR[marker] : 'transparent',
            textShadow: marker ? MARKER_SHADOW[marker] : 'none',
            paddingRight: 0,
          }}
        >
          {marker ? MARKER_GLYPH[marker] : ''}
        </span>
      </div>

      {/* Hover expand — visible when hovered */}
      {hovered && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            height: 16,
            paddingTop: 2,
            flexShrink: 0,
            paddingLeft: 2,
          }}
        >
          {runningVolumeAtPrice != null && (
            <span
              style={{
                color: 'var(--text-dim)',
                fontSize: 10,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              vol@px {runningVolumeAtPrice}
            </span>
          )}
          {directionBias && (
            <span
              style={{
                color: directionBias === 'BUY AGGRESSION' ? 'var(--ask)' : 'var(--bid)',
                fontSize: 10,
                fontWeight: 600,
                letterSpacing: '0.04em',
              }}
            >
              {directionBias}
            </span>
          )}
          {runningVolumeAtPrice == null && !directionBias && (
            <span style={{ color: 'var(--text-mute)', fontSize: 10 }}>
              no detail
            </span>
          )}
        </div>
      )}
    </motion.div>
  );
}

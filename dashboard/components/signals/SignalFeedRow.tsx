'use client';
/**
 * SignalFeedRow.tsx — per UI-SPEC v2 §4.3
 *
 * - 44px default height, expands to 88px on hover (reveals engine detail)
 * - 4px tier-color left border
 * - Status dot pulses for 8s after arrival then goes steady
 * - TYPE_A arrival: 320ms clip-path reveal + 800ms lime flash + 1200ms glow filter
 * - Age ticks every second: +1.2s / +45s / +3m format
 */
import { useState, useEffect, useRef } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import type { SignalEvent } from '@/types/deep6';

// ── Tier color maps ───────────────────────────────────────────────────────────

const TIER_COLOR: Record<string, string> = {
  TYPE_A: 'var(--lime)',
  TYPE_B: 'var(--amber)',
  TYPE_C: 'var(--cyan)',
  QUIET:  'var(--text-mute)',
};

function tierColor(tier: string): string {
  return TIER_COLOR[tier] ?? TIER_COLOR.QUIET;
}

// ── Age formatting ────────────────────────────────────────────────────────────

function formatAge(nowMs: number, signalTsMs: number): string {
  const diffMs = nowMs - signalTsMs;
  if (diffMs < 0) return '+0.0s';
  const diffS = diffMs / 1000;
  if (diffS < 60) {
    // Show one decimal if under 10s, else whole seconds
    if (diffS < 10) return `+${diffS.toFixed(1)}s`;
    return `+${Math.round(diffS)}s`;
  }
  return `+${Math.round(diffS / 60)}m`;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface SignalFeedRowProps {
  sig: SignalEvent;
  narrative?: string;
  /** True for the most-recently-arrived row — drives TYPE_A animation */
  justArrived?: boolean;
}

export function SignalFeedRow({ sig, narrative, justArrived }: SignalFeedRowProps) {
  const reduced = useReducedMotion();

  const tier = sig.tier ?? 'QUIET';
  const color = tierColor(tier);
  const arrivalMs = useRef(Date.now());

  // Track hover state for expand/collapse
  const [hovered, setHovered] = useState(false);

  // Age string — ticks every second
  const [ageStr, setAgeStr] = useState(() => formatAge(Date.now(), sig.ts * 1000));
  useEffect(() => {
    const id = setInterval(() => {
      setAgeStr(formatAge(Date.now(), sig.ts * 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [sig.ts]);

  // Status dot pulse: active for 8s after arrival
  const [dotPulsing, setDotPulsing] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setDotPulsing(false), 8000);
    return () => clearTimeout(timer);
  }, []);

  // TYPE_A arrival animation flags
  const isTypeA = tier === 'TYPE_A';
  const triggerArrival = isTypeA && justArrived === true;

  // Agreement string — UPPERCASE
  const agreementStr = sig.categories_firing?.length
    ? sig.categories_firing.join('+').toUpperCase()
    : '';

  // ── Animation variants ────────────────────────────────────────────────────

  // Clip-path reveal (320ms spring)
  const clipRevealInitial = triggerArrival && !reduced
    ? { clipPath: 'inset(0 100% 0 0)' }
    : { clipPath: 'inset(0 0% 0 0)' };

  const clipRevealAnimate = { clipPath: 'inset(0 0% 0 0)' };

  const clipRevealTransition = reduced
    ? { duration: 0 }
    : { duration: 0.32, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] };

  // Background flash: lime 20% → transparent over 800ms
  const bgFlashAnimate = triggerArrival && !reduced
    ? { backgroundColor: ['rgba(163,255,0,0.2)', 'rgba(163,255,0,0)'] }
    : {};

  const bgFlashTransition = { duration: 0.8, ease: 'easeOut' as const };

  // Glow filter: lime drop-shadow 1200ms → none
  const glowAnimate = triggerArrival && !reduced
    ? {
        filter: [
          'drop-shadow(0 0 8px rgba(163,255,0,0.5))',
          'drop-shadow(0 0 0px rgba(163,255,0,0))',
        ],
      }
    : {};

  const glowTransition = { duration: 1.2, ease: 'easeOut' as const };

  return (
    <motion.div
      initial={clipRevealInitial}
      animate={{
        ...clipRevealAnimate,
        ...(triggerArrival && !reduced ? bgFlashAnimate : {}),
        ...(triggerArrival && !reduced ? glowAnimate : {}),
      }}
      transition={{
        clipPath: clipRevealTransition,
        backgroundColor: bgFlashTransition,
        filter: glowTransition,
      }}
      style={{
        position: 'relative',
        borderLeft: `4px solid ${color}`,
        borderBottom: '1px solid var(--rule)',
        background: hovered ? 'var(--surface-1)' : 'transparent',
        padding: '8px 12px 8px 16px',
        cursor: 'default',
        overflow: 'hidden',
      }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Height wrapper — animate 44 → 88 on hover */}
      <motion.div
        animate={{ height: hovered ? 88 : 44 }}
        transition={reduced ? { duration: 0 } : { duration: 0.18, ease: 'easeOut' }}
        style={{ overflow: 'hidden' }}
      >
        {/* ── Top line: dot + badge + narrative + age ── */}
        <div
          style={{
            height: 14,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            overflow: 'hidden',
          }}
        >
          {/* Status dot */}
          <motion.div
            animate={
              dotPulsing && !reduced
                ? { scale: [1, 1.2, 1], opacity: [1, 0.6, 1] }
                : { scale: 1, opacity: 1 }
            }
            transition={
              dotPulsing && !reduced
                ? { duration: 1.2, repeat: Infinity, ease: 'easeInOut' }
                : { duration: 0 }
            }
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: color,
              flexShrink: 0,
            }}
          />

          {/* Tier badge [TYPE_A] */}
          <span
            className="text-xs label-tracked"
            style={{
              color,
              fontWeight: 600,
              letterSpacing: '0.08em',
              flexShrink: 0,
            }}
          >
            [{tier}]
          </span>

          {/* Narrative */}
          <span
            className="text-sm"
            style={{
              color: 'var(--text)',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {narrative ?? ''}
          </span>

          {/* Age */}
          <span
            className="text-xs tnum"
            style={{
              color: 'var(--text-dim)',
              flexShrink: 0,
            }}
          >
            {ageStr}
          </span>
        </div>

        {/* ── Bottom line: score + agreement + chevron ── */}
        <div
          style={{
            height: 14,
            marginTop: 4,
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            overflow: 'hidden',
          }}
        >
          <span
            className="text-xs tnum"
            style={{ color, fontWeight: 600, flexShrink: 0 }}
          >
            {Math.round(sig.total_score)}
          </span>
          <span style={{ color: 'var(--text-mute)', flexShrink: 0 }}>·</span>
          <span
            className="text-xs"
            style={{
              color: 'var(--text-dim)',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {agreementStr}
          </span>
          <span
            className="text-xs"
            style={{ color: 'var(--text-mute)', flexShrink: 0 }}
          >
            →
          </span>
        </div>

        {/* ── Hover-expand content (visible at 88px) ── */}
        {hovered && (
          <div
            style={{
              marginTop: 6,
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              rowGap: 2,
              columnGap: 12,
            }}
          >
            <DetailPair label="AGREEMENT" value={`${Math.round(sig.engine_agreement)}%`} />
            <DetailPair label="GEX" value={sig.gex_regime ?? '—'} />
            <DetailPair
              label="KRONOS"
              value={sig.kronos_bias != null ? sig.kronos_bias.toFixed(2) : '—'}
            />
            <DetailPair label="CATS" value={String(sig.category_count ?? 0)} />
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

// ── Detail pair (used in hover-expand section) ────────────────────────────────

function DetailPair({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', gap: 4, alignItems: 'baseline' }}>
      <span
        className="text-xs label-tracked"
        style={{ color: 'var(--text-dim)', letterSpacing: '0.08em' }}
      >
        {label}
      </span>
      <span
        className="text-xs tnum"
        style={{ color: 'var(--text)', fontVariantNumeric: 'tabular-nums' }}
      >
        {value}
      </span>
    </div>
  );
}

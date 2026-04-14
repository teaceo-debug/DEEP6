'use client';
/**
 * SignalFeedRow.tsx — per UI-SPEC v2 §4.3 (11.3 upgrade)
 *
 * Upgrades from 11.2 baseline:
 * - 40px default (compressed from 44px)
 * - 96px hover expand (spring stiffness:180 damping:20)
 * - Hover reveals: engine_agreement bar, GEX pill, Kronos capsule, 8-dot category row
 * - TYPE_A arrival: clip-path reveal + lime halo + border pulse + 3x glow + 1200ms flash
 * - Status dot pulses 10s, then steady with faint glow ring
 * - hover bg fades in at 300ms
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'motion/react';
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

// ── GEX regime color ──────────────────────────────────────────────────────────

function gexColor(regime: string): string {
  if (regime === 'POS_GAMMA') return 'var(--ask)';
  if (regime === 'NEG_GAMMA') return 'var(--bid)';
  return 'var(--text-mute)';
}

// ── Age formatting ────────────────────────────────────────────────────────────

function formatAge(nowMs: number, signalTsMs: number): string {
  const diffMs = nowMs - signalTsMs;
  if (diffMs < 0) return '+0.0s';
  const diffS = diffMs / 1000;
  if (diffS < 60) {
    if (diffS < 10) return `+${diffS.toFixed(1)}s`;
    return `+${Math.round(diffS)}s`;
  }
  return `+${Math.round(diffS / 60)}m`;
}

// ── 8 canonical categories ────────────────────────────────────────────────────

const ALL_CATEGORIES = ['ABS', 'EXH', 'IMB', 'DELTA', 'AUCT', 'VOL', 'TRAP', 'ML'];

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
  const isTypeA = tier === 'TYPE_A';
  const triggerArrival = isTypeA && justArrived === true;

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

  // Status dot pulse: active for 10s after arrival (up from 8s)
  const [dotPulsing, setDotPulsing] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setDotPulsing(false), 10_000);
    return () => clearTimeout(timer);
  }, []);

  // Border pulse animation: 3x expand-contract (4px → 8px → 4px) over 600ms
  const [borderPulsing, setBorderPulsing] = useState(triggerArrival);
  useEffect(() => {
    if (triggerArrival) {
      setBorderPulsing(true);
      const t = setTimeout(() => setBorderPulsing(false), 700);
      return () => clearTimeout(t);
    }
  }, [triggerArrival]);

  // Glow halo behind row
  const [haloVisible, setHaloVisible] = useState(triggerArrival);
  useEffect(() => {
    if (triggerArrival) {
      setHaloVisible(true);
      const t = setTimeout(() => setHaloVisible(false), 1800);
      return () => clearTimeout(t);
    }
  }, [triggerArrival]);

  // Agreement string — UPPERCASE
  const agreementStr = sig.categories_firing?.length
    ? sig.categories_firing.join('+').toUpperCase()
    : '';

  // Firing categories set for 8-dot indicator
  const firingSet = new Set(
    (sig.categories_firing ?? []).map((c) => c.toUpperCase())
  );

  // ── Animation config ──────────────────────────────────────────────────────

  // Clip-path reveal (400ms spring)
  const clipInitial = triggerArrival && !reduced
    ? { clipPath: 'inset(0 100% 0 0)' }
    : { clipPath: 'inset(0 0% 0 0)' };

  const clipAnimate = { clipPath: 'inset(0 0% 0 0)' };

  // Combined row animation: clip + bg flash + glow
  const rowAnimate: Record<string, unknown> = { ...clipAnimate };
  const rowTransition: Record<string, unknown> = {
    clipPath: reduced
      ? { duration: 0 }
      : { duration: 0.4, ease: [0.16, 1, 0.3, 1] as [number, number, number, number] },
  };

  if (triggerArrival && !reduced) {
    rowAnimate.backgroundColor = ['rgba(163,255,0,0.25)', 'rgba(163,255,0,0)'];
    rowTransition.backgroundColor = { duration: 1.2, ease: 'easeOut' };

    rowAnimate.filter = [
      'drop-shadow(0 0 12px rgba(163,255,0,0.7)) drop-shadow(0 0 4px rgba(163,255,0,0.5))',
      'drop-shadow(0 0 0px rgba(163,255,0,0))',
    ];
    rowTransition.filter = { duration: 1.8, ease: 'easeOut' };
  }

  // Border width animation for TYPE_A pulse
  const borderWidthAnimate = borderPulsing && !reduced
    ? { borderLeftWidth: ['4px', '8px', '4px', '8px', '4px', '8px', '4px'] }
    : { borderLeftWidth: '4px' };
  const borderTransition = borderPulsing && !reduced
    ? { duration: 0.6, ease: 'easeInOut' as const }
    : { duration: 0 };

  // ── Dot pulse size: TYPE_A pulses slightly bigger ─────────────────────────
  const dotPulseScale = isTypeA ? [1, 1.35, 1] : [1, 1.2, 1];

  // After pulse period: faint glow ring on dot
  const dotSteadyStyle = !dotPulsing
    ? {
        boxShadow: `0 0 0 2px color-mix(in oklch, ${color} 20%, transparent)`,
      }
    : {};

  return (
    <div style={{ position: 'relative' }}>
      {/* Lime halo layer — absolute behind row */}
      <AnimatePresence>
        {haloVisible && !reduced && (
          <motion.div
            key="halo"
            initial={{ opacity: 0.3 }}
            animate={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 1.8, ease: 'easeOut' }}
            style={{
              position: 'absolute',
              inset: 0,
              background:
                'radial-gradient(ellipse at 50% 50%, rgba(163,255,0,0.30) 0%, rgba(163,255,0,0) 70%)',
              pointerEvents: 'none',
              zIndex: 0,
            }}
          />
        )}
      </AnimatePresence>

      {/* Main row */}
      <motion.div
        initial={clipInitial}
        animate={
          (triggerArrival && !reduced
            ? { ...rowAnimate, ...borderWidthAnimate }
            : rowAnimate) as Parameters<typeof motion.div>[0]['animate']
        }
        transition={
          triggerArrival && !reduced
            ? { ...rowTransition, borderLeftWidth: borderTransition }
            : rowTransition
        }
        style={{
          position: 'relative',
          zIndex: 1,
          borderLeft: `4px solid ${color}`,
          borderBottom: '1px solid var(--rule)',
          padding: '4px 10px 4px 12px',
          cursor: 'default',
          overflow: 'hidden',
          backgroundColor: hovered ? 'var(--surface-1)' : undefined,
          transition: 'background-color 300ms ease',
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        {/* Height wrapper — animate 40 → 96 on hover */}
        <motion.div
          animate={{ height: hovered ? 96 : 40 }}
          transition={
            reduced
              ? { duration: 0 }
              : { type: 'spring', stiffness: 180, damping: 20 }
          }
          style={{ overflow: 'hidden' }}
        >
          {/* ── Top line: dot + badge + narrative + age ── */}
          <div
            style={{
              height: 16,
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
                  ? { scale: dotPulseScale, opacity: [1, 0.55, 1] }
                  : { scale: 1, opacity: 1 }
              }
              transition={
                dotPulsing && !reduced
                  ? { duration: 1.0, repeat: Infinity, ease: 'easeInOut' }
                  : { duration: 0 }
              }
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                background: color,
                flexShrink: 0,
                ...dotSteadyStyle,
              }}
            />

            {/* Tier badge [TYPE_A] */}
            <span
              style={{
                color,
                fontWeight: 600,
                letterSpacing: '0.08em',
                fontSize: 11,
                flexShrink: 0,
              }}
            >
              [{tier}]
            </span>

            {/* Narrative */}
            <span
              style={{
                color: 'var(--text)',
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 12,
              }}
            >
              {narrative ?? ''}
            </span>

            {/* Age */}
            <span
              className="tnum"
              style={{
                color: 'var(--text-dim)',
                flexShrink: 0,
                fontSize: 11,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {ageStr}
            </span>
          </div>

          {/* ── Bottom line: score + agreement + chevron ── */}
          <div
            style={{
              height: 14,
              marginTop: 3,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              overflow: 'hidden',
            }}
          >
            <span
              className="tnum"
              style={{
                color,
                fontWeight: 700,
                flexShrink: 0,
                fontSize: 12,
                fontVariantNumeric: 'tabular-nums',
              }}
            >
              {Math.round(sig.total_score)}
            </span>
            <span style={{ color: 'var(--text-mute)', flexShrink: 0, fontSize: 11 }}>·</span>
            <span
              style={{
                color: 'var(--text-dim)',
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 11,
                letterSpacing: '0.03em',
              }}
            >
              {agreementStr}
            </span>
            <span
              style={{ color: 'var(--text-mute)', flexShrink: 0, fontSize: 11 }}
            >
              →
            </span>
          </div>

          {/* ── Hover-expand content (visible at 96px) ── */}
          <AnimatePresence>
            {hovered && (
              <motion.div
                key="expand"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                style={{
                  marginTop: 6,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                }}
              >
                {/* Engine agreement bar */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      color: 'var(--text-dim)',
                      fontSize: 10,
                      letterSpacing: '0.08em',
                      width: 56,
                      flexShrink: 0,
                    }}
                  >
                    AGREE
                  </span>
                  <div
                    style={{
                      flex: 1,
                      height: 5,
                      background: 'var(--rule-bright)',
                      borderRadius: 2,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${Math.min(100, Math.round(sig.engine_agreement))}%`,
                        background: color,
                        borderRadius: 2,
                        transition: 'width 400ms ease',
                      }}
                    />
                  </div>
                  <span
                    className="tnum"
                    style={{
                      color: 'var(--text-dim)',
                      fontSize: 10,
                      width: 30,
                      textAlign: 'right',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {Math.round(sig.engine_agreement)}%
                  </span>
                </div>

                {/* GEX pill + Kronos capsule row */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  {/* GEX pill */}
                  <span
                    style={{
                      fontSize: 10,
                      color: gexColor(sig.gex_regime ?? ''),
                      border: `1px solid ${gexColor(sig.gex_regime ?? '')}`,
                      borderRadius: 3,
                      padding: '0 4px',
                      letterSpacing: '0.06em',
                      flexShrink: 0,
                    }}
                  >
                    GEX {sig.gex_regime ?? 'N/A'}
                  </span>

                  {/* Kronos mini-capsule */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 3,
                      flexShrink: 0,
                    }}
                  >
                    <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>
                      KRONOS
                    </span>
                    <div
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: 'var(--magenta)',
                        opacity:
                          sig.kronos_bias != null
                            ? 0.3 + (Math.abs(sig.kronos_bias) / 100) * 0.7
                            : 0.3,
                        flexShrink: 0,
                      }}
                    />
                    <span
                      className="tnum"
                      style={{
                        color: 'var(--magenta)',
                        fontSize: 10,
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {sig.kronos_bias != null ? `${Math.round(sig.kronos_bias)}%` : '—'}
                    </span>
                  </div>
                </div>

                {/* 8-dot category indicator */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span
                    style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: '0.06em' }}
                  >
                    CATS {(sig.category_count ?? 0)}/8
                  </span>
                  <div style={{ display: 'flex', gap: 3, marginLeft: 2 }}>
                    {ALL_CATEGORIES.map((cat) => {
                      const lit = firingSet.has(cat);
                      return (
                        <div
                          key={cat}
                          title={cat}
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: '50%',
                            background: lit ? color : 'var(--rule-bright)',
                            boxShadow: lit
                              ? `0 0 3px color-mix(in oklch, ${color} 60%, transparent)`
                              : 'none',
                            transition: 'background 200ms',
                          }}
                        />
                      );
                    })}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </motion.div>
    </div>
  );
}

'use client';
/**
 * SignalFeedRow.tsx — per UI-SPEC v2 §4.3 (11.3-r2 upgrade)
 *
 * Upgrades from 11.3 baseline:
 * - Score mini-bar: 2px progress bar at row bottom, tier-colored, width = total_score/100
 * - Age format: +0.0s / +45s / +3m / +2h / +1d — right-aligned fixed width
 * - Narrative: strip leading ticker prefix (e.g. "NQ." / "ES."); text-transform: none
 * - Hover expand: bar_index, entry-bias hint, full narrative (unwrapped), trading-card feel
 * - TYPE_A arrival: scan line sweep (left to right 500ms then fade)
 * - Status dot: 2px halo (40% tier color) when not pulsing; scale 1.0 to 1.25 when pulsing
 * - Row separator: 1px --rule between rows
 */
import { useState, useEffect } from 'react';
import { motion, useReducedMotion, AnimatePresence } from 'motion/react';
import type { SignalEvent } from '@/types/deep6';
import { DURATION, EASING, SPRING } from '@/lib/animations';

// -- Tier color maps ----------------------------------------------------------

const TIER_COLOR: Record<string, string> = {
  TYPE_A: 'var(--lime)',
  TYPE_B: 'var(--amber)',
  TYPE_C: 'var(--cyan)',
  QUIET:  'var(--text-mute)',
};

function tierColor(tier: string): string {
  return TIER_COLOR[tier] ?? TIER_COLOR.QUIET;
}

// -- GEX regime color ---------------------------------------------------------

function gexColor(regime: string): string {
  if (regime === 'POS_GAMMA') return 'var(--ask)';
  if (regime === 'NEG_GAMMA') return 'var(--bid)';
  return 'var(--text-mute)';
}

// -- Age formatting -----------------------------------------------------------

function formatAge(nowMs: number, signalTsMs: number): string {
  const diffMs = nowMs - signalTsMs;
  if (diffMs < 0) return '+0.0s';
  const diffS = diffMs / 1000;
  if (diffS < 10)  return `+${diffS.toFixed(1)}s`;
  if (diffS < 60)  return `+${Math.round(diffS)}s`;
  const diffM = diffS / 60;
  if (diffM < 60)  return `+${Math.round(diffM)}m`;
  const diffH = diffM / 60;
  if (diffH < 24)  return `+${Math.round(diffH)}h`;
  return `+${Math.round(diffH / 24)}d`;
}

// -- Strip leading ticker prefix (e.g. "NQ. " / "ES. " / "NQ ") --------------

function stripTickerPrefix(text: string): string {
  return text.replace(/^[A-Z]{1,4}[.\s]+/, '');
}

// -- Entry-bias hint ----------------------------------------------------------

function entryBiasHint(tier: string, direction: -1 | 0 | 1, score: number): string | null {
  if (tier === 'QUIET') return null;
  const pct = Math.round(Math.min(99, Math.max(50, score)));
  if (direction === 1) {
    if (tier === 'TYPE_A') return `BULL IDEA ${pct}%`;
    if (tier === 'TYPE_B') return `BULL WATCH ${pct}%`;
    return `BULL CAUTION ${pct}%`;
  }
  if (direction === -1) {
    if (tier === 'TYPE_A') return `BEAR IDEA ${pct}%`;
    if (tier === 'TYPE_B') return `BEAR WATCH ${pct}%`;
    return `BEAR CAUTION ${pct}%`;
  }
  return `NEUTRAL ${pct}%`;
}

// -- 8 canonical categories ---------------------------------------------------

const ALL_CATEGORIES = ['ABS', 'EXH', 'IMB', 'DELTA', 'AUCT', 'VOL', 'TRAP', 'ML'];

// -- Component ----------------------------------------------------------------

interface SignalFeedRowProps {
  sig: SignalEvent;
  narrative?: string;
  justArrived?: boolean;
  isSelected?: boolean;
  onClick?: () => void;
}

export function SignalFeedRow({ sig, narrative, justArrived, isSelected, onClick }: SignalFeedRowProps) {
  const reduced = useReducedMotion();

  const tier = sig.tier ?? 'QUIET';
  const color = tierColor(tier);
  const isTypeA = tier === 'TYPE_A';
  const triggerArrival = isTypeA && justArrived === true;

  const [hovered, setHovered] = useState(false);

  const [ageStr, setAgeStr] = useState(() => formatAge(Date.now(), sig.ts * 1000));
  useEffect(() => {
    const id = setInterval(() => {
      setAgeStr(formatAge(Date.now(), sig.ts * 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [sig.ts]);

  const [dotPulsing, setDotPulsing] = useState(true);
  useEffect(() => {
    const timer = setTimeout(() => setDotPulsing(false), 10_000);
    return () => clearTimeout(timer);
  }, []);

  const [borderPulsing, setBorderPulsing] = useState(triggerArrival);
  useEffect(() => {
    if (triggerArrival) {
      setBorderPulsing(true);
      const t = setTimeout(() => setBorderPulsing(false), 700);
      return () => clearTimeout(t);
    }
  }, [triggerArrival]);

  const [haloVisible, setHaloVisible] = useState(triggerArrival);
  useEffect(() => {
    if (triggerArrival) {
      setHaloVisible(true);
      const t = setTimeout(() => setHaloVisible(false), 1800);
      return () => clearTimeout(t);
    }
  }, [triggerArrival]);

  const [scanVisible, setScanVisible] = useState(triggerArrival);
  useEffect(() => {
    if (triggerArrival) {
      setScanVisible(true);
      const t = setTimeout(() => setScanVisible(false), 900);
      return () => clearTimeout(t);
    }
  }, [triggerArrival]);

  const agreementStr = sig.categories_firing?.length
    ? sig.categories_firing.join('+').toUpperCase()
    : '';

  const firingSet = new Set(
    (sig.categories_firing ?? []).map((c) => c.toUpperCase())
  );

  const rawNarrative = narrative ?? '';
  const shortNarrative = stripTickerPrefix(rawNarrative);
  const biasHint = entryBiasHint(tier, sig.direction, sig.total_score);
  const scoreBarPct = Math.min(100, Math.max(0, sig.total_score));

  // -- Animation config ------------------------------------------------------

  const clipInitial = triggerArrival && !reduced
    ? { clipPath: 'inset(0 100% 0 0)' }
    : { clipPath: 'inset(0 0% 0 0)' };

  const clipAnimate = { clipPath: 'inset(0 0% 0 0)' };

  const rowAnimate: Record<string, unknown> = { ...clipAnimate };
  const rowTransition: Record<string, unknown> = {
    clipPath: reduced
      ? { duration: 0 }
      : { duration: DURATION.entrance / 1000 * 0.5, ease: EASING.spring as [number, number, number, number] }, // 400ms entrance spring
  };

  if (triggerArrival && !reduced) {
    rowAnimate.backgroundColor = ['rgba(163,255,0,0.25)', 'rgba(163,255,0,0)'];
    rowTransition.backgroundColor = { duration: DURATION.flash / 1000, ease: 'easeOut' }; // 1200ms flash decay
    rowAnimate.filter = [
      'drop-shadow(0 0 12px rgba(163,255,0,0.7)) drop-shadow(0 0 4px rgba(163,255,0,0.5))',
      'drop-shadow(0 0 0px rgba(163,255,0,0))',
    ];
    rowTransition.filter = { duration: DURATION.flash / 1000 * 1.5, ease: 'easeOut' }; // 1800ms glow decay
  }

  const borderWidthAnimate = borderPulsing && !reduced
    ? { borderLeftWidth: ['4px', '8px', '4px', '8px', '4px', '8px', '4px'] }
    : { borderLeftWidth: '4px' };
  const borderTransition = borderPulsing && !reduced
    ? { duration: DURATION.normal / 1000 * 2.4, ease: 'easeInOut' as const } // 600ms border pulse
    : { duration: 0 };

  // Scale 1.0 to 1.25 per spec (unified for TYPE_A and others)
  const dotPulseScale = [1, 1.25, 1];

  // 2px halo at 40% tier-color opacity when not pulsing
  const dotSteadyStyle = !dotPulsing
    ? { boxShadow: `0 0 0 2px color-mix(in oklch, ${color} 40%, transparent)` }
    : {};

  // suppress unused-var warning: isTypeA is used in dotPulseScale context but
  // we keep it for clarity and future use
  void isTypeA;

  return (
    <div style={{ position: 'relative' }}>
      {/* Lime halo layer */}
      <AnimatePresence>
        {haloVisible && !reduced && (
          <motion.div
            key="halo"
            initial={{ opacity: 0.3 }}
            animate={{ opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: DURATION.flash / 1000 * 1.5, ease: 'easeOut' }} // 1800ms glow decay
            style={{
              position: 'absolute',
              inset: 0,
              background: 'radial-gradient(ellipse at 50% 50%, rgba(163,255,0,0.30) 0%, rgba(163,255,0,0) 70%)',
              pointerEvents: 'none',
              zIndex: 0,
            }}
          />
        )}
      </AnimatePresence>

      {/* TYPE_A scan line sweeps left to right */}
      <AnimatePresence>
        {scanVisible && !reduced && (
          <motion.div
            key="scanline"
            initial={{ left: '-2px', opacity: 0.8 }}
            animate={{ left: '102%', opacity: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: DURATION.slow / 1000, ease: 'linear' }} // 500ms scan sweep
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              width: 2,
              background: 'var(--lime)',
              pointerEvents: 'none',
              zIndex: 2,
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
          borderLeft: isSelected ? `6px solid ${color}` : `4px solid ${color}`,
          borderBottom: '1px solid var(--rule)',
          paddingTop: 4,
          paddingRight: 10,
          paddingBottom: 0,
          paddingLeft: isSelected ? 10 : 12,
          cursor: 'pointer',
          overflow: 'hidden',
          backgroundColor: isSelected
            ? 'var(--surface-1)'
            : hovered
            ? 'var(--surface-1)'
            : undefined,
          boxShadow: isSelected
            ? `inset 0 0 12px color-mix(in oklch, ${color} 10%, transparent), -2px 0 8px color-mix(in oklch, ${color} 25%, transparent)`
            : undefined,
          transition: `background-color ${DURATION.normal}ms ease, border-left-width ${DURATION.fast}ms ease, box-shadow ${DURATION.normal}ms ease`,
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        onClick={onClick}
      >
        {/* Height wrapper */}
        <motion.div
          animate={{ height: hovered ? 106 : 42 }}
          transition={
            reduced
              ? { duration: 0 }
              : { type: 'spring', stiffness: 180, damping: 20 } // hover expand — intentionally softer than SPRING.snap
          }
          style={{ overflow: 'hidden' }}
        >
          {/* Top line: dot + badge + narrative + age */}
          <div
            style={{
              height: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              overflow: 'hidden',
            }}
          >
            <motion.div
              animate={
                dotPulsing && !reduced
                  ? { scale: dotPulseScale, opacity: [1, 0.55, 1] }
                  : { scale: 1, opacity: 1 }
              }
              transition={
                dotPulsing && !reduced
                  ? { duration: DURATION.slow / 1000 * 2.4, repeat: Infinity, ease: 'easeInOut' } // 1200ms dot pulse loop
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

            <span
              style={{
                color: 'var(--text)',
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 12,
                textTransform: 'none',
              }}
            >
              {shortNarrative}
            </span>

            <span
              className="tnum"
              style={{
                color: 'var(--text-dim)',
                flexShrink: 0,
                fontSize: 11,
                fontVariantNumeric: 'tabular-nums',
                textAlign: 'right',
                minWidth: 44,
              }}
            >
              {ageStr}
            </span>
          </div>

          {/* Score + agreement line */}
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
            <span style={{ color: 'var(--text-mute)', flexShrink: 0, fontSize: 11 }}>
              &rarr;
            </span>
          </div>

          {/* Hover trading card */}
          <AnimatePresence>
            {hovered && (
              <motion.div
                key="expand"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: DURATION.fast / 1000 }} // 150ms microinteraction
                style={{
                  marginTop: 5,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 3,
                }}
              >
                {/* Engine agreement bar + bar index */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      color: 'var(--text-dim)',
                      fontSize: 10,
                      letterSpacing: '0.08em',
                      width: 40,
                      flexShrink: 0,
                    }}
                  >
                    AGREE
                  </span>
                  <div
                    style={{
                      flex: 1,
                      height: 4,
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
                        transition: `width ${DURATION.entrance / 2}ms ease`, // 400ms bar fill
                      }}
                    />
                  </div>
                  <span
                    className="tnum"
                    style={{
                      color: 'var(--text-dim)',
                      fontSize: 10,
                      width: 28,
                      textAlign: 'right',
                      fontVariantNumeric: 'tabular-nums',
                      flexShrink: 0,
                    }}
                  >
                    {Math.round(sig.engine_agreement)}%
                  </span>
                  <span
                    style={{
                      color: 'var(--text-dim)',
                      fontSize: 10,
                      flexShrink: 0,
                      marginLeft: 4,
                    }}
                  >
                    bar #{sig.bar_index_in_session}
                  </span>
                </div>

                {/* GEX + Kronos + entry bias hint */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span
                    style={{
                      fontSize: 10,
                      color: gexColor(sig.gex_regime ?? ''),
                      border: `1px solid ${gexColor(sig.gex_regime ?? '')}`,
                      borderRadius: 3,
                      padding: '0 4px',
                      letterSpacing: '0.06em',
                      flexShrink: 0,
                      lineHeight: '14px',
                    }}
                  >
                    GEX {sig.gex_regime ?? 'N/A'}
                  </span>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 3, flexShrink: 0 }}>
                    <span style={{ fontSize: 10, color: 'var(--text-dim)' }}>K</span>
                    <div
                      style={{
                        width: 7,
                        height: 7,
                        borderRadius: '50%',
                        background: 'var(--magenta)',
                        opacity: sig.kronos_bias != null
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
                      {sig.kronos_bias != null ? `${Math.round(sig.kronos_bias)}%` : '\u2014'}
                    </span>
                  </div>

                  {biasHint && (
                    <span
                      style={{
                        fontSize: 10,
                        color,
                        fontWeight: 600,
                        letterSpacing: '0.06em',
                        marginLeft: 'auto',
                        flexShrink: 0,
                        opacity: 0.85,
                      }}
                    >
                      {biasHint}
                    </span>
                  )}
                </div>

                {/* Category dots + full narrative */}
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 4 }}>
                  <span
                    style={{
                      fontSize: 10,
                      color: 'var(--text-dim)',
                      letterSpacing: '0.06em',
                      flexShrink: 0,
                    }}
                  >
                    CATS {(sig.category_count ?? 0)}/8
                  </span>
                  <div
                    style={{
                      display: 'flex',
                      gap: 3,
                      marginLeft: 2,
                      alignItems: 'center',
                      flexShrink: 0,
                      paddingTop: 2,
                    }}
                  >
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
                            transition: `background ${DURATION.fast}ms`, // 150ms dot color flick
                          }}
                        />
                      );
                    })}
                  </div>

                  {rawNarrative.length > 0 && (
                    <span
                      style={{
                        color: 'var(--text-dim)',
                        fontSize: 10,
                        marginLeft: 6,
                        flex: 1,
                        whiteSpace: 'normal',
                        lineHeight: 1.35,
                      }}
                    >
                      {rawNarrative}
                    </span>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Score mini-bar: 2px absolute at bottom, full row width */}
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: 2,
            background: 'var(--rule)',
          }}
        >
          <div
            style={{
              height: '100%',
              width: `${scoreBarPct}%`,
              background: color,
              opacity: 0.75,
              transition: `width ${DURATION.slow}ms ease`, // 500ms score bar update
            }}
          />
        </div>
      </motion.div>
    </div>
  );
}

'use client';
/**
 * SignalContext.tsx — Phase 11.3-r4
 *
 * Slide-in drawer panel showing deep breakdown for a clicked signal row.
 * - 400px wide, full height, overlays right side of signal feed column
 * - Slides in from right with spring (stiffness 220, damping 25)
 * - Content fades in with 100ms stagger after container settles
 * - Close: slide out + fade, 250ms
 */
import { useMemo } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'motion/react';
import type { SignalEvent } from '@/types/deep6';

// ---------------------------------------------------------------------------
// Tier color helpers (duplicated from row to keep this component standalone)
// ---------------------------------------------------------------------------

const TIER_COLOR: Record<string, string> = {
  TYPE_A: 'var(--lime)',
  TYPE_B: 'var(--amber)',
  TYPE_C: 'var(--cyan)',
  QUIET:  'var(--text-mute)',
};

function tierColor(tier: string): string {
  return TIER_COLOR[tier] ?? TIER_COLOR.QUIET;
}

function gexColor(regime: string): string {
  if (regime === 'POS_GAMMA') return 'var(--ask)';
  if (regime === 'NEG_GAMMA') return 'var(--bid)';
  return 'var(--text-mute)';
}

// ---------------------------------------------------------------------------
// Age formatting (duplicate — keeps component self-contained)
// ---------------------------------------------------------------------------

function formatAge(nowMs: number, signalTsMs: number): string {
  const diffMs = nowMs - signalTsMs;
  if (diffMs < 0) return '+0.0s';
  const diffS = diffMs / 1000;
  if (diffS < 10) return `+${diffS.toFixed(1)}s`;
  if (diffS < 60) return `+${Math.round(diffS)}s`;
  const diffM = diffS / 60;
  if (diffM < 60) return `+${Math.round(diffM)}m`;
  const diffH = diffM / 60;
  if (diffH < 24) return `+${Math.round(diffH)}h`;
  return `+${Math.round(diffH / 24)}d`;
}

// ---------------------------------------------------------------------------
// Timestamp formatting: 14:56:33 ET
// ---------------------------------------------------------------------------

function formatTimestamp(tsEpochSeconds: number): string {
  const d = new Date(tsEpochSeconds * 1000);
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'America/New_York',
  }) + ' ET';
}

// ---------------------------------------------------------------------------
// Derived narrative from signal data (narrative field not stored in SignalEvent)
// ---------------------------------------------------------------------------

function deriveNarrative(sig: SignalEvent): string {
  const cats = (sig.categories_firing ?? []).map((c) => c.toUpperCase());
  if (cats.length === 0) return 'NO SIGNAL';
  const dirStr = sig.direction === 1 ? '↑' : sig.direction === -1 ? '↓' : '—';
  return `${cats.slice(0, 3).join('+')} ${dirStr} @BAR ${sig.bar_index_in_session}`;
}

// ---------------------------------------------------------------------------
// Interpretation text templates
// ---------------------------------------------------------------------------

function getInterpretation(tier: string, direction: -1 | 0 | 1): string {
  if (tier === 'TYPE_A' && direction === 1) {
    return 'HIGH CONVICTION LONG — primary entry candidate. Confirm above POC, stop below VAL, target VAH.';
  }
  if (tier === 'TYPE_A' && direction === -1) {
    return 'HIGH CONVICTION SHORT — primary entry candidate. Confirm below POC, stop above VAH, target VAL.';
  }
  if (tier === 'TYPE_B' && direction === 1) {
    return 'MODERATE LONG — watch for confirmation from next bar. Scale in or wait for price to hold above signal bar.';
  }
  if (tier === 'TYPE_B' && direction === -1) {
    return 'MODERATE SHORT — watch for confirmation. Scale in or wait for price to hold below signal bar.';
  }
  if (tier === 'TYPE_C') {
    return 'LOW CONVICTION — context only. Do not enter unless paired with TYPE_A/B at same or nearby zone.';
  }
  return 'NEUTRAL — insufficient directional bias. Monitor for next signal.';
}

// ---------------------------------------------------------------------------
// 8-category pill grid
// ---------------------------------------------------------------------------

const ALL_CATEGORIES = ['ABS', 'EXH', 'IMB', 'DELTA', 'AUCT', 'VOL', 'TRAP', 'ML'] as const;

const CATEGORY_FULL: Record<string, string> = {
  ABS:   'ABSORPTION',
  EXH:   'EXHAUSTION',
  IMB:   'IMBALANCE',
  DELTA: 'DELTA',
  AUCT:  'AUCTION',
  VOL:   'VOLUME',
  TRAP:  'TRAP',
  ML:    'ML/KRONOS',
};

// ---------------------------------------------------------------------------
// Related signals (within ±5 bars of the selected signal)
// ---------------------------------------------------------------------------

interface RelatedProps {
  selected: SignalEvent;
  allSignals: SignalEvent[];
}

function RelatedSignals({ selected, allSignals }: RelatedProps) {
  const related = useMemo(() => {
    return allSignals
      .filter(
        (s) =>
          s.ts !== selected.ts &&
          Math.abs(s.bar_index_in_session - selected.bar_index_in_session) <= 5,
      )
      .slice(0, 5);
  }, [selected, allSignals]);

  if (related.length === 0) {
    return (
      <span style={{ color: 'var(--text-mute)', fontSize: 11, fontStyle: 'italic' }}>
        No related signals in window
      </span>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {related.map((s, i) => {
        const offset = s.bar_index_in_session - selected.bar_index_in_session;
        const offsetStr = offset >= 0 ? `+${offset}` : `${offset}`;
        const col = tierColor(s.tier);
        const cats = (s.categories_firing ?? []).join('+').toUpperCase();
        return (
          <div
            key={`${s.ts}-${i}`}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 11,
              color: 'var(--text-dim)',
            }}
          >
            <span style={{ color: 'var(--text-mute)', width: 20, flexShrink: 0 }}>
              {offsetStr}
            </span>
            <span
              style={{
                color: col,
                fontWeight: 600,
                letterSpacing: '0.06em',
                flexShrink: 0,
                fontSize: 10,
                border: `1px solid ${col}`,
                borderRadius: 2,
                padding: '0 3px',
              }}
            >
              {s.tier}
            </span>
            <span
              style={{
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: 11,
              }}
            >
              {cats || '—'}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section wrapper for consistent spacing
// ---------------------------------------------------------------------------

function Section({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        borderBottom: '1px solid var(--rule)',
        paddingBottom: 12,
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontSize: 10,
        color: 'var(--text-mute)',
        letterSpacing: '0.1em',
        marginBottom: 6,
        fontWeight: 600,
      }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SignalContext props
// ---------------------------------------------------------------------------

interface SignalContextProps {
  signal: SignalEvent | null;
  allSignals: SignalEvent[];
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function SignalContext({ signal, allSignals, onClose }: SignalContextProps) {
  const reduced = useReducedMotion();

  // Container spring: stiffness 220, damping 25
  const containerVariants = {
    hidden: { x: '100%', opacity: 0 },
    visible: { x: 0, opacity: 1 },
    exit: { x: '100%', opacity: 0 },
  };

  const containerTransition = reduced
    ? { duration: 0 }
    : {
        x: { type: 'spring' as const, stiffness: 220, damping: 25 },
        opacity: { duration: 0.2 },
      };

  const exitTransition = reduced
    ? { duration: 0 }
    : { duration: 0.25, ease: 'easeIn' as const };

  // Content stagger — fades in after container settles (~350ms)
  const contentVariants = {
    hidden: { opacity: 0, y: 4 },
    visible: { opacity: 1, y: 0 },
  };

  const contentTransition = (delayIndex: number) =>
    reduced
      ? { duration: 0 }
      : {
          duration: 0.2,
          delay: 0.35 + delayIndex * 0.1,
          ease: 'easeOut' as const,
        };

  const sig = signal;
  const tier = sig?.tier ?? 'QUIET';
  const color = tierColor(tier);
  const ageStr = sig ? formatAge(Date.now(), sig.ts * 1000) : '';
  const narrative = sig ? deriveNarrative(sig) : '';
  const interpretation = sig ? getInterpretation(tier, sig.direction as -1 | 0 | 1) : '';
  const firingSet = new Set((sig?.categories_firing ?? []).map((c) => c.toUpperCase()));
  const agreementPct = Math.min(100, Math.max(0, Math.round(sig?.engine_agreement ?? 0)));
  const kronosDir = (sig?.kronos_bias ?? 0) >= 0 ? 'LONG' : 'SHORT';
  const kronosPct = Math.abs(Math.round(sig?.kronos_bias ?? 0));

  return (
    <AnimatePresence mode="wait">
      {sig && (
        <motion.div
          key={`ctx-${sig.ts}-${sig.bar_index_in_session}`}
          variants={containerVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
          transition={
            // Use exit transition only during exit phase via AnimatePresence
            containerTransition
          }
          style={{
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            width: 400,
            background: 'var(--surface-2)',
            borderLeft: '1px solid var(--rule-bright)',
            display: 'flex',
            flexDirection: 'column',
            zIndex: 20,
            overflowY: 'auto',
            overflowX: 'hidden',
          }}
          className="scroll-terminal"
        >
          {/* ── Header strip ─────────────────────────────────────────── */}
          <motion.div
            variants={contentVariants}
            initial="hidden"
            animate="visible"
            transition={contentTransition(0)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '10px 12px 10px 14px',
              borderBottom: '1px solid var(--rule)',
              flexShrink: 0,
            }}
          >
            {/* Tier badge */}
            <span
              style={{
                color,
                fontWeight: 600,
                fontSize: 13,
                letterSpacing: '0.06em',
                border: `1px solid ${color}`,
                borderRadius: 3,
                padding: '2px 6px',
                flexShrink: 0,
              }}
            >
              [{tier}]
            </span>

            {/* Age */}
            <span
              style={{
                color: 'var(--text-dim)',
                fontSize: 11,
                fontVariantNumeric: 'tabular-nums',
                flex: 1,
              }}
            >
              {ageStr} ago
            </span>

            {/* Close button */}
            <button
              onClick={onClose}
              aria-label="Close signal context"
              style={{
                background: 'none',
                border: '1px solid var(--rule-bright)',
                borderRadius: 3,
                color: 'var(--text-dim)',
                cursor: 'pointer',
                fontSize: 16,
                lineHeight: 1,
                padding: '2px 7px',
                flexShrink: 0,
                transition: 'color 150ms ease, border-color 150ms ease',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--text)';
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--text-dim)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-dim)';
                (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--rule-bright)';
              }}
            >
              ×
            </button>
          </motion.div>

          {/* ── Body ─────────────────────────────────────────────────── */}
          <div style={{ flex: 1, padding: '14px 14px 0' }}>

            {/* ── Narrative headline ─────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(1)}
              style={{ marginBottom: 16 }}
            >
              <div
                style={{
                  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                  fontSize: 18,
                  fontWeight: 600,
                  color,
                  letterSpacing: '0.04em',
                  lineHeight: 1.2,
                  wordBreak: 'break-word',
                }}
              >
                {narrative}
              </div>
            </motion.div>

            {/* ── Score breakdown ──────────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(2)}
            >
              <Section>
                {/* Big score */}
                <div
                  style={{
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: 48,
                    fontWeight: 700,
                    color,
                    lineHeight: 1,
                    marginBottom: 8,
                  }}
                >
                  {Math.round(sig.total_score)}
                </div>

                {/* Engine agreement bar */}
                <div style={{ marginBottom: 6 }}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: 4,
                    }}
                  >
                    <span
                      style={{
                        color: 'var(--text-dim)',
                        fontSize: 10,
                        letterSpacing: '0.08em',
                      }}
                    >
                      ENGINE AGREEMENT
                    </span>
                    <span
                      style={{
                        color,
                        fontSize: 10,
                        fontVariantNumeric: 'tabular-nums',
                        fontWeight: 600,
                      }}
                    >
                      {agreementPct}%
                    </span>
                  </div>
                  <div
                    style={{
                      height: 5,
                      background: 'var(--rule-bright)',
                      borderRadius: 3,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        height: '100%',
                        width: `${agreementPct}%`,
                        background: color,
                        borderRadius: 3,
                        boxShadow: `0 0 6px color-mix(in oklch, ${color} 50%, transparent)`,
                      }}
                    />
                  </div>
                </div>

                {/* Category count */}
                <div
                  style={{
                    color: 'var(--text-dim)',
                    fontSize: 11,
                    letterSpacing: '0.06em',
                  }}
                >
                  CATEGORY COUNT:{' '}
                  <span style={{ color, fontWeight: 600 }}>
                    {sig.category_count ?? firingSet.size} / 8
                  </span>
                </div>
              </Section>
            </motion.div>

            {/* ── Categories firing ────────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(3)}
            >
              <Section>
                <SectionLabel>CATEGORIES</SectionLabel>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 5,
                  }}
                >
                  {ALL_CATEGORIES.map((cat) => {
                    const lit = firingSet.has(cat);
                    return (
                      <div
                        key={cat}
                        style={{
                          border: `1px solid ${lit ? color : 'var(--rule-bright)'}`,
                          borderRadius: 3,
                          padding: '4px 7px',
                          fontSize: 10,
                          letterSpacing: '0.07em',
                          color: lit ? color : 'var(--text-mute)',
                          opacity: lit ? 1 : 0.4,
                          fontWeight: lit ? 600 : 400,
                          boxShadow: lit
                            ? `0 0 5px color-mix(in oklch, ${color} 35%, transparent)`
                            : 'none',
                          transition: 'all 150ms ease',
                          userSelect: 'none',
                        }}
                      >
                        [{CATEGORY_FULL[cat] ?? cat}]
                      </div>
                    );
                  })}
                </div>
              </Section>
            </motion.div>

            {/* ── Context info ─────────────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(4)}
            >
              <Section>
                <SectionLabel>CONTEXT</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {/* GEX Regime */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        fontSize: 10,
                        color: 'var(--text-mute)',
                        letterSpacing: '0.06em',
                        width: 80,
                        flexShrink: 0,
                      }}
                    >
                      GEX REGIME
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: gexColor(sig.gex_regime ?? ''),
                        fontWeight: 600,
                        letterSpacing: '0.04em',
                      }}
                    >
                      {sig.gex_regime ?? 'N/A'}
                    </span>
                  </div>

                  {/* Kronos Bias */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        fontSize: 10,
                        color: 'var(--text-mute)',
                        letterSpacing: '0.06em',
                        width: 80,
                        flexShrink: 0,
                      }}
                    >
                      KRONOS BIAS
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: 'var(--magenta)',
                        fontWeight: 600,
                        letterSpacing: '0.04em',
                      }}
                    >
                      {kronosDir} {kronosPct}%
                    </span>
                  </div>

                  {/* Bar Index */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        fontSize: 10,
                        color: 'var(--text-mute)',
                        letterSpacing: '0.06em',
                        width: 80,
                        flexShrink: 0,
                      }}
                    >
                      BAR INDEX
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: 'var(--text-dim)',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {sig.bar_index_in_session}
                    </span>
                  </div>

                  {/* Timestamp */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        fontSize: 10,
                        color: 'var(--text-mute)',
                        letterSpacing: '0.06em',
                        width: 80,
                        flexShrink: 0,
                      }}
                    >
                      TIMESTAMP
                    </span>
                    <span
                      style={{
                        fontSize: 11,
                        color: 'var(--text-dim)',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {formatTimestamp(sig.ts)}
                    </span>
                  </div>
                </div>
              </Section>
            </motion.div>

            {/* ── Interpretation ───────────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(5)}
            >
              <Section>
                <SectionLabel>INTERPRETATION</SectionLabel>
                <div
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--rule)',
                    borderRadius: 4,
                    padding: '8px 10px',
                  }}
                >
                  <p
                    style={{
                      color: 'var(--text-dim)',
                      fontSize: 13,
                      fontStyle: 'italic',
                      margin: 0,
                      lineHeight: 1.5,
                    }}
                  >
                    {interpretation}
                  </p>
                </div>
              </Section>
            </motion.div>

            {/* ── Related signals ──────────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(6)}
            >
              <Section>
                <SectionLabel>RELATED SIGNALS (±5 BARS)</SectionLabel>
                <RelatedSignals selected={sig} allSignals={allSignals} />
              </Section>
            </motion.div>

            {/* ── Footer actions ───────────────────────────────────────── */}
            <motion.div
              variants={contentVariants}
              initial="hidden"
              animate="visible"
              transition={contentTransition(7)}
              style={{ paddingBottom: 16 }}
            >
              <SectionLabel>ACTIONS</SectionLabel>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {/* ENTER LONG — disabled, Phase 12 placeholder */}
                <button
                  disabled
                  title="Execution in Phase 12"
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--rule-bright)',
                    borderRadius: 3,
                    color: 'var(--text-mute)',
                    cursor: 'not-allowed',
                    fontSize: 11,
                    letterSpacing: '0.07em',
                    padding: '5px 10px',
                    opacity: 0.4,
                    fontWeight: 600,
                  }}
                >
                  ENTER LONG
                </button>

                {/* ENTER SHORT — disabled, Phase 12 placeholder */}
                <button
                  disabled
                  title="Execution in Phase 12"
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--rule-bright)',
                    borderRadius: 3,
                    color: 'var(--text-mute)',
                    cursor: 'not-allowed',
                    fontSize: 11,
                    letterSpacing: '0.07em',
                    padding: '5px 10px',
                    opacity: 0.4,
                    fontWeight: 600,
                  }}
                >
                  ENTER SHORT
                </button>

                {/* DISMISS */}
                <button
                  onClick={onClose}
                  style={{
                    background: 'var(--surface-1)',
                    border: '1px solid var(--rule-bright)',
                    borderRadius: 3,
                    color: 'var(--text-dim)',
                    cursor: 'pointer',
                    fontSize: 11,
                    letterSpacing: '0.07em',
                    padding: '5px 10px',
                    fontWeight: 600,
                    transition: 'border-color 150ms ease, color 150ms ease',
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text)';
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--text-dim)';
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-dim)';
                    (e.currentTarget as HTMLButtonElement).style.borderColor = 'var(--rule-bright)';
                  }}
                >
                  DISMISS
                </button>
              </div>
            </motion.div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

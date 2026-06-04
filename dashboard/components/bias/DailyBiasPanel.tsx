'use client';

/**
 * DailyBiasPanel — Institutional-grade PO3 bias display.
 *
 * Receives LiveBiasMessage via the existing /ws/live WebSocket.
 * Shows: direction badge, score gauge, component breakdown, MTF matrix,
 * trade setup card, AI reasoning, and macro blackout warning.
 */

import { useEffect, useRef, useState } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface BiasMessage {
  type: 'bias';
  direction: 'STRONG_BULL' | 'BULL' | 'NEUTRAL' | 'BEAR' | 'STRONG_BEAR';
  score: number;          // -100 to +100
  confidence: number;     // 0-1
  bull_pts: number;
  bear_pts: number;
  phase: string;
  judas_status: string;
  technical_score: number;
  news_score: number;
  ai_score: number;
  ai_reasoning: string;
  ai_key_triggers: string;
  macro_blackout: boolean;
  divergence_warning: string;
  ts: number;
}

interface TradeSetup {
  direction: 'LONG' | 'SHORT' | 'WAIT';
  entry_zone_high?: number;
  entry_zone_low?: number;
  stop_loss?: number;
  target_1?: number;
  target_2?: number;
  rrr?: number;
  entry_trigger?: string;
  session_window?: string;
}

// ── Color map ─────────────────────────────────────────────────────────────────

const DIR_COLOR: Record<string, string> = {
  STRONG_BULL: '#00e5a0',
  BULL: '#00c97a',
  NEUTRAL: '#9ca3af',
  BEAR: '#ff6b6b',
  STRONG_BEAR: '#ff3355',
};

const DIR_LABEL: Record<string, string> = {
  STRONG_BULL: '▲▲ STRONG BULL',
  BULL: '▲ BULL',
  NEUTRAL: '— NEUTRAL',
  BEAR: '▼ BEAR',
  STRONG_BEAR: '▼▼ STRONG BEAR',
};

const PHASE_COLOR: Record<string, string> = {
  ACCUMULATION: '#4f8ef7',
  MANIPULATION: '#f7a74f',
  DISTRIBUTION: '#00c97a',
  BETWEEN: '#6b7280',
};

const JUDAS_COLOR: Record<string, string> = {
  BULL_CONFIRMED: '#00e5a0',
  BEAR_CONFIRMED: '#ff3355',
  SWEPT_LO: '#f7a74f',
  SWEPT_HI: '#f7a74f',
  NONE: '#6b7280',
};

// ── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ value, label, color }: { value: number; label: string; color: string }) {
  const pct = Math.abs(value) / 100;
  const isPositive = value >= 0;
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#9ca3af', marginBottom: 2 }}>
        <span>{label}</span>
        <span style={{ color }}>{value > 0 ? '+' : ''}{value.toFixed(0)}</span>
      </div>
      <div style={{ background: '#1e2535', borderRadius: 3, height: 5, overflow: 'hidden' }}>
        <div style={{
          height: '100%',
          width: `${pct * 100}%`,
          background: color,
          borderRadius: 3,
          marginLeft: isPositive ? '50%' : `${50 - pct * 50}%`,
          transition: 'width 0.4s ease',
        }} />
      </div>
    </div>
  );
}

// ── Confidence arc gauge ───────────────────────────────────────────────────────

function ConfidenceGauge({ confidence, direction }: { confidence: number; direction: string }) {
  const pct = Math.round(confidence * 100);
  const color = DIR_COLOR[direction] ?? '#9ca3af';
  const radius = 32;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference * (1 - confidence * 0.75); // 75% arc

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={90} height={60} viewBox="0 0 90 60">
        {/* Background arc */}
        <circle
          cx={45} cy={50} r={radius}
          fill="none" stroke="#1e2535" strokeWidth={8}
          strokeDasharray={`${circumference * 0.75} ${circumference}`}
          strokeDashoffset={0}
          transform="rotate(-135 45 50)"
        />
        {/* Score arc */}
        <circle
          cx={45} cy={50} r={radius}
          fill="none" stroke={color} strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={`${circumference * 0.75} ${circumference}`}
          strokeDashoffset={dashOffset}
          transform="rotate(-135 45 50)"
          style={{ transition: 'stroke-dashoffset 0.6s ease' }}
        />
        <text x={45} y={48} textAnchor="middle" fill={color} fontSize={14} fontWeight="bold">
          {pct}%
        </text>
      </svg>
      <span style={{ fontSize: 10, color: '#6b7280', letterSpacing: '0.05em' }}>CONFIDENCE</span>
    </div>
  );
}

// ── Score dots for PO3 pts ────────────────────────────────────────────────────

function ScoreDots({ pts, color, max = 6 }: { pts: number; color: string; max?: number }) {
  return (
    <div style={{ display: 'flex', gap: 3 }}>
      {Array.from({ length: max }).map((_, i) => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: 2,
          background: i < pts ? color : '#1e2535',
          transition: 'background 0.3s',
        }} />
      ))}
    </div>
  );
}

// ── Main Panel ────────────────────────────────────────────────────────────────

export function DailyBiasPanel() {
  const [bias, setBias] = useState<BiasMessage | null>(null);
  const [connected, setConnected] = useState(false);
  const [age, setAge] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const ws = new WebSocket(
      typeof window !== 'undefined'
        ? `ws://${window.location.hostname}:8765/ws/live`
        : 'ws://localhost:8765/ws/live'
    );
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'bias') {
          setBias(msg as BiasMessage);
          setAge(0);
        }
      } catch {
        // ignore non-JSON
      }
    };

    // Age counter
    timerRef.current = setInterval(() => setAge((a) => a + 1), 1000);

    return () => {
      ws.close();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  if (!bias) {
    return (
      <div style={panelStyle}>
        <div style={{ color: '#6b7280', textAlign: 'center', padding: '32px 0', fontSize: 13 }}>
          {connected ? '⏳ Waiting for bias data…' : '⚡ Connecting to bias engine…'}
        </div>
      </div>
    );
  }

  const dirColor = DIR_COLOR[bias.direction] ?? '#9ca3af';
  const phaseColor = PHASE_COLOR[bias.phase] ?? '#6b7280';
  const judasColor = JUDAS_COLOR[bias.judas_status] ?? '#6b7280';
  const isBlackout = bias.macro_blackout;

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 10, color: '#4f8ef7', letterSpacing: '0.1em', fontWeight: 700 }}>
            DEEP6 DAILY BIAS
          </span>
          <span style={{
            fontSize: 9, padding: '1px 6px', borderRadius: 3,
            background: connected ? '#0a2a1a' : '#2a1010',
            color: connected ? '#00c97a' : '#ff6b6b',
            border: `1px solid ${connected ? '#00c97a33' : '#ff6b6b33'}`,
          }}>
            {connected ? '● LIVE' : '○ OFF'}
          </span>
        </div>
        <span style={{ fontSize: 10, color: '#4b5563' }}>
          {age > 0 ? `${age}s ago` : 'just now'}
          {age > 120 && <span style={{ color: '#f7a74f' }}> ⚠ stale</span>}
        </span>
      </div>

      {/* Macro blackout banner */}
      {isBlackout && (
        <div style={{
          background: '#2a1500', border: '1px solid #f7a74f66',
          borderRadius: 6, padding: '8px 12px', marginBottom: 12,
          fontSize: 12, color: '#f7a74f',
        }}>
          ⚠ HIGH-IMPACT EVENT ACTIVE — Bias paused. No new entries.
        </div>
      )}

      {/* Direction + Gauge row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div>
          <div style={{
            fontSize: 20, fontWeight: 900, color: dirColor,
            letterSpacing: '0.02em', lineHeight: 1.1,
            filter: `drop-shadow(0 0 8px ${dirColor}66)`,
          }}>
            {DIR_LABEL[bias.direction]}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: '#6b7280' }}>
            Score: <span style={{ color: dirColor, fontWeight: 700 }}>
              {bias.score > 0 ? '+' : ''}{bias.score.toFixed(1)}
            </span>
          </div>
        </div>
        <ConfidenceGauge confidence={bias.confidence} direction={bias.direction} />
      </div>

      {/* PO3 pts */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 4 }}>BULL {bias.bull_pts}/6</div>
          <ScoreDots pts={bias.bull_pts} color="#00c97a" />
        </div>
        <div>
          <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 4 }}>BEAR {bias.bear_pts}/6</div>
          <ScoreDots pts={bias.bear_pts} color="#ff6b6b" />
        </div>
      </div>

      {/* Phase + Judas row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
        <Chip label={bias.phase} color={phaseColor} />
        <Chip
          label={bias.judas_status === 'NONE' ? 'No Sweep' : bias.judas_status.replace('_', ' ')}
          color={judasColor}
        />
      </div>

      {/* Score breakdown */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 6, letterSpacing: '0.05em' }}>
          SIGNAL BREAKDOWN
        </div>
        <ScoreBar value={bias.technical_score} label="Technical (PO3)" color="#4f8ef7" />
        <ScoreBar value={bias.news_score}      label="News / Macro"    color="#a78bfa" />
        <ScoreBar value={bias.ai_score}        label="AI Synthesis"    color="#f7a74f" />
      </div>

      {/* Divergence warning */}
      {bias.divergence_warning && (
        <div style={warningStyle}>
          ⚡ {bias.divergence_warning}
        </div>
      )}

      {/* AI reasoning */}
      {bias.ai_reasoning && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 5, letterSpacing: '0.05em' }}>
            AI REASONING
          </div>
          <div style={{ fontSize: 12, color: '#c8d0e0', lineHeight: 1.5 }}>
            {bias.ai_reasoning}
          </div>
        </div>
      )}

      {/* Key triggers */}
      {bias.ai_key_triggers && (
        <div style={{
          background: '#0e1a2a', borderLeft: `3px solid ${dirColor}`,
          borderRadius: 4, padding: '8px 10px', fontSize: 11,
          color: '#9ca3af', lineHeight: 1.5,
        }}>
          <span style={{ color: '#6b7280', fontWeight: 700 }}>FLIP: </span>
          {bias.ai_key_triggers}
        </div>
      )}
    </div>
  );
}

// ── Chip component ────────────────────────────────────────────────────────────

function Chip({ label, color }: { label: string; color: string }) {
  return (
    <span style={{
      fontSize: 10, padding: '3px 8px', borderRadius: 4,
      background: `${color}18`, border: `1px solid ${color}44`,
      color, fontWeight: 700, letterSpacing: '0.04em',
      whiteSpace: 'nowrap',
    }}>
      {label}
    </span>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const panelStyle: React.CSSProperties = {
  background: '#0d1117',
  border: '1px solid #1e2535',
  borderRadius: 8,
  padding: 16,
  width: '100%',
  fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
};

const warningStyle: React.CSSProperties = {
  background: '#1a1500',
  border: '1px solid #f7a74f44',
  borderRadius: 5,
  padding: '7px 10px',
  fontSize: 11,
  color: '#f7a74f',
  marginBottom: 12,
};

'use client';
import { useTradingStore } from '@/store/tradingStore';
import { KronosBiasBar } from './KronosBiasBar';

// ── Category config ───────────────────────────────────────────────────────────
// Per UI-SPEC §Score Widget §Category bars: 8 categories, each 5 cells (20% per cell).

const CATEGORIES = [
  { label: 'Absorption',  color: '#a3e635' },
  { label: 'Exhaustion',  color: '#a3e635' },
  { label: 'Imbalance',   color: '#38bdf8' },
  { label: 'Delta',       color: '#facc15' },
  { label: 'Auction',     color: '#38bdf8' },
  { label: 'Volume',      color: '#facc15' },
  { label: 'Trap',        color: '#a3e635' },
  { label: 'ML/Context',  color: '#a3e635' },
] as const;

const CELLS_PER_CAT = 5;

// ── Sub-component: category bar row ──────────────────────────────────────────

function CategoryBar({ label, score, color }: { label: string; score: number; color: string }) {
  const litCount = Math.min(CELLS_PER_CAT, Math.ceil((score / 100) * CELLS_PER_CAT));

  return (
    <div className="flex items-center gap-2 h-5">
      <span className="text-[12px] text-muted" style={{ width: '80px', flexShrink: 0 }}>
        {label}
      </span>
      <div className="flex items-center gap-1">
        {Array.from({ length: CELLS_PER_CAT }, (_, i) => (
          <div
            key={i}
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '2px',
              background: i < litCount ? color : 'var(--border-subtle)',
              flexShrink: 0,
            }}
          />
        ))}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function ScoreWidget() {
  const score = useTradingStore((s) => s.score);

  const { totalScore, kronosDirection, kronosBias, gexRegime, categoryScores } = score;

  // Score color per UI-SPEC
  const scoreColor =
    totalScore >= 80 ? 'text-type-a' :
    totalScore >= 50 ? 'text-type-b' :
    'text-muted';

  const barColor =
    totalScore >= 80 ? '#a3e635' :
    totalScore >= 50 ? '#facc15' :
    '#6b7280';

  const gexColor =
    gexRegime === 'POS_GAMMA' ? 'text-ask' :
    gexRegime === 'NEG_GAMMA' ? 'text-bid' :
    'text-muted';

  return (
    <div className="w-60 bg-bg-surface p-4 flex flex-col gap-3 border-l border-border-subtle overflow-y-auto">
      {/* Label */}
      <p className="text-[13px] font-semibold text-muted tracking-wide uppercase">
        Confluence Score
      </p>

      {/* PRIMARY FOCAL POINT: 28px score number — unique in the entire app */}
      <div className="flex flex-col gap-2">
        <span className={`font-mono text-[28px] font-semibold leading-none ${scoreColor}`}>
          {Math.round(totalScore)}
        </span>

        {/* Progress bar */}
        <div
          className="rounded-full overflow-hidden"
          style={{ height: '8px', background: 'var(--border-subtle)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${Math.min(100, totalScore)}%`,
              background: barColor,
            }}
          />
        </div>
      </div>

      {/* Category bars */}
      <div className="flex flex-col gap-0.5">
        <p className="text-[12px] text-muted font-semibold mb-1">Categories</p>
        {CATEGORIES.map(({ label, color }) => (
          <CategoryBar
            key={label}
            label={label}
            score={categoryScores[label] ?? 0}
            color={color}
          />
        ))}
      </div>

      {/* Kronos E10 bias */}
      <div className="flex flex-col gap-1">
        <p className="text-[12px] text-muted font-semibold">Kronos E10</p>
        <KronosBiasBar
          direction={kronosDirection as 'LONG' | 'SHORT' | 'NEUTRAL'}
          bias={kronosBias}
        />
      </div>

      {/* GEX Regime */}
      <div className="flex flex-col gap-1">
        <p className="text-[12px] text-muted font-semibold">GEX Regime</p>
        <span className={`text-[13px] font-semibold ${gexColor}`}>
          {gexRegime || 'NEUTRAL'}
        </span>
      </div>
    </div>
  );
}

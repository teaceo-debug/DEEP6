import { fmtPrice } from './format'

export interface VerdictPanelProps {
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  confidence: number
  grade: string
  regime_name: string
  nq_price?: number
  nq_change?: number
}

const DIR_MAP = {
  BULLISH: {
    arrows: '\u25B2\u25B2\u25B2',
    color: 'var(--terminal-green)',
    glow: 'var(--terminal-glow)',
  },
  BEARISH: {
    arrows: '\u25BC\u25BC\u25BC',
    color: 'var(--terminal-red)',
    glow: 'var(--terminal-glow-red)',
  },
  NEUTRAL: {
    arrows: '\u2500\u2500\u2500',
    color: 'var(--terminal-dim)',
    glow: 'none',
  },
} as const

function gradeColor(g: string): string {
  if (g.startsWith('A')) return 'var(--terminal-green)'
  if (g === 'F') return 'var(--terminal-red)'
  return 'var(--terminal-amber)'
}

export function VerdictPanel({
  direction, confidence, grade, regime_name, nq_price, nq_change,
}: VerdictPanelProps) {
  const dir = DIR_MAP[direction]
  const filled = Math.round(confidence / 10)
  const deltaClr = (nq_change ?? 0) >= 0 ? 'var(--terminal-green)' : 'var(--terminal-red)'
  const deltaGlow = (nq_change ?? 0) >= 0 ? 'var(--terminal-glow)' : 'var(--terminal-glow-red)'
  const pct = nq_price && nq_change != null
    ? ((nq_change / nq_price) * 100).toFixed(2)
    : null

  return (
    <div className="panel-section" data-testid="verdict-panel">
      <div className="panel-row">
        <span style={{ color: dir.color, textShadow: dir.glow, fontWeight: 700 }}>
          {dir.arrows} {direction} {dir.arrows}
        </span>
        {'                   '}
        <span className="text-dim">{'CONFIDENCE: '}</span>
        <span style={{ color: dir.color, textShadow: dir.glow }}>
          {'\u2588'.repeat(filled)}
        </span>
        <span className="text-dark">{'\u2591'.repeat(10 - filled)}</span>
        {' '}<span style={{ color: dir.color, textShadow: dir.glow }}>{confidence}%</span>
        {'    '}
        <span className="text-dim">{'GRADE: '}</span>
        <span style={{ color: gradeColor(grade) }}>{grade}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'Regime: '}</span>
        <span className="text-bright">{regime_name.toUpperCase()}</span>
        {'           '}
        <span className="text-dim">{'NQ: '}</span>
        <span style={{ color: deltaClr, textShadow: deltaGlow }}>
          {fmtPrice(nq_price)}
        </span>
        {nq_change != null && (
          <span style={{ color: deltaClr, textShadow: deltaGlow }}>
            {'  \u0394 '}{nq_change >= 0 ? '+' : ''}{nq_change.toFixed(2)}
            {pct != null && ` (${nq_change >= 0 ? '+' : ''}${pct}%)`}
          </span>
        )}
      </div>
    </div>
  )
}

'use client'

interface DarkPoolPanelProps {
  levels_nq: number[]
  net_premium: number | null
  institutional_bias: string
}

export function DarkPoolPanel({ levels_nq, net_premium, institutional_bias }: DarkPoolPanelProps) {
  const levelsStr = levels_nq.slice(0, 4).map(l => l.toLocaleString('en-US', { maximumFractionDigits: 0 })).join('  ')
  const premiumStr = net_premium ? `${net_premium > 0 ? '+' : ''}${(net_premium / 1_000_000).toFixed(1)}M` : 'N/A'
  const biasColor = institutional_bias === 'bullish' ? 'var(--terminal-green)' :
    institutional_bias === 'bearish' ? 'var(--terminal-red)' :
      'var(--terminal-dim)'

  return (
    <div data-testid="dark-pool-panel" style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', lineHeight: '1.4' }}>
      <div style={{ color: 'var(--terminal-dim)' }}>╠══════════════════════════════════════════════════════════════════════════════════════════════╣</div>
      <div>
        ║ <span style={{ color: 'var(--terminal-dim)' }}>DARK POOL:</span>{' '}
        <span data-testid="dp-levels" style={{ color: 'var(--terminal-green)' }}>{levelsStr || 'N/A'}</span>
        {'  '}│{'  '}
        <span style={{ color: 'var(--terminal-dim)' }}>BIAS:</span>{' '}
        <span data-testid="dp-bias" style={{ color: biasColor }}>{institutional_bias.toUpperCase()}</span>
        {'  '}
        <span data-testid="dp-premium" style={{ color: 'var(--terminal-dim)' }}>{premiumStr}</span>
        {'  '}║
      </div>
    </div>
  )
}

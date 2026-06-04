export interface FlowPanelProps {
  direction: string
  intensity: number
  sweep_count: number
  block_count: number
  z_score: number
}

function intensityLabel(n: number): string {
  if (n >= 0.8) return 'EXTREME'
  if (n >= 0.6) return 'HIGH'
  if (n >= 0.4) return 'MODERATE'
  if (n >= 0.2) return 'LOW'
  return 'MINIMAL'
}

function intensityColor(n: number): string {
  if (n >= 0.8) return 'var(--terminal-red)'
  if (n >= 0.6) return 'var(--terminal-green)'
  return 'var(--terminal-dim)'
}

export function FlowPanel({
  direction, intensity, sweep_count, block_count, z_score,
}: FlowPanelProps) {
  const isBull = direction.toUpperCase().includes('BULL')
  const arrow = isBull ? '\u25B2' : '\u25BC'
  const dirColor = isBull ? 'var(--terminal-green)' : 'var(--terminal-red)'
  const dirGlow = isBull ? 'var(--terminal-glow)' : 'var(--terminal-glow-red)'
  const filled = Math.round(intensity * 10)
  const zSign = z_score >= 0 ? '+' : ''

  return (
    <div className="panel-section" data-testid="flow-panel">
      <div className="panel-row">
        <span className="text-dim">{'FLOW: '}</span>
        <span style={{ color: dirColor, textShadow: dirGlow, fontWeight: 700 }}>
          {arrow} {direction.toUpperCase()}
        </span>
        {'  '}
        <span className="text-dim">{'z:'}</span>
        <span style={{ color: dirColor, textShadow: dirGlow }}>
          {zSign}{z_score.toFixed(1)}
        </span>
        {'  '}
        <span className="text-dim">{'INT: '}</span>
        <span style={{ color: intensityColor(intensity) }}>
          {'\u2588'.repeat(filled)}
        </span>
        <span className="text-dark">{'\u2591'.repeat(10 - filled)}</span>
        {' '}
        <span style={{ color: intensityColor(intensity) }}>
          {intensityLabel(intensity)}
        </span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'SWEEPS: '}</span>
        <span className="text-bright">{sweep_count}</span>
        {'  '}
        <span className="text-dim">{'BLOCKS: '}</span>
        <span className="text-bright">{block_count}</span>
      </div>
    </div>
  )
}

export interface Deep6BiasPanelProps {
  bias_score?: number
  bias_label?: string
  confidence?: number
  connected: boolean
}

export function Deep6BiasPanel({
  bias_score, bias_label, confidence, connected,
}: Deep6BiasPanelProps) {
  const standalone = bias_label === 'STANDALONE'
  const scoreClr = bias_score == null
    ? 'var(--terminal-dim)'
    : bias_score >= 0
    ? 'var(--terminal-green)'
    : 'var(--terminal-red)'
  const scoreGlow = bias_score == null
    ? 'none'
    : bias_score >= 0
    ? 'var(--terminal-glow)'
    : 'var(--terminal-glow-red)'
  const connClr = standalone
    ? 'var(--terminal-dim)'
    : connected
    ? 'var(--terminal-green)'
    : 'var(--terminal-red)'
  const connText = standalone ? 'STANDALONE' : connected ? 'CONNECTED' : 'N/A'
  const scoreSign = bias_score != null && bias_score >= 0 ? '+' : ''

  return (
    <div className="panel-section" data-testid="deep6-bias-panel">
      <div className="panel-row">
        <span className="text-dim">{'DEEP6: '}</span>
        <span className="text-dim">{'bias_score='}</span>
        <span style={{ color: scoreClr, textShadow: scoreGlow }}>
          {bias_score != null ? `${scoreSign}${bias_score}` : standalone ? 'N/A' : '---'}
        </span>
        {'  '}
        <span className="text-dim">{'bias_label='}</span>
        <span style={{ color: scoreClr, textShadow: scoreGlow }}>
          {bias_label ?? '---'}
        </span>
        {'  '}
        <span className="text-dim">{'confidence='}</span>
        <span className="text-bright">
          {confidence != null ? confidence.toFixed(2) : standalone ? 'N/A' : '---'}
        </span>
        {'  '}
        <span style={{ color: connClr }}>{'['}{connText}{']'}</span>
      </div>
    </div>
  )
}

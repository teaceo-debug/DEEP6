export interface StatusFooterProps {
  sources: Record<string, { status: string }>
  cost_today_usd: number
  refresh_countdown: number
}

function dotChar(status: string): string {
  return status === 'ok' || status === 'stale' ? '\u25CF' : '\u25CB'
}

function dotClass(status: string): string {
  if (status === 'ok') return 'text-bright'
  if (status === 'stale') return 'text-amber'
  return 'text-dark'
}

export function StatusFooter({
  sources, cost_today_usd, refresh_countdown,
}: StatusFooterProps) {
  const sourceEntries = Object.entries(sources)

  return (
    <div className="panel-section" data-testid="status-footer">
      <div className="panel-row">
        {sourceEntries.map(([name, { status }], i) => (
          <span key={name}>
            <span className="text-dim">{name}:</span>
            <span className={dotClass(status)}>{dotChar(status)}</span>
            {i < sourceEntries.length - 1 ? ' ' : ''}
          </span>
        ))}
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-bright">${cost_today_usd.toFixed(2)}</span>
        <span className="text-dim">{' today'}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-bright">{'\u27F3 '}{refresh_countdown}s</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">
          {new Date().toLocaleTimeString('en-US', {
            hour12: false,
            timeZone: 'America/New_York',
          })}{' ET'}
        </span>
      </div>
    </div>
  )
}

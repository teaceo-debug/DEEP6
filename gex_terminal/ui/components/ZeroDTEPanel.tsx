export interface ZeroDTEPanelProps {
  gex_pct_of_total?: number
  pin_risk: string
  gamma_acceleration?: number
}

function pinColor(risk: string): string {
  const r = risk.toUpperCase()
  if (r === 'HIGH') return 'var(--terminal-red)'
  if (r === 'MODERATE' || r === 'MEDIUM') return 'var(--terminal-amber)'
  return 'var(--terminal-green)'
}

function pctColor(pct: number | undefined | null): string {
  if (pct == null) return 'var(--terminal-dim)'
  if (pct > 35) return 'var(--terminal-amber)'
  return 'var(--terminal-bright)'
}

export function ZeroDTEPanel({
  gex_pct_of_total, pin_risk, gamma_acceleration,
}: ZeroDTEPanelProps) {
  const accelSign = (gamma_acceleration ?? 0) >= 0 ? '+' : ''
  const accelClr = (gamma_acceleration ?? 0) >= 0
    ? 'var(--terminal-green)'
    : 'var(--terminal-red)'

  return (
    <div className="panel-section" data-testid="zero-dte-panel">
      <div className="panel-row">
        <span className="text-dim">{'0DTE: '}</span>
        <span style={{ color: pctColor(gex_pct_of_total) }}>
          {gex_pct_of_total != null ? `${gex_pct_of_total}%` : '---'}
        </span>
        <span className="text-dim">{' of total GEX'}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'PIN RISK: '}</span>
        <span style={{ color: pinColor(pin_risk) }}>{pin_risk.toUpperCase()}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'GAMMA ACCEL: '}</span>
        <span style={{ color: accelClr }}>
          {gamma_acceleration != null ? `${accelSign}${gamma_acceleration.toFixed(2)}` : '---'}
        </span>
      </div>
    </div>
  )
}

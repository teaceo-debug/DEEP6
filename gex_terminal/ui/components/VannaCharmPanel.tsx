import { fmtGex } from './format'

export interface VannaCharmPanelProps {
  vanna_exposure?: number
  charm_exposure?: number
  net_hedge_direction: string
}

export function VannaCharmPanel({
  vanna_exposure, charm_exposure, net_hedge_direction,
}: VannaCharmPanelProps) {
  const vannaPositive = (vanna_exposure ?? 0) >= 0
  const vannaSuffix = vannaPositive ? '(tailwind \u25B2)' : '(headwind \u25BC)'
  const vannaClr = vannaPositive ? 'var(--terminal-green)' : 'var(--terminal-red)'
  const vannaGlow = vannaPositive ? 'var(--terminal-glow)' : 'var(--terminal-glow-red)'

  const charmPositive = (charm_exposure ?? 0) >= 0
  const charmSuffix = charmPositive ? '(boost \u25B2)' : '(drag \u25BC)'
  const charmClr = charmPositive ? 'var(--terminal-green)' : 'var(--terminal-amber)'
  const charmGlow = charmPositive ? 'var(--terminal-glow)' : 'var(--terminal-glow-amber)'

  const hedgeClr = net_hedge_direction.toUpperCase() === 'TAILWIND'
    ? 'var(--terminal-green)'
    : net_hedge_direction.toUpperCase() === 'HEADWIND'
    ? 'var(--terminal-red)'
    : 'var(--terminal-amber)'

  return (
    <div className="panel-section" data-testid="vanna-charm-panel">
      <div className="panel-row">
        <span className="text-dim">{'VANNA: '}</span>
        <span style={{ color: vannaClr, textShadow: vannaGlow }}>
          {fmtGex(vanna_exposure, true)}
        </span>
        {' '}
        <span style={{ color: vannaClr, textShadow: vannaGlow }}>{vannaSuffix}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'CHARM: '}</span>
        <span style={{ color: charmClr, textShadow: charmGlow }}>
          {fmtGex(charm_exposure, true)}
        </span>
        {' '}
        <span style={{ color: charmClr, textShadow: charmGlow }}>{charmSuffix}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'NET HEDGE: '}</span>
        <span style={{ color: hedgeClr }}>{net_hedge_direction.toUpperCase()}</span>
      </div>
    </div>
  )
}

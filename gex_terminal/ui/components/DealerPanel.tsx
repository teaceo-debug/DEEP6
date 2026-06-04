import { fmtGex, signColor, signGlow } from './format'

export interface DealerPanelProps {
  net_gex?: number
  net_dex?: number
  net_vex?: number
  net_chex?: number
  regime: string
  hedge_direction: string
}

function gexLabel(n: number | undefined | null): string {
  if (n == null) return '---'
  return n >= 0 ? 'positive' : 'negative'
}

function dexLabel(n: number | undefined | null): string {
  if (n == null) return '---'
  return n >= 0 ? 'long delta' : 'short delta'
}

function vexLabel(n: number | undefined | null): string {
  if (n == null) return '---'
  return n >= 0 ? 'long vol' : 'short vol'
}

function chexLabel(n: number | undefined | null): string {
  if (n == null) return '---'
  return n >= 0 ? 'time boost' : 'time drag'
}

export function DealerPanel({
  net_gex, net_dex, net_vex, net_chex, regime, hedge_direction,
}: DealerPanelProps) {
  return (
    <div className="panel-section" data-testid="dealer-panel">
      <div className="panel-row">
        <span className="text-dim text-bold">{'DEALER POSITIONING'}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'GEX: '}</span>
        <span style={{ color: signColor(net_gex), textShadow: signGlow(net_gex) }}>
          {fmtGex(net_gex)}
        </span>
        <span className="text-dim">{` (${gexLabel(net_gex)})`}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'DEX: '}</span>
        <span style={{ color: signColor(net_dex), textShadow: signGlow(net_dex) }}>
          {fmtGex(net_dex)}
        </span>
        <span className="text-dim">{` (${dexLabel(net_dex)})`}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'REGIME: '}</span>
        <span className="text-bright">{regime.toUpperCase()}</span>
      </div>
      <div className="panel-row">
        <span className="text-dim">{'VEX: '}</span>
        <span style={{ color: signColor(net_vex), textShadow: signGlow(net_vex) }}>
          {fmtGex(net_vex)}
        </span>
        <span className="text-dim">{` (${vexLabel(net_vex)})`}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'CHEX: '}</span>
        <span style={{ color: signColor(net_chex), textShadow: signGlow(net_chex) }}>
          {fmtGex(net_chex)}
        </span>
        <span className="text-dim">{` (${chexLabel(net_chex)})`}</span>
        <span className="text-dark">{' \u2502 '}</span>
        <span className="text-dim">{'HEDGE: '}</span>
        <span className="text-bright">{hedge_direction.toUpperCase()}</span>
      </div>
    </div>
  )
}

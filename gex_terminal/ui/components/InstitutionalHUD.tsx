'use client'

import { fmtGex, fmtPrice } from './format'

interface InstitutionalHUDProps {
  inst_flow_direction: string
  dp_session: {
    print_count: number
    net_premium: number
    bias: string
  }
  market_tide: {
    direction: string
    call_premium: number
    put_premium: number
  }
  signal_grid: {
    rows: { label: string; state: string; score: number }[]
    confluence_buy: number
    confluence_sell: number
    total_signals: number
  }
  dp_levels: {
    price_nq: number
    total_premium: number
    print_count: number
    level_type: string
    multiplier: number
  }[]
  swing_equilibrium: {
    price_nq: number
    period_days: number
  }
  dp_bias: string
}

function stateColor(state: string): string {
  switch (state.toUpperCase()) {
    case 'BUY': return 'var(--terminal-green)'
    case 'SELL': return 'var(--terminal-red)'
    case 'HOLD':
    case 'MIXED': return 'var(--terminal-amber)'
    default: return 'var(--terminal-dark)'
  }
}

function stateGlow(state: string): string {
  switch (state.toUpperCase()) {
    case 'BUY': return 'var(--terminal-glow)'
    case 'SELL': return 'var(--terminal-glow-red)'
    case 'HOLD':
    case 'MIXED': return 'var(--terminal-glow-amber)'
    default: return 'none'
  }
}

function biasColor(bias: string): string {
  const b = bias.toUpperCase()
  if (b.includes('BULL') || b.includes('BUY') || b.includes('ACCUM')) return 'var(--terminal-green)'
  if (b.includes('BEAR') || b.includes('SELL') || b.includes('DISTRIB')) return 'var(--terminal-red)'
  return 'var(--terminal-amber)'
}

function biasGlow(bias: string): string {
  const b = bias.toUpperCase()
  if (b.includes('BULL') || b.includes('BUY') || b.includes('ACCUM')) return 'var(--terminal-glow)'
  if (b.includes('BEAR') || b.includes('SELL') || b.includes('DISTRIB')) return 'var(--terminal-glow-red)'
  return 'var(--terminal-glow-amber)'
}

function levelColor(type: string): string {
  switch (type.toUpperCase()) {
    case 'SUPPORT': return 'var(--terminal-green)'
    case 'RESIST': return 'var(--terminal-red)'
    default: return 'var(--terminal-dim)'
  }
}

function levelGlow(type: string): string {
  switch (type.toUpperCase()) {
    case 'SUPPORT': return 'var(--terminal-glow)'
    case 'RESIST': return 'var(--terminal-glow-red)'
    default: return 'none'
  }
}

function fmtDollar(n: number): string {
  const abs = Math.abs(n)
  if (abs >= 1e9) return `$${(abs / 1e9).toFixed(1)}B`
  if (abs >= 1e6) return `$${Math.round(abs / 1e6)}M`
  if (abs >= 1e3) return `$${Math.round(abs / 1e3)}K`
  return `$${abs.toFixed(0)}`
}

export function InstitutionalHUD({
  inst_flow_direction,
  dp_session,
  market_tide,
  signal_grid,
  dp_levels,
  swing_equilibrium,
  dp_bias,
}: InstitutionalHUDProps) {
  return (
    <div data-testid="institutional-hud" style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', lineHeight: '1.4' }}>
      {/* Section header */}
      <div style={{ color: 'var(--terminal-dim)' }}>
        {'╠═══════════════════════ INSTITUTIONAL DARK POOL ═══════════════════════════════════════════╣'}
      </div>

      {/* Inst Flow + DP Today + Tide — one dense row */}
      <div className="panel-row">
        <span className="text-dim">{'INST FLOW: '}</span>
        <span data-testid="inst-flow" style={{ color: biasColor(inst_flow_direction), textShadow: biasGlow(inst_flow_direction) }}>
          {inst_flow_direction.toUpperCase()}
        </span>
        <span className="text-dark">{' │ '}</span>
        <span className="text-dim">{'DP TODAY: '}</span>
        <span className="text-bright" data-testid="dp-prints">{dp_session.print_count}</span>
        <span className="text-dim">{' prints'}</span>
        <span className="text-dark">{' │ '}</span>
        <span data-testid="dp-net-premium" style={{ color: biasColor(dp_session.bias), textShadow: biasGlow(dp_session.bias) }}>
          {fmtDollar(dp_session.net_premium)}
        </span>
        <span className="text-dark">{' │ '}</span>
        <span data-testid="dp-session-bias" style={{ color: biasColor(dp_session.bias), textShadow: biasGlow(dp_session.bias) }}>
          {dp_session.bias.toUpperCase()}
        </span>
      </div>

      {/* Market Tide */}
      <div className="panel-row">
        <span className="text-dim">{'TIDE: '}</span>
        <span data-testid="market-tide" style={{ color: biasColor(market_tide.direction), textShadow: biasGlow(market_tide.direction) }}>
          {market_tide.direction.toUpperCase()}
        </span>
        <span className="text-dark">{' │ '}</span>
        <span className="text-dim">{'Bull: '}</span>
        <span style={{ color: 'var(--terminal-green)' }}>{fmtDollar(market_tide.call_premium)}</span>
        <span className="text-dark">{' │ '}</span>
        <span className="text-dim">{'Bear: '}</span>
        <span style={{ color: 'var(--terminal-red)' }}>{fmtDollar(market_tide.put_premium)}</span>
      </div>

      {/* Signal Grid header */}
      <div style={{ color: 'var(--terminal-dark)', marginTop: '2px' }}>
        {'├──────────────────────── SIGNAL GRID ───────────────────────────────────────────────────────┤'}
      </div>

      {/* Signal rows — two columns */}
      {(() => {
        const rows = signal_grid.rows
        const mid = Math.ceil(rows.length / 2)
        const left = rows.slice(0, mid)
        const right = rows.slice(mid)
        const lines: React.ReactNode[] = []

        for (let i = 0; i < left.length; i++) {
          const l = left[i]
          const r = right[i]
          lines.push(
            <div className="panel-row" key={`sig-${i}`}>
              <span className="text-dim">{(l.label + ':').padEnd(18)}</span>
              <span style={{ color: stateColor(l.state), textShadow: stateGlow(l.state) }}>
                {l.state.toUpperCase().padEnd(8)}
              </span>
              {r && (
                <>
                  <span className="text-dark">{'│ '}</span>
                  <span className="text-dim">{(r.label + ':').padEnd(18)}</span>
                  <span style={{ color: stateColor(r.state), textShadow: stateGlow(r.state) }}>
                    {r.state.toUpperCase().padEnd(8)}
                  </span>
                </>
              )}
            </div>,
          )
        }
        return lines
      })()}

      {/* Confluence summary */}
      <div className="panel-row" data-testid="confluence">
        <span className="text-dim">{'CONFLUENCE: '}</span>
        <span style={{ color: 'var(--terminal-green)', textShadow: 'var(--terminal-glow)' }}>
          {signal_grid.confluence_buy}/{signal_grid.total_signals} BUY
        </span>
        <span className="text-dark">{' │ '}</span>
        <span style={{ color: 'var(--terminal-red)', textShadow: 'var(--terminal-glow-red)' }}>
          {signal_grid.confluence_sell}/{signal_grid.total_signals} SELL
        </span>
      </div>

      {/* DP Levels header */}
      {dp_levels.length > 0 && (
        <>
          <div style={{ color: 'var(--terminal-dark)', marginTop: '2px' }}>
            {'├──────────────────────── DP LEVELS ─────────────────────────────────────────────────────────┤'}
          </div>
          {dp_levels.map((lv, i) => (
            <div className="panel-row" key={`dp-lv-${i}`} data-testid={`dp-level-${i}`}>
              <span style={{ color: levelColor(lv.level_type), textShadow: levelGlow(lv.level_type) }}>
                {lv.level_type.toUpperCase().padEnd(8)}
              </span>
              <span className="text-bright">
                {fmtPrice(lv.price_nq)}
              </span>
              <span className="text-dark">{' │ '}</span>
              <span className="text-dim">{fmtDollar(lv.total_premium)}</span>
              <span className="text-dark">{' │ '}</span>
              <span className="text-dim">{lv.print_count} prints</span>
              <span className="text-dark">{' │ '}</span>
              <span className="text-dim">{'x'}{lv.multiplier.toFixed(1)}</span>
            </div>
          ))}
        </>
      )}

      {/* Swing Equilibrium + DP Bias */}
      <div style={{ color: 'var(--terminal-dark)', marginTop: '2px' }}>
        {'├───────────────────────────────────────────────────────────────────────────────────────────┤'}
      </div>
      <div className="panel-row">
        <span className="text-dim">{'SWING EQUILIBRIUM: '}</span>
        <span className="text-bright" data-testid="swing-eq">
          {fmtPrice(swing_equilibrium.price_nq)}
        </span>
        <span className="text-dim">{` (${swing_equilibrium.period_days}d)`}</span>
        <span className="text-dark">{' │ '}</span>
        <span className="text-dim">{'DP BIAS: '}</span>
        <span data-testid="dp-bias-inst" style={{ color: biasColor(dp_bias), textShadow: biasGlow(dp_bias) }}>
          {dp_bias.toUpperCase()}
        </span>
      </div>
    </div>
  )
}

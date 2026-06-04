'use client'

import { useGEXStore } from '@/store/gexStore'
import { useGEXStream } from '@/hooks/useGEXStream'
import { TerminalFrame } from '@/components/TerminalFrame'
import { VerdictPanel } from '@/components/VerdictPanel'
import { LevelsPanel } from '@/components/LevelsPanel'
import { DealerPanel } from '@/components/DealerPanel'
import { FlowPanel } from '@/components/FlowPanel'
import { VannaCharmPanel } from '@/components/VannaCharmPanel'
import { ZeroDTEPanel } from '@/components/ZeroDTEPanel'
import { NarrativePanel } from '@/components/NarrativePanel'
import { Deep6BiasPanel } from '@/components/Deep6BiasPanel'
import { DarkPoolPanel } from '@/components/DarkPoolPanel'
import { InstitutionalHUD } from '@/components/InstitutionalHUD'
import { StatusFooter } from '@/components/StatusFooter'
import { useState, useEffect } from 'react'

export default function Home() {
  useGEXStream()
  const { snapshot, connected } = useGEXStore()
  const [countdown, setCountdown] = useState(30)

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdown(c => c <= 1 ? 30 : c - 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    setCountdown(30)
  }, [snapshot?.timestamp])

  if (!snapshot) {
    return (
      <TerminalFrame>
        <div className="terminal-content">
          <div className="panel-row">
            <span className="text-dim text-bold">{'GEX DOCTOR v2.0'}</span>
            <span className="text-dark">{' │ '}</span>
            <span className="text-dim">{'NQ FUTURES'}</span>
            <span className="text-dark">{' │ '}</span>
            <span className="text-dim">{'Connecting...'}</span>
            <span className="text-dark">{' │ '}</span>
            <span className="text-dark">{'○ OFFLINE'}</span>
          </div>
        </div>
      </TerminalFrame>
    )
  }

  const timeStr = new Date(snapshot.timestamp * 1000).toLocaleTimeString('en-US', {
    timeZone: 'America/New_York',
    hour12: false,
  })

  // ZeroDTEPanel expects percentage (23), snapshot stores fraction (0.23)
  const zeroDtePct = snapshot.zero_dte.gex_pct_of_total != null
    ? Math.round(snapshot.zero_dte.gex_pct_of_total * 100)
    : undefined

  return (
    <TerminalFrame>
      <div className="terminal-content">
        <div className="panel-row">
          <span className="text-dim text-bold">{'GEX DOCTOR v2.0'}</span>
          <span className="text-dark">{' │ '}</span>
          <span className="text-dim">{'NQ FUTURES'}</span>
          <span className="text-dark">{' │ '}</span>
          <span className="text-dim">{timeStr}{' ET'}</span>
          <span className="text-dark">{' │ '}</span>
          <span className={connected ? 'text-bright' : 'text-dark'}>
            {connected ? '⬤ LIVE' : '○ OFFLINE'}
          </span>
        </div>
        <VerdictPanel {...snapshot.bias} />
        <LevelsPanel
          gamma_flip={snapshot.levels.gamma_flip ?? undefined}
          call_wall={snapshot.levels.call_wall ?? undefined}
          put_wall={snapshot.levels.put_wall ?? undefined}
          hvl={snapshot.levels.hvl ?? undefined}
          zero_dte_magnet={snapshot.levels.zero_dte_magnet ?? undefined}
          expected_move_up={snapshot.levels.expected_move_up ?? undefined}
          expected_move_down={snapshot.levels.expected_move_down ?? undefined}
        />
        <DealerPanel
          net_gex={snapshot.dealer.net_gex ?? undefined}
          net_dex={snapshot.dealer.net_dex ?? undefined}
          net_vex={snapshot.dealer.net_vex ?? undefined}
          net_chex={snapshot.dealer.net_chex ?? undefined}
          regime={snapshot.dealer.regime}
          hedge_direction={snapshot.dealer.hedge_direction}
        />
        <FlowPanel {...snapshot.flow} />
        <VannaCharmPanel
          vanna_exposure={snapshot.vanna_charm.vanna_exposure ?? undefined}
          charm_exposure={snapshot.vanna_charm.charm_exposure ?? undefined}
          net_hedge_direction={snapshot.vanna_charm.net_hedge_direction}
        />
        <ZeroDTEPanel
          gex_pct_of_total={zeroDtePct}
          pin_risk={snapshot.zero_dte.pin_risk}
          gamma_acceleration={snapshot.zero_dte.gamma_acceleration ?? undefined}
        />
        <NarrativePanel
          text={snapshot.narrative.text}
          model={snapshot.narrative.model}
          cached={snapshot.narrative.cached}
          cost_usd={snapshot.narrative.cost_usd}
        />
        <Deep6BiasPanel
          bias_score={snapshot.deep6_bias_score ?? undefined}
          bias_label={snapshot.deep6_bias_label ?? undefined}
          confidence={snapshot.deep6_confidence ?? undefined}
          connected={snapshot.deep6_bias_score != null || snapshot.deep6_bias_label === 'STANDALONE'}
        />
        {snapshot.dark_pool && (
          <DarkPoolPanel
            levels_nq={snapshot.dark_pool.levels_nq}
            net_premium={snapshot.dark_pool.net_premium}
            institutional_bias={snapshot.dark_pool.institutional_bias}
          />
        )}
        {snapshot.institutional && (
          <InstitutionalHUD
            inst_flow_direction={snapshot.institutional.inst_flow_direction}
            dp_session={snapshot.institutional.dark_pool_session}
            market_tide={snapshot.institutional.market_tide}
            signal_grid={snapshot.institutional.signal_grid}
            dp_levels={snapshot.institutional.dp_levels}
            swing_equilibrium={snapshot.institutional.swing_equilibrium}
            dp_bias={snapshot.institutional.dp_bias}
          />
        )}
        <StatusFooter
          sources={snapshot.sources}
          cost_today_usd={snapshot.cost_today_usd}
          refresh_countdown={countdown}
        />
      </div>
    </TerminalFrame>
  )
}

/** GEX Terminal TypeScript types — mirrors gex_terminal/schemas.py exactly. */

export interface SourceHealth {
  name: string
  status: 'ok' | 'stale' | 'error' | 'pending'
  last_update: number | null
  ttl_sec: number
  error_msg: string
}

export interface GEXLevels {
  gamma_flip: number | null
  call_wall: number | null
  put_wall: number | null
  hvl: number | null
  zero_dte_magnet: number | null
  expected_move_up: number | null
  expected_move_down: number | null
}

export interface DealerPositioning {
  net_gex: number | null
  net_dex: number | null
  net_vex: number | null
  net_chex: number | null
  regime: string
  hedge_direction: string
}

export interface FlowSummary {
  direction: string
  intensity: number
  sweep_count: number
  block_count: number
  z_score: number
}

export interface VannaCharmState {
  vanna_exposure: number | null
  charm_exposure: number | null
  net_hedge_direction: string
}

export interface ZeroDTEState {
  gex_pct_of_total: number | null
  pin_risk: string
  gamma_acceleration: number | null
}

export interface DarkPoolData {
  levels_nq: number[]
  net_premium: number | null
  institutional_bias: string
}

export interface ClaudeNarrative {
  text: string
  model: string
  timestamp: number | null
  cached: boolean
  cost_usd: number
}

export interface BiasVerdict {
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  confidence: number
  grade: string
  regime_name: string
}

/* ── Institutional Dark Pool Types ── */

export interface InstitutionalHolder {
  name: string
  shares: number
  value_usd: number
  change_shares: number
  pct_of_float: number
}

export interface DarkPoolLevel {
  price_nq: number
  total_premium: number
  print_count: number
  volume: number
  multiplier: number
  std_dev: number
  level_type: string
}

export interface SignalGridRow {
  signal_id: string
  label: string
  state: string
  score: number
}

export interface SignalGrid {
  rows: SignalGridRow[]
  confluence_buy: number
  confluence_sell: number
  total_signals: number
}

export interface DarkPoolSession {
  print_count: number
  buy_volume: number
  sell_volume: number
  net_premium: number
  bias: string
  accumulation_pct: number
}

export interface MarketTide {
  call_premium: number
  put_premium: number
  direction: string
  strength_pct: number
}

export interface SwingEquilibrium {
  price_nq: number
  period_days: number
  confidence: number
}

export interface InstitutionalSnapshot {
  timestamp: number
  inst_flow_direction: string
  top_holders: InstitutionalHolder[]
  dark_pool_session: DarkPoolSession
  market_tide: MarketTide
  signal_grid: SignalGrid
  dp_levels: DarkPoolLevel[]
  swing_equilibrium: SwingEquilibrium
  dp_bias: string
}

/* ── Root Snapshot ── */

export interface GEXTerminalSnapshot {
  timestamp: number
  bias: BiasVerdict
  levels: GEXLevels
  dealer: DealerPositioning
  flow: FlowSummary
  vanna_charm: VannaCharmState
  zero_dte: ZeroDTEState
  dark_pool?: DarkPoolData
  narrative: ClaudeNarrative
  sources: Record<string, SourceHealth>
  deep6_bias_score: number | null
  deep6_bias_label: string | null
  deep6_confidence: number | null
  cost_today_usd: number
  institutional?: InstitutionalSnapshot
}

// === Footprint bar wire shape (matches BarEventIn in deep6/api/schemas.py) ===

export interface FootprintLevel {
  bid_vol: number;
  ask_vol: number;
}

/**
 * Full bar payload. `levels` keys are stringified tick integers;
 * price = tick * 0.25 (NQ). Mirrors BarEventIn in deep6/api/schemas.py.
 */
export interface FootprintBar {
  session_id: string;
  bar_index: number;
  ts: number;
  open: number;
  high: number;
  low: number;
  close: number;
  total_vol: number;
  bar_delta: number;
  cvd: number;
  poc_price: number;
  bar_range: number;
  running_delta: number;
  max_delta: number;
  min_delta: number;
  levels: Record<string, FootprintLevel>;
}

// === Signal === (mirrors SignalEventIn in deep6/api/schemas.py)
export interface SignalEvent {
  ts: number;
  bar_index_in_session: number;
  total_score: number;
  tier: 'TYPE_A' | 'TYPE_B' | 'TYPE_C' | 'QUIET';
  direction: -1 | 0 | 1;
  engine_agreement: number;
  category_count: number;
  categories_firing: string[];
  gex_regime: string;
  kronos_bias: number;
}

// === Zones (UI-SPEC §Zone Overlay Canvas Layer) ===
export type ZoneType = 'LVN' | 'HVN' | 'ABSORPTION' | 'GEX_CALL' | 'GEX_PUT';

export interface ZoneRef {
  kind: ZoneType;
  priceHigh: number;
  priceLow: number;
  score?: number;
}

// === Tape row (placeholder shape for Wave 3) ===
export interface TapeEntry {
  ts: number;
  price: number;
  size: number;
  side: 'ASK' | 'BID'; // ask=buy-aggressor, bid=sell-aggressor
}

// === LiveMessage discriminated union (mirrors LiveMessage in deep6/api/schemas.py) ===

export interface LiveBarMessage {
  type: 'bar';
  session_id: string;
  bar_index: number;
  bar: FootprintBar;
}

export interface LiveSignalMessage {
  type: 'signal';
  event: SignalEvent;
  narrative: string;
}

export interface LiveScoreMessage {
  type: 'score';
  total_score: number;
  tier: 'TYPE_A' | 'TYPE_B' | 'TYPE_C' | 'QUIET';
  direction: -1 | 0 | 1;
  categories_firing: string[];
  category_scores: Record<string, number>;
  kronos_bias: number;
  kronos_direction: 'LONG' | 'SHORT' | 'NEUTRAL';
  gex_regime: string;
}

export interface LiveStatusMessage {
  type: 'status';
  connected: boolean;
  pnl: number;
  circuit_breaker_active: boolean;
  feed_stale: boolean;
  ts: number;
}

export type LiveMessage =
  | LiveBarMessage
  | LiveSignalMessage
  | LiveScoreMessage
  | LiveStatusMessage;

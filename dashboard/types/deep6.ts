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

// === Tape row (mirrors TapeEventIn in deep6/api/schemas.py) ===
export interface TapeEntry {
  ts: number;
  price: number;
  size: number;
  side: 'ASK' | 'BID'; // ask=buy-aggressor, bid=sell-aggressor
  marker: '' | 'SWEEP' | 'ICEBERG' | 'KRONOS';
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
  // Phase 11.3-r3 observability fields (all optional — safe defaults on the wire)
  session_start_ts?: number;   // epoch when session started; frontend computes elapsed
  bars_received?: number;      // authoritative backend bar count
  signals_fired?: number;      // authoritative backend signal count
  last_signal_tier?: string;   // '' | 'TYPE_A' | 'TYPE_B' | 'TYPE_C'
  uptime_seconds?: number;     // backend process uptime in seconds
  active_clients?: number;     // WS clients currently connected
}

export interface LiveTapeMessage {
  type: 'tape';
  event: TapeEntry;
}

export type LiveMessage =
  | LiveBarMessage
  | LiveSignalMessage
  | LiveScoreMessage
  | LiveStatusMessage
  | LiveTapeMessage;

// === DOM Intelligence types ===

export interface DOMLadderLevel {
  price: number;
  volume: number;
}

/** WebSocket schema for DOM ladder updates. */
export interface DOMLadderState {
  bids: DOMLadderLevel[];
  asks: DOMLadderLevel[];
  version: number;
}

/** Detector tier classification. */
export type DetectorTier = 'MECHANICAL' | 'HEURISTIC' | 'DISCRETIONARY_OVERLAY';

/** Single active detector summary. */
export interface ActiveDetectorSummary {
  detector_id: string;
  name: string;
  tier: DetectorTier;
  fire_count: number;
  last_direction: -1 | 0 | 1;
  last_confidence: number;
}

/** Intelligence rail state from API SSE endpoint. */
export interface IntelligenceRailState {
  total_events: number;
  active_detectors: ActiveDetectorSummary[];
  score_summary: {
    mechanical_score: number;
    heuristic_score: number;
    overall_direction: -1 | 0 | 1;
  };
  updated_at: number;
}

// === DepthRadar types (LiveMBORadar wall classification + episodes + touches) ===

export type WallIntent =
  | 'PASSIVE_REAL'
  | 'RESERVE_REFRESH'
  | 'SPOOF_LIKE'
  | 'MIGRATORY'
  | 'UNKNOWN';

export type WallState =
  | 'FRESH'
  | 'ESTABLISHED'
  | 'UNDER_ATTACK'
  | 'DEFENDING'
  | 'EXHAUSTED'
  | 'STALE';

export type WallSide = 'BID' | 'ASK';

export type TouchOutcome = 'BOUNCE' | 'BREAK' | 'CHURN';

/** Active wall from GET /api/depthradar/walls */
export interface DepthRadarWall {
  id: string;
  price: number;
  side: WallSide;
  size: number;
  max_size: number;
  intent: WallIntent;
  state: WallState;
  confidence: number;
  age_seconds: number;
  first_seen_ts: number;
}

/** Episode from GET /api/depthradar/episodes */
export interface DepthRadarEpisode {
  id: string;
  wall_id: string;
  price: number;
  side: WallSide;
  intent: WallIntent;
  final_state: WallState;
  duration_seconds: number;
  max_size: number;
  touch_count: number;
  started_at: number;
  ended_at: number;
}

/** Touch event from GET /api/depthradar/touches */
export interface DepthRadarTouch {
  id: string;
  episode_id: string;
  price: number;
  outcome: TouchOutcome;
  aggressor_volume: number;
  defender_volume: number;
  ts: number;
}

/** Aggregated metrics from GET /api/depthradar/metrics */
export interface DepthRadarMetrics {
  total_walls_classified: number;
  total_episodes: number;
  total_touches: number;
  intent_distribution: Record<WallIntent, number>;
  outcome_distribution: Record<TouchOutcome, number>;
  avg_episode_duration_seconds: number;
}

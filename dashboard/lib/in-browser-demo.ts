/**
 * in-browser-demo.ts — Client-side port of scripts/demo_broadcast.py
 *
 * Provides PriceModel, ScoreModel, SignalScheduler, buildBar, and Stats.
 * All logic runs in the browser; no backend required.
 * Used by useInBrowserDemo hook for Vercel / demo deployments.
 */

import type {
  LiveMessage,
  LiveBarMessage,
  LiveSignalMessage,
  LiveScoreMessage,
  LiveStatusMessage,
  LiveTapeMessage,
  FootprintBar,
} from '@/types/deep6';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TICK_SIZE = 0.25;
const NQ_START  = 19_483.50;
const NQ_LO     = 19_400.00;
const NQ_HI     = 19_560.00;

export const SESSION_ID = 'demo-browser-2026-04-14';

const ALL_CATEGORIES = [
  'absorption', 'exhaustion', 'imbalance', 'delta',
  'auction', 'volume', 'trap', 'ml_context',
] as const;

const NARRATIVES = [
  'ABSORBED @VAH',
  'EXHAUSTED @LVN',
  'TRAPPED @19478.00',
  'REVERSAL @POC',
  'ICEBERG @19482.25',
  'SWEEP @HVN',
  'DELTA FLIP @19490.00',
  'REJECTION @HOD',
  'STACKED IMBALANCE @19475.50',
  'STOP RUN @LOD',
] as const;

const GEX_REGIMES = ['POS_GAMMA', 'NEUTRAL', 'NEG_GAMMA'] as const;

// ---------------------------------------------------------------------------
// Tiny RNG helpers (no external deps)
// ---------------------------------------------------------------------------

function randn(): number {
  // Box-Muller transform — standard normal
  const u = 1 - Math.random();
  const v = Math.random();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function gauss(mean: number, std: number): number {
  return mean + std * randn();
}

function randUniform(lo: number, hi: number): number {
  return lo + Math.random() * (hi - lo);
}

function randInt(lo: number, hi: number): number {
  return Math.floor(lo + Math.random() * (hi - lo + 1));
}

function choice<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function sample<T>(arr: readonly T[], k: number): T[] {
  const copy = [...arr];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy.slice(0, Math.min(k, copy.length));
}

function weightedChoice<T>(items: readonly T[], weights: readonly number[]): T {
  const total = weights.reduce((a, b) => a + b, 0);
  let r = Math.random() * total;
  for (let i = 0; i < items.length; i++) {
    r -= weights[i];
    if (r <= 0) return items[i];
  }
  return items[items.length - 1];
}

// ---------------------------------------------------------------------------
// PriceModel — autocorrelated Gaussian random walk, bounded, tick-snapped
// ---------------------------------------------------------------------------

export class PriceModel {
  price: number;
  drift: number;

  constructor(start = NQ_START) {
    this.price = start;
    this.drift = 0;
  }

  tick(): number {
    const mid = (NQ_LO + NQ_HI) / 2;
    const reversion = (mid - this.price) * 0.002;
    this.drift = this.drift * 0.80 + gauss(0, 0.25);
    let raw = this.price + this.drift + reversion;

    if (raw < NQ_LO) {
      raw = NQ_LO + (NQ_LO - raw);
      this.drift = Math.abs(this.drift);
    } else if (raw > NQ_HI) {
      raw = NQ_HI - (raw - NQ_HI);
      this.drift = -Math.abs(this.drift);
    }

    this.price = Math.round(Math.round(raw / TICK_SIZE) * TICK_SIZE * 100) / 100;
    return this.price;
  }
}

// ---------------------------------------------------------------------------
// ScoreModel — oscillator 30-92, TYPE_A spikes, Kronos updates
// ---------------------------------------------------------------------------

export class ScoreModel {
  score: number;
  lastSignalTier: string;
  private target: number;
  private phase: number;
  private spikeUntil: number;
  private spikeValue: number;
  kronosBias: number;
  kronosDir: 'LONG' | 'SHORT' | 'NEUTRAL';
  gexRegime: string;
  private kronosNextUpdate: number;

  constructor() {
    this.score = 55;
    this.target = 55;
    this.phase = 0;
    this.spikeUntil = 0;
    this.spikeValue = 0;
    this.kronosBias = 60;
    this.kronosDir = 'NEUTRAL';
    this.gexRegime = 'NEUTRAL';
    this.kronosNextUpdate = 0;
    this.lastSignalTier = '';
  }

  applyTypeASpike(): void {
    this.spikeValue = randUniform(85, 95);
    this.spikeUntil = Date.now() / 1000 + 10;
  }

  update(): void {
    this.phase += 0.12;
    this.target += gauss(0, 0.4);
    this.target = Math.max(32, Math.min(88, this.target));
    this.score += (this.target - this.score) * 0.12;
    this.score += Math.sin(this.phase) * 3.5;
    this.score = Math.max(28, Math.min(92, this.score));

    const now = Date.now() / 1000;
    if (now < this.spikeUntil) {
      const elapsed = this.spikeUntil - now;
      const decay = elapsed / 10;
      this.score = this.spikeValue * decay + this.score * (1 - decay);
    }

    if (now >= this.kronosNextUpdate) {
      this.kronosBias = randUniform(35, 85);
      this.kronosDir = choice(['LONG', 'SHORT', 'NEUTRAL'] as const);
      this.gexRegime = weightedChoice(GEX_REGIMES, [0.50, 0.35, 0.15]);
      this.kronosNextUpdate = now + randUniform(15, 20);
    }
  }

  tier(): 'TYPE_A' | 'TYPE_B' | 'TYPE_C' | 'QUIET' {
    if (this.score >= 80) return 'TYPE_A';
    if (this.score >= 60) return 'TYPE_B';
    if (this.score >= 40) return 'TYPE_C';
    return 'QUIET';
  }

  direction(): -1 | 0 | 1 {
    const m: Record<string, -1 | 0 | 1> = { LONG: 1, SHORT: -1, NEUTRAL: 0 };
    return m[this.kronosDir] ?? 0;
  }

  categoryScores(): Record<string, number> {
    const b = this.score;
    const clamp = (v: number) => Math.min(100, Math.max(0, v));
    return {
      absorption: clamp(b * randUniform(0.85, 1.15)),
      exhaustion:  clamp(b * randUniform(0.75, 1.10)),
      imbalance:   clamp(b * randUniform(0.70, 1.05)),
      delta:       clamp(b * randUniform(0.65, 1.10)),
      auction:     clamp(b * randUniform(0.60, 1.00)),
      volume:      clamp(b * randUniform(0.60, 1.05)),
      trap:        clamp(b * randUniform(0.50, 0.95)),
      ml_context:  clamp(b * randUniform(0.40, 0.90)),
    };
  }

  categoriesFiring(tier: string): string[] {
    const n: Record<string, number> = { TYPE_A: 7, TYPE_B: 5, TYPE_C: 3 };
    return sample(ALL_CATEGORIES, n[tier] ?? 1);
  }
}

// ---------------------------------------------------------------------------
// SignalScheduler — Poisson-like timers per tier, narrative cycling
// ---------------------------------------------------------------------------

export class SignalScheduler {
  private next: Record<string, number>;
  private narrativeIdx: number;

  constructor() {
    const now = Date.now() / 1000;
    this.next = {
      TYPE_C: now + randUniform(8, 15),
      TYPE_B: now + randUniform(30, 60),
      TYPE_A: now + randUniform(90, 180),
    };
    this.narrativeIdx = 0;
  }

  due(): string[] {
    const now = Date.now() / 1000;
    return Object.entries(this.next)
      .filter(([, t]) => now >= t)
      .map(([tier]) => tier);
  }

  reset(tier: string): void {
    const intervals: Record<string, [number, number]> = {
      TYPE_C: [8, 15],
      TYPE_B: [30, 60],
      TYPE_A: [90, 180],
    };
    const [lo, hi] = intervals[tier] ?? [15, 30];
    this.next[tier] = Date.now() / 1000 + randUniform(lo, hi);
  }

  nextNarrative(): string {
    const n = NARRATIVES[this.narrativeIdx % NARRATIVES.length];
    this.narrativeIdx++;
    return n;
  }
}

// ---------------------------------------------------------------------------
// buildBar — 31-row Gaussian-weighted footprint ladder
// ---------------------------------------------------------------------------

export function buildBar(
  barIndex: number,
  barOpen: number,
  barClose: number,
  barHigh: number,
  barLow: number,
  barTs: number,
  runningDelta: number,
): LiveBarMessage {
  const center = (barHigh + barLow) / 2;
  const centerTick = Math.round(center / TICK_SIZE);
  const oneSided = Math.random() < 0.30;
  const biasSide = choice(['ask', 'bid'] as const);
  const pocTick = centerTick + randInt(-3, 3);
  const pocPrice = Math.round(pocTick * TICK_SIZE * 100) / 100;
  const totalVol = randInt(1500, 3500);

  const NUM_ROWS = 31;
  const rowWeights: number[] = [];
  for (let i = 0; i < NUM_ROWS; i++) {
    rowWeights.push(Math.exp(-0.5 * ((i - 15) / 6) ** 2));
  }
  const wSum = rowWeights.reduce((a, b) => a + b, 0);

  const levels: Record<string, { bid_vol: number; ask_vol: number }> = {};
  let cumBid = 0;
  let cumAsk = 0;

  for (let i = 0; i < NUM_ROWS; i++) {
    const offset = i - 15;
    const tick = centerTick + offset;
    const weight = rowWeights[i] / wSum;
    let rowVol = Math.max(1, Math.floor(totalVol * weight * randUniform(0.7, 1.3)));

    if (tick === pocTick) {
      rowVol = Math.floor(rowVol * randUniform(1.8, 2.8));
    }

    let bidVol: number, askVol: number;
    if (oneSided && biasSide === 'ask') {
      const factor = randUniform(2, 4);
      askVol = Math.floor(rowVol * factor / (1 + factor));
      bidVol = rowVol - askVol;
    } else if (oneSided && biasSide === 'bid') {
      const factor = randUniform(2, 4);
      bidVol = Math.floor(rowVol * factor / (1 + factor));
      askVol = rowVol - bidVol;
    } else {
      const split = randUniform(0.38, 0.62);
      bidVol = Math.max(1, Math.floor(rowVol * split));
      askVol = Math.max(1, rowVol - bidVol);
    }

    levels[String(tick)] = { bid_vol: bidVol, ask_vol: askVol };
    cumBid += bidVol;
    cumAsk += askVol;
  }

  const barDelta = cumAsk - cumBid;
  const bar: FootprintBar = {
    session_id: SESSION_ID,
    bar_index: barIndex,
    ts: barTs,
    open: barOpen,
    high: barHigh,
    low: barLow,
    close: barClose,
    total_vol: totalVol,
    bar_delta: barDelta,
    cvd: runningDelta + barDelta,
    poc_price: pocPrice,
    bar_range: Math.round((barHigh - barLow) * 100) / 100,
    running_delta: runningDelta,
    max_delta: Math.abs(barDelta) + randInt(10, 60),
    min_delta: -(Math.abs(barDelta) + randInt(10, 60)),
    levels,
  };

  return { type: 'bar', session_id: SESSION_ID, bar_index: barIndex, bar };
}

// ---------------------------------------------------------------------------
// Stats — cumulative counters
// ---------------------------------------------------------------------------

export class Stats {
  ticks    = 0;
  bars     = 0;
  signals  = 0;
  scores   = 0;
  tape     = 0;
  status   = 0;
  readonly start: number;

  constructor() {
    this.start = Date.now() / 1000;
  }

  elapsed(): number {
    return Date.now() / 1000 - this.start;
  }
}

// ---------------------------------------------------------------------------
// DemoState — aggregated mutable state shared across ticks
// ---------------------------------------------------------------------------

export interface DemoState {
  price:    PriceModel;
  score:    ScoreModel;
  sched:    SignalScheduler;
  stats:    Stats;
  sessionStartTs: number;
  barIndex: number;
  barOpen:  number;
  barHigh:  number;
  barLow:   number;
  barTs:    number;
  runningDelta: number;
  ticksSinceBar:   number;
  ticksSinceTape:  number;
  ticksSinceScore: number;
  pnl: number;
}

export function createDemoState(): DemoState {
  const now = Date.now() / 1000;
  return {
    price:    new PriceModel(NQ_START),
    score:    new ScoreModel(),
    sched:    new SignalScheduler(),
    stats:    new Stats(),
    sessionStartTs: now,
    barIndex: 0,
    barOpen:  NQ_START,
    barHigh:  NQ_START,
    barLow:   NQ_START,
    barTs:    now,
    runningDelta: 0,
    ticksSinceBar:   0,
    ticksSinceTape:  0,
    ticksSinceScore: 0,
    pnl: Math.round(randUniform(-500, 1200) * 100) / 100,
  };
}

// Intervals (ticks) — matches Python BAR_INTERVAL=2, TAPE_INTERVAL=1, SCORE_INTERVAL=5
// (hook fires every 500ms at rate 2x, so: bar every 2 ticks ≈ 1s, tape every tick, score every 10 ticks)
const BAR_INTERVAL   = 2;
const TAPE_INTERVAL  = 1;
const SCORE_INTERVAL = 10;

/**
 * runDemoTick — advance state by one tick and return all LiveMessages to dispatch.
 * Caller (useInBrowserDemo) calls this on each interval and dispatches the array.
 */
export function runDemoTick(s: DemoState): LiveMessage[] {
  const messages: LiveMessage[] = [];
  const now = Date.now() / 1000;

  // --- Advance models ---
  const price = s.price.tick();
  s.score.update();
  s.barHigh = Math.max(s.barHigh, price);
  s.barLow  = Math.min(s.barLow, price);
  s.stats.ticks++;
  s.ticksSinceBar++;
  s.ticksSinceTape++;
  s.ticksSinceScore++;

  // 1. STATUS — every tick
  s.pnl += gauss(0, 1.5);
  s.pnl  = Math.round(s.pnl * 100) / 100;
  const statusMsg: LiveStatusMessage = {
    type: 'status',
    connected: true,
    pnl: s.pnl,
    circuit_breaker_active: false,
    feed_stale: false,
    ts: now,
    session_start_ts: s.sessionStartTs,
    bars_received: s.stats.bars,
    signals_fired: s.stats.signals,
    last_signal_tier: s.score.lastSignalTier,
    uptime_seconds: Math.floor(now - s.sessionStartTs),
    active_clients: 0,
  };
  messages.push(statusMsg);
  s.stats.status++;

  // 2. TAPE — every TAPE_INTERVAL ticks (2-4 prints per fire for realism)
  if (s.ticksSinceTape >= TAPE_INTERVAL) {
    s.ticksSinceTape = 0;
    const printCount = randInt(2, 4);
    for (let i = 0; i < printCount; i++) {
      const tapePrice = price + choice([-0.25, 0, 0.25] as const);
      const tapeSize  = randInt(1, 200);
      const askWeight = s.runningDelta > 0 ? 0.60 : 0.40;
      const tapeSide  = weightedChoice(['ASK', 'BID'] as const, [askWeight, 1 - askWeight]);
      let tapeMarker: '' | 'SWEEP' | 'ICEBERG' | 'KRONOS' = '';
      if (Math.random() < 0.20) {
        if (tapeSize >= 100)       tapeMarker = 'SWEEP';
        else if (Math.random() < 0.40) tapeMarker = 'ICEBERG';
        else                       tapeMarker = 'KRONOS';
      }
      const tapeMsg: LiveTapeMessage = {
        type: 'tape',
        event: { ts: now, price: tapePrice, size: tapeSize, side: tapeSide, marker: tapeMarker },
      };
      messages.push(tapeMsg);
      s.stats.tape++;
    }
  }

  // 3. BAR — every BAR_INTERVAL ticks
  if (s.ticksSinceBar >= BAR_INTERVAL) {
    s.ticksSinceBar = 0;
    const barMsg = buildBar(
      s.barIndex, s.barOpen, price, s.barHigh, s.barLow, now, s.runningDelta,
    );
    s.runningDelta = barMsg.bar.cvd;
    messages.push(barMsg);
    s.stats.bars++;
    s.barIndex++;
    s.barOpen = price;
    s.barHigh = price;
    s.barLow  = price;
    s.barTs   = now;
  }

  // 4. SCORE — every SCORE_INTERVAL ticks
  if (s.ticksSinceScore >= SCORE_INTERVAL) {
    s.ticksSinceScore = 0;
    const tier = s.score.tier();
    const scoreMsg: LiveScoreMessage = {
      type: 'score',
      total_score: Math.round(s.score.score * 10) / 10,
      tier,
      direction: s.score.direction(),
      categories_firing: s.score.categoriesFiring(tier),
      category_scores: Object.fromEntries(
        Object.entries(s.score.categoryScores()).map(([k, v]) => [k, Math.round(v * 10) / 10])
      ),
      kronos_bias: Math.round(s.score.kronosBias * 10) / 10,
      kronos_direction: s.score.kronosDir,
      gex_regime: s.score.gexRegime,
    };
    messages.push(scoreMsg);
    s.stats.scores++;
  }

  // 5. SIGNALS — Poisson-like cadence
  for (const tier of s.sched.due()) {
    s.sched.reset(tier);
    const sigScoreMap: Record<string, [number, number]> = {
      TYPE_A: [82, 97], TYPE_B: [62, 79], TYPE_C: [40, 61],
    };
    const [lo, hi] = sigScoreMap[tier] ?? [40, 61];
    const sigScore = randUniform(lo, hi);
    const direction = s.score.direction() || (Math.random() < 0.5 ? 1 : -1) as -1 | 1;
    const signalMsg: LiveSignalMessage = {
      type: 'signal',
      event: {
        ts: now,
        bar_index_in_session: s.barIndex,
        total_score: Math.round(sigScore * 10) / 10,
        tier: tier as 'TYPE_A' | 'TYPE_B' | 'TYPE_C',
        direction: direction as -1 | 0 | 1,
        engine_agreement: Math.round(randUniform(0.50, 0.95) * 100) / 100,
        category_count: ({ TYPE_A: 7, TYPE_B: 5, TYPE_C: 3 } as Record<string, number>)[tier] ?? 3,
        categories_firing: s.score.categoriesFiring(tier),
        gex_regime: s.score.gexRegime,
        kronos_bias: Math.round(s.score.kronosBias * 10) / 10,
      },
      narrative: s.sched.nextNarrative(),
    };
    messages.push(signalMsg);
    s.stats.signals++;
    s.score.lastSignalTier = tier;
    if (tier === 'TYPE_A') s.score.applyTypeASpike();
  }

  return messages;
}

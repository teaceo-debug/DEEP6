# GEX Doctor v2.0 — Terminal Layout Mockups

> 800×800 CSS pixels · 11px JetBrains Mono · 96 columns × 55 rows
> Box-drawing: ╔═╗║╚═╝╠╣╦╩╬─│

---

## 1. BULLISH State

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║ GEX DOCTOR v2.0  │  NQ FUTURES  │  14:32:45 ET  │  ⬤ LIVE                               ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ ▲▲▲ BULLISH ▲▲▲                   CONFIDENCE: ████████░░ 82%    GRADE: A                 ║
║ Regime: POSITIVE BETWEEN           NQ: 21,450.25  Δ +125.75 (+0.59%)                     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ LEVELS                                                                                    ║
║ GAMMA FLIP: 21,380  ▲ above=bullish  │  CALL WALL: 21,500  │  PUT WALL: 20,900           ║
║ HVL:        21,425                   │  MAGNET:    21,450  │  0DTE MAGNET: 21,400         ║
║ EXP MOVE+:  21,620 (+170pts)         │  EXP MOVE-: 21,280 (-170pts)                      ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEALER POSITIONING                                                                        ║
║ GEX: +3.2B (positive)  │  DEX: -1.1B (short delta)  │  REGIME: POSITIVE                  ║
║ VEX: +450M (long vol)  │  CHEX: -200M (time drag)   │  HEDGE: BUYING                     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ FLOW: ▲ BULLISH  z:+1.8  INT: ████████░░ HIGH │  SWEEPS: 14  BLOCKS: 3  NET: +$24M      ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ VANNA: +$850M (tailwind ▲)  │  CHARM: -$320M (drag ▼)  │  NET HEDGE: TAILWIND            ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ 0DTE: 23% of total GEX  │  PIN RISK: LOW  │  GAMMA ACCEL: +0.42  │  NEXT 0DTE: TODAY     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ AI: Positive gamma regime. Dealers short gamma, hedging into strength. Call wall           ║
║     21,500 acting as magnet. Expect mean-reversion if price approaches wall.              ║
║     [HAIKU · LIVE · $0.003]                                                               ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEEP6: bias_score=+4  bias_label=LEAN_BULL  confidence=0.72  [CONNECTED]                  ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ FA:● MAS:● UW:●  │  $2.14 today  │  ⟳ 28s  │  14:32:45 ET                               ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝
```

### BULLISH Color Map

| Element                    | Color         | Hex       |
|----------------------------|---------------|-----------|
| Direction arrows ▲▲▲       | Bright green  | `#00FF41` |
| BULLISH verdict text       | Bright green  | `#00FF41` |
| Confidence bar ████████    | Bright green  | `#00FF41` |
| Confidence bar ░░          | Dark green    | `#006600` |
| NQ price + positive delta  | Bright green  | `#00FF41` |
| Grade A                    | Bright green  | `#00FF41` |
| GAMMA FLIP label           | Dim green     | `#00AA00` |
| Level values (21,380 etc)  | Bright green  | `#00FF41` |
| ▲ above=bullish            | Bright green  | `#00FF41` |
| Section headers (LEVELS…)  | Dim green     | `#00AA00` |
| GEX positive values        | Bright green  | `#00FF41` |
| FLOW ▲ BULLISH             | Bright green  | `#00FF41` |
| VANNA tailwind ▲           | Bright green  | `#00FF41` |
| CHARM drag ▼               | Amber         | `#FFB000` |
| AI narrative text          | Dim green     | `#00AA00` |
| AI model badge [HAIKU…]    | Dark green    | `#006600` |
| DEEP6 [CONNECTED]          | Bright green  | `#00FF41` |
| Footer source dots ●       | Bright green  | `#00FF41` |
| Box borders ╔═╗║╚╝╠╣      | Dark green    | `#006600` |
| Separators │               | Dark green    | `#006600` |
| Background                 | Near-black    | `#0A0A0A` |

---

## 2. BEARISH State

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║ GEX DOCTOR v2.0  │  NQ FUTURES  │  14:32:45 ET  │  ⬤ LIVE                               ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ ▼▼▼ BEARISH ▼▼▼                   CONFIDENCE: ██████░░░░ 63%    GRADE: C                 ║
║ Regime: NEGATIVE BELOW FLIP        NQ: 21,180.50  Δ -144.25 (-0.68%)                     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ LEVELS                                                                                    ║
║ GAMMA FLIP: 21,380  ▼ below=bearish  │  CALL WALL: 21,500  │  PUT WALL: 20,900           ║
║ HVL:        21,200                   │  MAGNET:    21,150  │  0DTE MAGNET: 21,100         ║
║ EXP MOVE+:  21,420 (+170pts)         │  EXP MOVE-: 21,080 (-170pts)                      ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEALER POSITIONING                                                                        ║
║ GEX: -1.8B (negative)  │  DEX: +2.3B (long delta)   │  REGIME: NEGATIVE                  ║
║ VEX: -620M (short vol) │  CHEX: +180M (time boost)   │  HEDGE: SELLING                   ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ FLOW: ▼ BEARISH  z:-2.1  INT: ██████████ EXTREME │  SWEEPS: 28  BLOCKS: 7  NET: -$41M   ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ VANNA: -$620M (headwind ▼)  │  CHARM: +$410M (boost ▲)  │  NET HEDGE: HEADWIND           ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ 0DTE: 41% of total GEX  │  PIN RISK: HIGH │  GAMMA ACCEL: -0.67  │  NEXT 0DTE: TODAY     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ AI: Negative gamma regime. Dealers long delta, selling into weakness. Put wall             ║
║     20,900 is next support. Volatility expanding — expect outsized moves.                 ║
║     [HAIKU · LIVE · $0.003]                                                               ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEEP6: bias_score=-3  bias_label=LEAN_BEAR  confidence=0.68  [CONNECTED]                  ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ FA:● MAS:● UW:●  │  $1.87 today  │  ⟳ 28s  │  14:32:45 ET                               ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝
```

### BEARISH Color Map

| Element                    | Color         | Hex       |
|----------------------------|---------------|-----------|
| Direction arrows ▼▼▼       | Red           | `#FF4444` |
| BEARISH verdict text       | Red           | `#FF4444` |
| Confidence bar ██████      | Red           | `#FF4444` |
| Confidence bar ░░░░        | Dark green    | `#006600` |
| NQ price + negative delta  | Red           | `#FF4444` |
| Grade C                    | Amber         | `#FFB000` |
| ▼ below=bearish            | Red           | `#FF4444` |
| GEX negative values        | Red           | `#FF4444` |
| FLOW ▼ BEARISH             | Red           | `#FF4444` |
| FLOW INT: EXTREME          | Red           | `#FF4444` |
| VANNA headwind ▼           | Red           | `#FF4444` |
| CHARM boost ▲              | Bright green  | `#00FF41` |
| PIN RISK: HIGH             | Red           | `#FF4444` |
| 0DTE 41% (elevated)        | Amber         | `#FFB000` |
| DEEP6 bias_score=-3        | Red           | `#FF4444` |
| DEEP6 LEAN_BEAR            | Red           | `#FF4444` |
| Section headers            | Dim green     | `#00AA00` |
| Level values               | Bright green  | `#00FF41` |
| AI narrative text          | Dim green     | `#00AA00` |
| Footer source dots ●       | Bright green  | `#00FF41` |
| Box borders                | Dark green    | `#006600` |
| Background                 | Near-black    | `#0A0A0A` |

---

## 3. DEGRADED State

```
╔════════════════════════════════════════════════════════════════════════════════════════════╗
║ GEX DOCTOR v2.0  │  NQ FUTURES  │  14:32:45 ET  │  ⬤ LIVE                               ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ ▲▲▲ BULLISH ▲▲▲  STALE             CONFIDENCE: ██████░░░░ 58%    GRADE: B-               ║
║ Regime: POSITIVE BETWEEN           NQ: 21,450.25  Δ +125.75 (+0.59%)                     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ LEVELS                                                                                    ║
║ GAMMA FLIP: 21,380  ▲ above=bullish  │  CALL WALL: 21,500  │  PUT WALL: 20,900           ║
║ HVL:        21,425                   │  MAGNET:    21,450  │  0DTE MAGNET: 21,400         ║
║ EXP MOVE+:  21,620 (+170pts)         │  EXP MOVE-: 21,280 (-170pts)                      ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEALER POSITIONING                                                                        ║
║ GEX: +3.2B (positive)  │  DEX: --- (stale)          │  REGIME: POSITIVE                  ║
║ VEX: +450M (long vol)  │  CHEX: --- (stale)         │  HEDGE: BUYING                     ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ FLOW: ▲ BULLISH  z:+1.8  INT: ████████░░ HIGH │  SWEEPS: --  BLOCKS: --  NET: ---        ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ VANNA: +$850M (tailwind ▲)  │  CHARM: --- (stale)       │  NET HEDGE: PARTIAL             ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ 0DTE: 23% of total GEX  │  PIN RISK: LOW  │  GAMMA ACCEL: ---   │  NEXT 0DTE: TODAY      ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ AI: Positive gamma regime but data degraded — UW feed down since 14:28. Confidence        ║
║     reduced. Levels from FlashAlpha still valid. Proceed with caution.                    ║
║     [HAIKU · CACHED · $0.000]                                                             ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ DEEP6: bias_score=+2  bias_label=LEAN_BULL  confidence=0.48  [CONNECTED]                  ║
╠════════════════════════════════════════════════════════════════════════════════════════════╣
║ FA:● MAS:● UW:✗  │  $1.92 today  │  ⟳ 28s  │  14:32:45 ET                               ║
╚════════════════════════════════════════════════════════════════════════════════════════════╝
```

### DEGRADED Color Map

| Element                    | Color         | Hex       |
|----------------------------|---------------|-----------|
| STALE badge                | Amber         | `#FFB000` |
| Direction arrows ▲▲▲       | Amber         | `#FFB000` |
| BULLISH verdict (degraded) | Amber         | `#FFB000` |
| Confidence bar (reduced)   | Amber         | `#FFB000` |
| Grade B-                   | Amber         | `#FFB000` |
| --- (stale) placeholders   | Amber         | `#FFB000` |
| NQ price + positive delta  | Bright green  | `#00FF41` |
| Valid level values          | Bright green  | `#00FF41` |
| GEX positive (still valid) | Bright green  | `#00FF41` |
| NET HEDGE: PARTIAL         | Amber         | `#FFB000` |
| [CACHED] badge             | Amber         | `#FFB000` |
| UW:✗ (failed source)       | Red           | `#FF4444` |
| FA:● MAS:● (healthy)       | Bright green  | `#00FF41` |
| Section headers            | Dim green     | `#00AA00` |
| AI narrative text          | Dim green     | `#00AA00` |
| Box borders                | Dark green    | `#006600` |
| Background                 | Near-black    | `#0A0A0A` |

---

## Color System Summary

| Role             | Name         | Hex       | Usage                                |
|------------------|--------------|-----------|--------------------------------------|
| Primary data     | Bright green | `#00FF41` | Values, bullish, positive numbers    |
| Labels/metadata  | Dim green    | `#00AA00` | Headers, AI text, descriptions       |
| Borders/seps     | Dark green   | `#006600` | Box chars, separators, bar empty     |
| Bearish/error    | Red          | `#FF4444` | Bearish, negative values, failures   |
| Warning/stale    | Amber        | `#FFB000` | STALE badge, degraded, warnings      |
| Background       | Near-black   | `#0A0A0A` | Terminal background                  |

## Layout Dimensions

- **Width**: 92 content chars + 2 border chars = 94 chars total (within 96-col limit)
- **Height per mockup**: 30 lines (well within 55-line budget)
- **Line budget breakdown**:
  - Header: 2 lines (border + title)
  - Verdict: 3 lines (border + 2 content)
  - Levels: 5 lines (border + 4 content)
  - Dealer: 4 lines (border + 3 content)
  - Flow: 2 lines (border + 1 content)
  - Vanna/Charm: 2 lines (border + 1 content)
  - 0DTE: 2 lines (border + 1 content)
  - Narrative: 4 lines (border + 3 content)
  - DEEP6 Bias: 2 lines (border + 1 content)
  - Footer: 3 lines (border + 1 content + closing border)
  - **Total: 29 lines**

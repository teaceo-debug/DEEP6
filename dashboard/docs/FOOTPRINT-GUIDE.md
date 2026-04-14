# DEEP6 Footprint Chart — Trader's Guide

## 1. What a Footprint Chart Is

A footprint chart is a candlestick variant that replaces the plain OHLC body with a per-price-level breakdown of volume traded on the bid versus the ask. Instead of seeing only that a bar moved from 19480 to 19485, you see *exactly how much volume traded at each tick* and *who was the aggressor* — buyer lifting the offer, or seller hitting the bid. This raw order-flow data is the closest thing to watching the auction unfold in real time: you can observe when large sell orders are absorbed without price moving, when buyers exhaust themselves after a run, and where the market transacted the most total volume. Every institutional order-flow platform — Sierra Chart, ATAS, Bookmap, Jigsaw — is built on this foundation.

---

## 2. How to Read a Numbers Bar Cell

Each row in a bar corresponds to a single tick on the NQ ladder (0.25 point increments). The row shows two numbers separated by an `×`:

```
  BID × ASK
  247 × 89
```

- **Left number (bid volume):** contracts traded where a seller hit the passive bid. These are aggressive sell orders. When this number is large, sellers are entering the market at that price.
- **Right number (ask volume):** contracts traded where a buyer lifted the passive offer. These are aggressive buy orders. When this number is large, buyers are entering at that price.

The cell reads like a score: bid on the left, ask on the right. A row reading `247 × 89` means sellers were dominant at that level — 247 contracts traded on the bid side versus 89 on the ask. A row reading `12 × 380` means aggressive buyers dominated.

---

## 3. Color Meanings

Cell backgrounds carry imbalance and context information at a glance:

| Color | Meaning | Trigger |
|---|---|---|
| **Red** (`#ff2e63`) | Sell imbalance | Bid volume > 3× ask volume at that row |
| **Green** (`#00ff88`) | Buy imbalance | Ask volume > 3× bid volume at that row |
| **Amber** (`#ffd60a`) | POC — Point of Control | The single row with the highest total volume (bid + ask) in the bar |
| **Grey shades** | Neutral | Total volume at that row tinted proportionally — darker = more total volume |

The 3× threshold is an industry standard for calling a row "imbalanced." A ratio below 3× means both sides are trading meaningfully and there is no clear aggressor dominance at that level.

Imbalanced cells render with a **bloom effect** — a faint glow around the bar — so the eye finds them instantly without scanning numbers.

---

## 4. Stacked Imbalance Runs

When three or more consecutive rows in a bar all show the *same direction* of imbalance, DEEP6 draws a vertical line along the imbalance side spanning the entire run:

- **Lime vertical line** (`#a3ff00`) = stacked imbalance run of 3+ rows, either direction
- Runs of 4+ consecutive rows render as a **solid** line; 3-row runs render **dashed**

What this means in practice:

- **Stacked sell imbalances (red rows, lime line):** Large aggressive selling across a band of prices. This often signals either a breakout push lower, or — if price holds — an absorption zone where buyers are quietly taking the other side.
- **Stacked buy imbalances (green rows, lime line):** Aggressive buying across a band. Same dual read: momentum push higher, or exhaustion if price stalls.

A stacked run is not a directional signal by itself — it is a flag that says *something structural happened here*. Context from delta, POC placement, and zone confluence resolves the direction.

---

## 5. Delta Footer

Beneath each bar is a thin horizontal bar labeled with the bar's **delta** value:

```
delta = total ask volume − total bid volume
```

- **Positive delta (green bar):** Net buying pressure in the bar. More contracts executed on the ask than the bid.
- **Negative delta (red bar):** Net selling pressure. The `−` sign uses a proper Unicode minus (−) for clean display.
- **Near-zero delta:** Mixed auction; neither side dominated.

Delta tells you the *net* story of the bar. Combined with price direction it reveals divergences: a bar that closed higher on *negative* delta means sellers were active but buyers won the tape anyway — often a sign of absorption.

---

## 6. Volume Profile Sidebar

The sidebar on the right edge of the chart is a **cumulative volume profile** across all visible bars. Each price level shows a horizontal histogram bar split by color:

- **Red portion (left):** Total bid volume transacted at that price across all visible bars
- **Green portion (right):** Total ask volume transacted at that price

The wider the combined bar, the more *total activity* at that level across the session. This gives you the same information as a traditional volume profile but decomposed by side — you can see not just *where* volume concentrated but *how* it was distributed between buyers and sellers.

---

## 7. POC vs VAH/VAL

These are volume-profile terms used in the Zone List panel and the chart overlays:

| Term | Definition |
|---|---|
| **POC** (Point of Control) | The single price level with the highest total volume in the profile. This is where the market found the most two-sided agreement. |
| **VAH** (Value Area High) | The upper boundary of the Value Area — the range containing 70% of total volume. Price tends to gravitate back to this range. |
| **VAL** (Value Area Low) | The lower boundary of the Value Area. |
| **HVN** (High Volume Node) | A price cluster with abnormally high volume — strong support/resistance. |
| **LVN** (Low Volume Node) | A price gap in the profile where little volume traded — price tends to travel through LVNs quickly. |

On the chart, POC is marked with an **amber glow line** across the bar. VAH/VAL appear as dashed lines in the zone overlay. LVNs are cyan-outlined bands; HVNs are amber-outlined.

---

## 8. Signal Markers

When DEEP6's signal engine fires on a bar, a vertical line extends upward from the top of the bar, terminating in a small colored square:

| Marker color | Signal tier | Meaning |
|---|---|---|
| **Lime** (`#a3ff00`) | TYPE_A | High-confluence signal — 3+ signal categories agree (absorption + exhaustion + at least one confirming engine) |
| **Amber** (`#ffd60a`) | TYPE_B | Mid-confidence — 2 categories agree |
| **Cyan** (`#00d9ff`) | TYPE_C | Single-category alert — watch but do not act blindly |

No text labels appear on the chart. Full signal details — engine agreement, Kronos bias, GEX regime, narrative — appear in the Signal Feed panel to the right. The marker on the bar is deliberately minimal: its job is to locate the signal in time, not explain it.

---

## 9. Tips for Reading Orderflow

**The bar is a debate, not a verdict.** A bullish bar closing at the high says *buyers won*, but the footprint tells you *how easily* they won. If the bar closed up on stacked sell imbalances with negative delta, buyers overcame a lot of selling — that is a very different context than a clean buy sweep with no opposing volume.

**Absorption is the alpha signal.** When a zone (POC, VAH, HVN) receives multiple bars with heavy sell imbalances at and below the level, but price does not fall, someone is absorbing the supply. The footprint will show red-heavy cells stacked at support while price holds. When absorption completes, the reversal tends to be sharp.

**Delta divergence precedes reversals.** If a bar makes a new high but the delta is the most negative of the session, exhaustion is likely. Buyers are no longer winning the auction despite the headline price print. Watch for a TYPE_B or TYPE_A signal in the next 1-3 bars.

**Stacked imbalances near a zone confirm, not signal.** A stacked sell run 10 ticks away from a key level is noise. The same stacked sell run *at* the POC, with price holding, is absorption. Always anchor the footprint read to a zone.

**The POC is the fair value anchor.** In balanced sessions, price rotates around the POC. Bars that develop well above the session POC with thin, two-sided volume are extended; bars that develop at or near the POC with heavy, imbalanced volume are at the heart of the auction. Know where the POC is before reading any individual bar.

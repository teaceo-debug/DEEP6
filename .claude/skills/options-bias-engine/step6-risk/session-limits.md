# Step 6: Risk — Session Limits

## Overview

Session limits are the macro-level risk controls that govern the entire trading day, not individual trades. Where kill switches (kill-switches.md) evaluate each trade in isolation, session limits evaluate the cumulative state of the session. They answer questions like: How much have I lost today? How many trades have I taken? Am I overtrading? Am I giving back a winning session?

These rules exist because individual trade quality is not the only risk. Overtrading, revenge trading, and failing to protect profits are session-level failure modes that can turn a good system into a losing one.

---

## Daily Loss Limit

**Rule:** Stop trading for the session when total session loss reaches the daily loss limit.

**Threshold:** 50 NQ points total session loss OR 2% of account equity, whichever is smaller.

At $20/point per NQ contract, 50 NQ points equals:
- 1 contract: $1,000
- 2 contracts: $2,000 (but this is the total session loss, not per-trade)
- 5 contracts: $5,000

For a $50,000 account: 2% = $1,000. At 1 NQ contract, this is 50 points. At 2 NQ contracts, this is 25 points. The 2% rule is binding at larger position sizes.

**Implementation:**
```python
class DailyLossLimit:
    def __init__(self, account_equity: float, max_pts: float = 50.0):
        self.account_equity = account_equity
        self.max_pts = max_pts
        self.max_dollars = account_equity * 0.02
        self.session_pnl_pts = 0.0
        self.session_pnl_dollars = 0.0
    
    def record_trade(self, pnl_pts: float, contracts: int):
        self.session_pnl_pts += pnl_pts
        self.session_pnl_dollars += pnl_pts * contracts * 20
    
    def is_limit_hit(self) -> tuple[bool, str]:
        pts_limit_hit = self.session_pnl_pts <= -self.max_pts
        dollar_limit_hit = self.session_pnl_dollars <= -self.max_dollars
        if pts_limit_hit:
            return True, f"Daily loss limit: {self.session_pnl_pts:.1f} pts (limit: -{self.max_pts})"
        if dollar_limit_hit:
            return True, f"Daily loss limit: ${self.session_pnl_dollars:.0f} (limit: -${self.max_dollars:.0f})"
        return False, f"Session P&L: {self.session_pnl_pts:.1f} pts / ${self.session_pnl_dollars:.0f}"
```

**When the limit is hit:** No more trades for the session. Close any open positions. Log the session result. Do not attempt to "trade back" to breakeven. The daily loss limit is a hard stop, not a suggestion.

**Why 50 points:** 50 NQ points is a meaningful but not catastrophic loss. It represents roughly 0.25% of NQ's value at 20,000. It's large enough to represent a genuinely bad day (not just normal variance) but small enough to preserve capital for future sessions. A trader who loses 50 points on a bad day and stops has preserved 98% of their capital for the next session.

---

## Daily Trade Count Limit

**Rule:** Maximum 8-10 trades per session. Stop taking new trades after reaching the limit.

**Threshold:** 8 trades is the soft limit. 10 trades is the hard limit. Between 8 and 10, only take trades with 4/5 or 5/5 conviction. After 10, no new trades regardless of setup quality.

**Rationale:**

The options bias engine is designed to identify HIGH-QUALITY setups, not to generate constant trade signals. If you're taking 15 trades in a session, you're not being selective. You're overtrading.

Each additional trade beyond the optimal count:
- Increases commission costs (NQ commissions are $4-8 per side, $8-16 round trip)
- Dilutes the edge (the 8th trade of the day is almost always lower quality than the 2nd)
- Increases cognitive load and decision fatigue
- Increases the probability of revenge trading after a loss

The system's edge comes from SELECTIVITY. A 65% win rate on 5 high-quality trades beats a 52% win rate on 15 mediocre trades, both in expected value and in psychological sustainability.

**Tracking:**
```python
class TradeCountLimit:
    SOFT_LIMIT = 8
    HARD_LIMIT = 10
    
    def __init__(self):
        self.trade_count = 0
    
    def record_trade(self):
        self.trade_count += 1
    
    def check_limit(self, conviction: int) -> tuple[bool, str]:
        if self.trade_count >= self.HARD_LIMIT:
            return False, f"Hard trade limit reached: {self.trade_count} trades today"
        if self.trade_count >= self.SOFT_LIMIT and conviction < 4:
            return False, f"Soft limit: {self.trade_count} trades, conviction {conviction}/5 < 4 required"
        return True, f"Trade count: {self.trade_count}"
```

---

## Consecutive Loss Response Protocol

The consecutive loss response is graduated. Each additional consecutive loss triggers a more conservative response.

### 1 consecutive loss: Normal

Re-evaluate the regime and levels. Was the regime correctly identified? Did the level hold as expected? Was the flow reading accurate? No size change. No behavioral change. One loss is within normal variance for any system with a 60-70% win rate.

Log the loss with full context: regime, setup, conviction, entry, stop, exit, what went wrong. This log is the raw material for the weekly review.

### 2 consecutive losses: Reduce and re-verify

Reduce the NEXT trade size by 25% (multiply the final size from position-sizing.md by 0.75).

Re-verify the regime is correctly identified. Two consecutive losses often indicate one of:
- The regime has shifted and the system is still trading the old one
- A specific level (call wall, put wall) is not behaving as expected (may have been rolled or closed)
- The flow signals are noisy today (low-quality day)

Before the next trade, explicitly confirm: Is the regime the same as when the losing trades were taken? If the regime has changed, the losses may be explained by the transition. If the regime is the same, something else is wrong.

### 3 consecutive losses: Stop for the session

As documented in kill-switches.md Gate 8: three consecutive losses triggers a mandatory session stop. No exceptions.

The 25% size reduction from the second consecutive loss does not prevent the third loss from triggering the stop. The stop is based on consecutive loss COUNT, not on whether you reduced size.

---

## Profit Protection Rules

### The 30-point profit protection threshold

After accumulating 30+ NQ points of session profit, tighten stops on all open positions. The goal is to not give back a winning session.

Specifically:
- Any open position with a profit of 10+ NQ points: move stop to breakeven
- Any open position with a profit of 20+ NQ points: move stop to +10 NQ points (lock in half the profit)
- Do not open new positions with stops wider than 10 NQ points (reduces risk of giving back the session gain)

**Why 30 points:** 30 NQ points at $20/point = $600 per contract. This is a meaningful session gain. Giving it back to end the day flat is psychologically damaging and represents a failure of session management. The 30-point threshold triggers conservative behavior to protect the gain.

### The "winning session" mindset shift

Once you're up 30+ points, the session objective changes. You're no longer trying to maximize profit. You're trying to PROTECT the profit while allowing for additional gains. This means:
- Smaller position sizes on new trades
- Tighter stops on existing positions
- Higher conviction threshold for new entries (require 4/5 minimum)
- No new trades in the last 30 minutes of the session

A session that ends +25 points is a success. A session that was +35 points and ended +5 points is a failure of session management, even though it's technically profitable.

---

## Time-Based Rules

### No new trades after 3:45 PM ET

The last 15 minutes of the session (3:45-4:00 PM ET) are dominated by charm flows, end-of-day hedging, and position squaring. These flows are mechanical and often reverse immediately after close. The R:R for new positions in this window is poor.

Exception: Closing existing positions is always allowed. The rule applies to OPENING new positions.

### No new trades 9:30-9:35 AM ET

Covered in kill-switches.md Gate 5. Repeated here for completeness. The opening 5 minutes are untradeable.

### Reduced size 11:30 AM - 1:30 PM ET (midday doldrums)

The midday period is characterized by:
- Low options flow (sweeps and blocks drop significantly)
- Thin DOM depth (market makers reduce size)
- Higher probability of DEAD MARKET classification (Gate 3 in kill-switches.md)
- Choppy, mean-reverting price action with no follow-through

During this window, apply an additional 0.75x size multiplier to all trades. This is on top of the conviction × regime × setup calculation from position-sizing.md.

The midday period is not a no-trade zone. Good setups still occur. But the lower flow quality and thinner book mean the signals are noisier. Smaller size is appropriate.

**Midday size formula:**
```
final_size_midday = final_size × 0.75
```

Applied only between 11:30 AM and 1:30 PM ET.

### Session time context summary

| Time (ET) | Status | Rule |
|-----------|--------|------|
| 9:30-9:35 | Opening noise | NO NEW TRADES (Gate 5) |
| 9:35-11:30 | Morning session | Full rules apply |
| 11:30-1:30 | Midday doldrums | 0.75x size multiplier |
| 1:30-3:45 | Afternoon session | Full rules apply |
| 3:45-4:00 | Close | NO NEW TRADES |

---

## Correlation Limits

**Rule:** Do not hold multiple positions that are effectively the same directional bet at the same level.

### What correlation means here

If you're long 2 NQ contracts from the put wall AND you take another long 1 NQ contract at the same put wall 10 minutes later, you effectively have 3 NQ contracts long at the put wall. This is not two separate trades — it's one trade with 3x the risk.

The system should track:
- Current open positions: direction, entry level, size
- Proposed new position: direction, entry level, size
- If the new position is in the same direction AND within 20 NQ points of an existing position's entry → they're correlated

### Correlation response

If a proposed trade is correlated with an existing open position:
- Do not open the new position if the combined size would exceed the 2% account risk rule
- If the combined size is within the 2% rule, the new position is allowed but counts as adding to the existing position (apply scaling-in rules from position-sizing.md)

### Cross-setup correlation

Two different setups can be correlated if they're both bullish at the same time. Example: Setup 1 (Wall Bounce) long at put wall AND Setup 4 (Vanna Rally) long triggered simultaneously. These are two different setups but both are bullish. The combined position is effectively a 2x long.

In this case, choose the higher-conviction setup and take that position only. Do not double up on the same directional bet even if the setups are technically different.

---

## Weekly Review Cadence

Every Friday after market close, conduct a structured review of the week's trades. This is not optional. The weekly review is how the system learns and adapts.

### Review structure

**Win rate by regime:**
- For each regime (A through G), calculate: trades taken, wins, losses, win rate
- If any regime has a win rate below 40% over 10+ trades, investigate. The regime may be misidentified, or the setup within that regime may not be working.

**Win rate by setup:**
- For each setup (1 through 8), calculate: trades taken, wins, losses, win rate, average win, average loss, R:R
- If any setup has a win rate below 35% over 10+ trades, consider suspending that setup pending investigation.

**Win rate by time of day:**
- Morning (9:35-11:30): win rate
- Midday (11:30-1:30): win rate
- Afternoon (1:30-3:45): win rate
- If midday win rate is significantly lower than morning/afternoon, consider tightening the midday size multiplier further (0.50x instead of 0.75x).

**Data source reliability:**
- Were there any staleness events this week? Which sources went stale and when?
- Did any stale source correlate with losing trades?
- Are the FlashAlpha polls completing within the 3-minute threshold consistently?

**Level reliability:**
- Did the call walls and put walls hold as expected?
- Were there any wall breaks that the system missed (low defense score but the wall held anyway)?
- Were there any wall holds that the system predicted as breaks?

### Adaptation triggers

If the weekly review reveals a consistent failure mode, adapt:

**Regime misidentification:** If Regime D trades are consistently losing, re-examine the regime classification logic. Is the gamma flip level being computed correctly? Is the total GEX sign reliable?

**Setup failure:** If Setup 3 (Gamma Flip Cross) has a 30% win rate over 20 trades, the setup's entry conditions may need tightening. Increase the conviction requirement from 3/5 to 4/5 for that setup.

**Level unreliability:** If put walls are breaking more often than expected, the GEX data may be stale or the proxy (QQQ/NDX for NQ) may be diverging. Investigate the NQ-to-QQQ ratio (nominally 85.7x) for drift.

**Time-of-day pattern:** If afternoon trades are consistently losing, consider stopping new entries after 2:30 PM instead of 3:45 PM.

### Review log format

```
WEEKLY REVIEW: [Date Range]

OVERALL: X trades, Y wins (Z%), avg win W pts, avg loss V pts, R:R = W/V

BY REGIME:
  A: X trades, Y% win rate
  B: X trades, Y% win rate
  C: X trades, Y% win rate
  D: X trades, Y% win rate
  E: X trades, Y% win rate
  F: X trades, Y% win rate

BY SETUP:
  1 (Wall Bounce): X trades, Y% win rate, avg R:R Z
  2 (Wall Break): X trades, Y% win rate, avg R:R Z
  [...]

BY TIME:
  Morning: X trades, Y% win rate
  Midday: X trades, Y% win rate
  Afternoon: X trades, Y% win rate

DATA ISSUES:
  [List any staleness events, API failures, data anomalies]

LEVEL RELIABILITY:
  Call walls held: X/Y (Z%)
  Put walls held: X/Y (Z%)
  Gamma flip crossings predicted: X/Y (Z%)

ADAPTATION DECISIONS:
  [Any changes to thresholds, setup requirements, or time rules]
```

---

## Session State Machine

The session has distinct states that determine which rules apply:

```
PRE_MARKET → OPENING_NOISE → ACTIVE → MIDDAY → ACTIVE → CLOSING → POST_MARKET
                                ↓
                          LOSS_STOPPED (if 3 consecutive losses or daily limit hit)
                                ↓
                          PROFIT_PROTECTED (if session P&L > 30 pts)
```

**PRE_MARKET (before 9:30 AM ET):** No trades. Prepare the morning setup narrative. Load FlashAlpha data. Identify key levels for the day.

**OPENING_NOISE (9:30-9:35 AM ET):** No new trades. Monitor the open. Note gap direction if > 2%.

**ACTIVE (9:35-11:30 AM and 1:30-3:45 PM ET):** Full rules apply. All eight kill switches evaluated per trade.

**MIDDAY (11:30 AM-1:30 PM ET):** Active rules plus 0.75x size multiplier. Higher conviction threshold recommended.

**CLOSING (3:45-4:00 PM ET):** No new trades. Manage existing positions. Close anything with a profit.

**LOSS_STOPPED:** Triggered by 3 consecutive losses or daily loss limit. No new trades for the remainder of the session. Log and review.

**PROFIT_PROTECTED:** Triggered when session P&L > 30 NQ points. Tighter stops, smaller sizes, higher conviction threshold for new entries.

States can overlap: PROFIT_PROTECTED + MIDDAY = 0.75x size multiplier AND tighter stops AND 4/5 minimum conviction.

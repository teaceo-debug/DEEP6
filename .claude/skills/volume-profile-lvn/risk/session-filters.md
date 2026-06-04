# Session and Time-of-Day Filters for LVN Trades

Not all hours are equal. An LVN that's structurally valid at 11:00 ET is a completely different animal at 8:45 ET or 15:45 ET. Session filters aren't about being selective for its own sake. They're about trading when the conditions that make LVN setups work are actually present.

---

## RTH vs Overnight

The volume profile is only as good as the participation behind it. Overnight sessions have a fraction of RTH volume, which means LVN zones built from overnight data are often artifacts of thin trading rather than genuine structural gaps.

| Characteristic | RTH (9:30-16:00 ET) | Overnight (16:00-9:30 ET) |
|---|---|---|
| Volume | 80-90% of total | 10-20% |
| Institutional presence | Heavy | Light (Asian/European desks) |
| LVN reliability | High (structural) | Low (time-of-day artifact) |
| Profile quality | Full participation | Sparse, misleading |
| Spread | Tight (1-2 ticks NQ) | Wider (2-4+ ticks NQ) |
| Best for | All LVN setups | Gap-fill setup only |

Build your primary profile from RTH data. The overnight profile is a separate tool, used specifically for gap-fill analysis and detecting overnight inventory imbalances. Don't mix them.

---

## Time-of-Day Windows (NQ, Eastern Time)

| Window | Time | Quality | Notes |
|---|---|---|---|
| Pre-market | 8:00-9:30 | Avoid | Low volume, wide spreads, fakeouts common |
| Opening rotation | 9:30-10:00 | Avoid | Chaotic, IB forming, too many fakeouts |
| IB completion | 10:00-10:30 | Caution | IB established; identify LVN zones but wait for confirmation |
| Prime window | 10:30-14:00 | Optimal | Peak institutional participation, cleanest LVN structures, highest win rates |
| Afternoon | 14:00-15:00 | Declining | Volume drops, LVN less reliable, 0DTE effects increasing |
| Final hour | 15:00-16:00 | Special | 0DTE gamma extreme; use lvn-0dte-gamma rules; reduce size 50% |
| After hours | 16:00-17:00 | Avoid | Settlement, thin book, erratic |

The prime window from 10:30 to 14:00 is where the system performs best. Institutional desks are active, spreads are tight, and LVN zones that were identified pre-market tend to hold or break cleanly. Outside this window, the same setup has a meaningfully lower win rate.

The final hour is a special case, not a blanket avoid. 0DTE gamma effects can amplify LVN reactions dramatically, but they can also cause violent reversals. If you trade the final hour, cut size in half and apply the 0DTE gamma rules from the companion file.

---

## Day-of-Week Filters

| Day | Quality | Notes |
|---|---|---|
| Monday | Moderate | Weekend gap dynamics; composite profile may shift |
| Tuesday | Good | Full institutional participation typically resumes |
| Wednesday | Good | FOMC days are exceptions: avoid LVN setups 30 min before/after announcement |
| Thursday | Good | Best day for gap-fill setups (pre-Friday positioning) |
| Friday | Caution | Weekly options expiration; 0DTE amplification all day; reduce size |

Monday's composite profile often needs recalibration. If price gapped significantly over the weekend, the prior week's LVN map may no longer reflect current structure. Rebuild or verify before trading.

Friday is the most dangerous day for LVN setups. Weekly options expiration creates 0DTE gamma effects from the open, not just the final hour. Treat all of Friday like the final hour: reduced size, tighter filters.

---

## Event Filters: Do Not Trade LVN Setups

These windows are hard stops. No LVN setup is worth the binary risk of a macro event:

- 30 minutes before and after any FOMC rate decision
- 15 minutes before and after CPI, PPI, or NFP releases
- During major earnings that move NQ (AAPL, MSFT, NVDA, AMZN) if the report is pre-market or intraday
- First 30 minutes after an exchange halt resumes

The issue isn't that LVN setups fail during events. It's that the fills become unpredictable. Slippage through an LVN during a news spike can be 5-10x the normal range. The structural logic of the setup is irrelevant when the market is repricing on new information.

---

## Gamma Regime Time Switching

The gamma regime that governs LVN behavior shifts during the day as 0DTE options gain dominance.

- **Before 14:00 ET:** Use full-chain GEX for regime determination. The full options chain reflects institutional positioning across all expirations.
- **After 14:00 ET:** Switch to 0DTE gamma flip if 0DTE represents more than 50% of total GEX. At this point, the 0DTE flow is driving intraday price behavior more than the full chain.
- **Expiration day (any):** Monitor 0DTE from the open. On expiration days, 0DTE gamma can dominate from 9:30 onward.

This matters for LVN setups because the gamma regime determines whether price will pin, trend, or reverse at key levels. A positive full-chain GEX environment with negative 0DTE GEX after 14:00 is a mixed signal. Reduce size or wait for clarity.

---

## Session Profile Best Practices

**RTH profile:** Build starting at 9:30, not from overnight. The overnight session distorts the distribution and creates false LVN zones that don't reflect institutional structure.

**Overnight profile:** Keep separate. Use it only for gap-fill analysis and inventory detection. Never use overnight LVN zones as primary trade locations during RTH.

**Weekly composite:** Aggregate Monday through Friday RTH sessions only. Weight the most recent day at 1.5x to reflect current market structure more accurately than equal-weighted composites.

**Stale profile rule:** If the VP profile is more than 2 sessions old and price has moved more than 100 NQ points, rebuild from scratch. A stale profile is worse than no profile. It gives you false confidence in LVN zones that no longer exist structurally.

---

## Pre-Market Checklist

Run this before the open, every day. It takes 5-10 minutes and prevents the most common LVN trading mistakes.

- [ ] Mark prior day's POC, VAH, and VAL from the RTH profile
- [ ] Identify LVN zones on the 5-day composite
- [ ] Mark overnight gaps and any overnight LVN zones (for gap-fill analysis only)
- [ ] Check gamma regime (positive or negative) from FlashAlpha
- [ ] Note naked VPOCs from the prior 5 sessions
- [ ] Check the economic calendar for event filters today
- [ ] Determine session plan: which setups are valid given today's regime, events, and day of week?

The last item is the most important. Going into the session with a specific plan ("today I'm watching for LVN rejection at 19,450 if we open above it, and I'm avoiding the final hour because it's Friday") is categorically different from watching the chart and reacting. The checklist forces the plan.

# Stop Loss Placement

## The ATR Baseline

Before choosing a method, establish your volatility baseline. SL should fall within **10-20% of average daily volatility (ATR)**.

Examples:
- EUR/USD ATR = 100 pips → target SL of 10-20 pips
- NQ ATR = 200 points → target SL of 20-40 points

If your chosen method produces a SL outside this range, either skip the trade or fall back to the fixed SL within the acceptable range. A logically placed SL that's too wide destroys your R:R. A SL that's too tight gets stopped out by noise.

## Method 1: Fixed Stop Loss

Set the same SL size for every trade. Simple, consistent, easy to backtest.

**When to use:** When you want consistency above all else, or when you're still learning and don't want SL placement to be another variable.

**Drawback:** Doesn't adapt to the specific setup. A tight S/R zone might warrant a tighter SL; a wide zone might need more room.

**Maintenance:** Review periodically. If volatility changes dramatically (e.g., a regime shift in NQ from 150-point days to 300-point days), adjust your fixed SL accordingly.

## Method 2: High/Low of the S/R Area

Place SL at the structural extreme of the S/R zone you're trading.

- **Long trade at support:** SL goes at the low of the support zone
- **Short trade at resistance:** SL goes at the high of the resistance zone

**Logic:** If price breaks through the S/R zone that justified your entry, the setup is invalidated. You don't need to be in the trade anymore. The zone's extreme is the natural invalidation point.

**How to identify the zone boundary:** Use the 30-minute Volume cell content chart. The S/R zone spans from the heaviest volume cluster to the edge of the surrounding low-volume area. The low of the zone (for longs) is where volume drops off sharply below the cluster.

## Method 3: Low Volume Area Behind Heavy Volume

Place SL in the thin/low-volume zone on the far side of the heavy volume area.

**Logic:** Heavy volume = strong S/R. If price breaks through heavy volume and enters the low-volume zone behind it, the move has enough momentum to keep going. You're not fighting a temporary pullback anymore — you're fighting a trend. Get out.

**How to identify:** On the 30-minute Volume chart, find the heavy volume cluster (thick bars). Behind it (below for longs, above for shorts) there's typically a thin area where bars are noticeably shorter. That thin area is your SL zone.

**Advantage over Method 2:** More precise. Instead of placing SL at the structural high/low, you're placing it where the volume structure actually breaks down. Often gives a tighter SL with the same logical invalidation.

## Which Method to Use

| Situation | Recommended Method |
|-----------|-------------------|
| New to OF trading, want consistency | Fixed SL |
| Clear S/R zone with defined boundaries | Method 2 or 3 |
| S/R zone is wide, need tighter SL | Method 3 |
| Calculated SL from Method 2/3 is outside ATR range | Fall back to Fixed SL |

## Chart Setup for Methods 2 and 3

Both require the **30-minute chart with Volume cell content** (total volume, grey shading). The volume histogram on each footprint bar shows you exactly where volume was heavy and where it was thin. You're reading the horizontal distribution of volume within each bar to find the cluster and the thin zone behind it.

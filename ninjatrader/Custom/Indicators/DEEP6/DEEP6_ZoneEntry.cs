// DEEP6_ZoneEntry — Institutional zones + exhaustion wick entry signals
//
// Detects 15m Supply / Demand / RBR / DBD zones (3-bar pattern, hardcoded).
// Fires an entry arrow when a 1m bar touches the zone's proximal edge with
// an exhaustion wick (EXH-02 proxy) and closes back outside the zone.
//
// ONE setting: WickMinPct (default 0.35)
//   — the fraction of the bar's range the wick into the zone must represent.
//
// Visual: thin zone box + bright proximal-edge line + arrow on signal bar.
// Deploy to: %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DEEP6_ZoneEntry : Indicator
    {
        // ── Single user-facing setting ───────────────────────────────────────────
        [NinjaScriptProperty]
        [Range(0.10, 0.80)]
        [Display(Name        = "Wick Min %",
                 Description = "Wick into zone must be ≥ this fraction of bar range (0.35 = 35%)",
                 Order        = 0,
                 GroupName    = "Entry Signal")]
        public double WickMinPct { get; set; } = 0.35;

        // ── Zone record ──────────────────────────────────────────────────────────
        private enum ZoneKind { Supply, Demand, RBR, DBD }

        private class Zone
        {
            public ZoneKind Kind;
            public double   Top, Bot;       // zone rectangle bounds
            public double   Proximal;       // near edge (entry side)
            public double   Distal;         // far edge (stop side)
            public bool     IsBull;         // true → BUY, false → SELL
            public DateTime StartTime;      // 15m confirmation bar timestamp
            public DateTime ValidAfter;     // skip signals until next 15m bar
            public bool     Active      = true;
            public bool     EntryFired  = false;
            public int      TouchCount  = 0;
            public string   RectTag, LineTag;
        }

        private readonly List<Zone> _zones = new List<Zone>();
        private int  _zoneBip;              // 0 = single series, 1 = dual series

        // ── Hardcoded constants ──────────────────────────────────────────────────
        private const double SmallBodyRatio  = 0.50;   // base body ≤ 50% of neighbours
        private const int    MinZoneTicks    = 4;      // minimum zone height
        private const int    MaxTouches      = 2;      // zone expires after N touches
        private const int    CloseBufTicks   = 2;      // close must be ≥ N ticks outside proximal
        private const int    MinEntryTicks   = 8;      // zone must be ≥ N ticks tall for entry
        private const int    RightOffsetBars = -3;     // extend boxes 3 bars right of current

        // ── Colors (frozen static brushes) ──────────────────────────────────────
        private static readonly Brush _sellBrush = MkBrush(220,  60,  60);   // crimson
        private static readonly Brush _buyBrush  = MkBrush( 50, 160, 220);   // dodger-blue
        private static readonly Brush _sellArrow = MkBrush(255,  80,  80);   // bright red
        private static readonly Brush _buyArrow  = MkBrush( 80, 230,  80);   // bright green
        private static readonly Brush _transparent;

        static DEEP6_ZoneEntry()
        {
            var t = new SolidColorBrush(Colors.Transparent);
            t.Freeze();
            _transparent = t;
        }

        private static Brush MkBrush(byte r, byte g, byte b)
        {
            var br = new SolidColorBrush(Color.FromRgb(r, g, b));
            br.Freeze();
            return br;
        }

        // ── Lifecycle ────────────────────────────────────────────────────────────
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name                      = "DEEP6 Zone Entry";
                Description               = "15m zones + exhaustion-wick entry arrows";
                Calculate                 = Calculate.OnBarClose;
                IsOverlay                 = true;
                IsSuspendedWhileInactive  = true;
            }
            else if (State == State.Configure)
            {
                bool alreadyFifteen = BarsPeriod.BarsPeriodType == BarsPeriodType.Minute
                                      && BarsPeriod.Value >= 15;
                if (alreadyFifteen)
                {
                    _zoneBip = 0;
                }
                else
                {
                    AddDataSeries(BarsPeriodType.Minute, 15);
                    _zoneBip = 1;
                }
            }
            else if (State == State.DataLoaded)
            {
                RemoveDrawObjects();
                _zones.Clear();
            }
        }

        // ── Bar update dispatch ───────────────────────────────────────────────────
        protected override void OnBarUpdate()
        {
            if (BarsInProgress == _zoneBip)
                TryDetectZone();

            if (BarsInProgress == 0)
            {
                ProcessZones();
                RedrawZones();
            }
        }

        // ── Zone detection  (runs on 15m series) ─────────────────────────────────
        private void TryDetectZone()
        {
            int bip = _zoneBip;
            if (CurrentBars[bip] < 2) return;

            double pO = Opens[bip][2],  pC = Closes[bip][2];
            double bO = Opens[bip][1],  bC = Closes[bip][1];
            double bH = Highs[bip][1],  bL = Lows[bip][1];
            double nO = Opens[bip][0],  nC = Closes[bip][0];

            double pb = Math.Abs(pC - pO);
            double bb = Math.Abs(bC - bO);
            double nb = Math.Abs(nC - nO);
            double br = bH - bL;

            if (pb <= 0 || nb <= 0) return;

            bool svp  = bb <= SmallBodyRatio * pb;
            bool svn  = bb <= SmallBodyRatio * nb;
            bool tall = br >= MinZoneTicks * TickSize;
            if (!svp || !svn || !tall) return;

            bool pG = pC > pO, pR = pC < pO;
            bool bR = bC < bO;
            DateTime ts = Times[bip][0];

            double nBodyMax = Math.Max(nO, nC);
            double nBodyMin = Math.Min(nO, nC);

            // Supply — big green → small red base → next stays under base high
            if (pG && bR && nBodyMax <= bH + 1e-9)
                AddZone(bH, bC, false, ZoneKind.Supply, ts);

            // Demand — big red → small green base → next stays above base low
            if (pR && !bR && nBodyMin >= bL - 1e-9)
                AddZone(bC, bL, true, ZoneKind.Demand, ts);

            // RBR — big green → small base → next breaks above base high
            if (pG && nBodyMax > bH + 1e-9)
                AddZone(bH, bL, true, ZoneKind.RBR, ts);

            // DBD — big red → small base → next breaks below base low
            if (pR && nBodyMin < bL - 1e-9)
                AddZone(bH, bL, false, ZoneKind.DBD, ts);
        }

        private void AddZone(double top, double bot, bool isBull, ZoneKind kind, DateTime ts)
        {
            if (top - bot < MinZoneTicks * TickSize) return;

            foreach (var z in _zones)
            {
                if (!z.Active || z.Kind != kind) continue;
                if (bot <= z.Top + 1e-9 && top >= z.Bot - 1e-9) return;
            }

            string id = $"{kind}_{ts:yyyyMMddHHmm}";
            _zones.Add(new Zone
            {
                Kind       = kind,
                Top        = top,
                Bot        = bot,
                Proximal   = isBull ? top : bot,
                Distal     = isBull ? bot : top,
                IsBull     = isBull,
                StartTime  = ts,
                ValidAfter = ts.AddMinutes(15),
                RectTag    = "ZR_" + id,
                LineTag    = "ZL_" + id,
            });
        }

        // ── Entry signal check  (runs on primary series each bar) ─────────────────
        private void ProcessZones()
        {
            double h = High[0], l = Low[0], o = Open[0], c = Close[0];
            double range = h - l;
            if (range < TickSize) return;

            double bodyMax   = Math.Max(o, c);
            double bodyMin   = Math.Min(o, c);
            double upperWick = h - bodyMax;
            double lowerWick = bodyMin - l;
            double buf       = CloseBufTicks * TickSize;

            for (int i = _zones.Count - 1; i >= 0; i--)
            {
                Zone z = _zones[i];
                if (!z.Active) continue;

                // Invalidation: body closes through the distal edge
                if (!z.IsBull && bodyMax > z.Distal + 1e-9)
                {
                    z.Active = false;
                    RemoveDrawObject(z.RectTag);
                    RemoveDrawObject(z.LineTag);
                    continue;
                }
                if (z.IsBull && bodyMin < z.Distal - 1e-9)
                {
                    z.Active = false;
                    RemoveDrawObject(z.RectTag);
                    RemoveDrawObject(z.LineTag);
                    continue;
                }

                // Touch count — expires after MaxTouches
                bool entersZone = h >= z.Bot - 1e-9 && l <= z.Top + 1e-9;
                if (entersZone)
                {
                    z.TouchCount++;
                    if (z.TouchCount > MaxTouches)
                    {
                        z.Active = false;
                        RemoveDrawObject(z.RectTag);
                        RemoveDrawObject(z.LineTag);
                        continue;
                    }
                }

                if (z.EntryFired) continue;
                if (Time[0] <= z.ValidAfter) continue;
                if (Math.Abs(z.Distal - z.Proximal) < MinEntryTicks * TickSize) continue;

                // Exhaustion-wick check at proximal edge
                if (!z.IsBull)
                {
                    // SELL — wick pushes UP into supply zone, close below proximal
                    bool touched = h >= z.Proximal - 1e-9;
                    bool wick    = (upperWick / range) >= WickMinPct;
                    bool closed  = c < z.Proximal - buf;
                    if (!touched || !wick || !closed) continue;

                    z.EntryFired = true;
                    Draw.ArrowDown(this, "E_" + z.RectTag, true, 0,
                        h + 2 * TickSize, _sellArrow);
                }
                else
                {
                    // BUY — wick pushes DOWN into demand/RBR zone, close above proximal
                    bool touched = l <= z.Proximal + 1e-9;
                    bool wick    = (lowerWick / range) >= WickMinPct;
                    bool closed  = c > z.Proximal + buf;
                    if (!touched || !wick || !closed) continue;

                    z.EntryFired = true;
                    Draw.ArrowUp(this, "E_" + z.RectTag, true, 0,
                        l - 2 * TickSize, _buyArrow);
                }
            }
        }

        // ── Zone drawing  (redraws each bar to extend right edge) ─────────────────
        private void RedrawZones()
        {
            foreach (var z in _zones)
            {
                if (!z.Active) continue;

                int startAgo = PrimaryBarsAgo(z.StartTime);
                if (startAgo < 0) continue;

                Brush color = z.IsBull ? _buyBrush : _sellBrush;

                // Zone rectangle — no outline (Transparent), light fill only
                Draw.Rectangle(this, z.RectTag, false,
                    startAgo, z.Top, RightOffsetBars, z.Bot,
                    _transparent, color, 12);

                // Proximal edge — solid line at the exact entry price
                Draw.Line(this, z.LineTag, false,
                    startAgo, z.Proximal, RightOffsetBars, z.Proximal,
                    color, DashStyleHelper.Solid, 2);
            }
        }

        // ── Helpers ──────────────────────────────────────────────────────────────
        private int PrimaryBarsAgo(DateTime t)
        {
            int idx = BarsArray[0].GetBar(t);
            if (idx >= 0) return CurrentBar - idx;
            for (int i = 0; i <= Math.Min(CurrentBar, 2000); i++)
                if (Times[0][i] <= t) return i;
            return CurrentBar;
        }
    }
}

#region NinjaScript generated code — do not edit
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6_ZoneEntry[] cacheDEEP6_ZoneEntry;

        public DEEP6_ZoneEntry DEEP6_ZoneEntry(double wickMinPct)
        {
            return DEEP6_ZoneEntry(Input, wickMinPct);
        }

        public DEEP6_ZoneEntry DEEP6_ZoneEntry(ISeries<double> input, double wickMinPct)
        {
            if (cacheDEEP6_ZoneEntry != null)
                foreach (var c in cacheDEEP6_ZoneEntry)
                    if (c != null && Math.Abs(c.WickMinPct - wickMinPct) < 1e-9 && c.EqualsInput(input))
                        return c;
            return CacheIndicator<DEEP6_ZoneEntry>(
                new DEEP6_ZoneEntry { WickMinPct = wickMinPct }, input, ref cacheDEEP6_ZoneEntry);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6_ZoneEntry DEEP6_ZoneEntry(double wickMinPct)
        {
            return indicator.DEEP6_ZoneEntry(Input, wickMinPct);
        }
        public Indicators.DEEP6_ZoneEntry DEEP6_ZoneEntry(ISeries<double> input, double wickMinPct)
        {
            return indicator.DEEP6_ZoneEntry(input, wickMinPct);
        }
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6_ZoneEntry DEEP6_ZoneEntry(double wickMinPct)
        {
            return indicator.DEEP6_ZoneEntry(Input, wickMinPct);
        }
        public Indicators.DEEP6_ZoneEntry DEEP6_ZoneEntry(ISeries<double> input, double wickMinPct)
        {
            return indicator.DEEP6_ZoneEntry(input, wickMinPct);
        }
    }
}
#endregion

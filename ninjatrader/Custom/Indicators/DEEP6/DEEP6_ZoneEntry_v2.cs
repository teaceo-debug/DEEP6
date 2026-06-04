// DEEP6_ZoneEntry_v2 — 15m + optional 5m zones, wick exhaustion entry arrows
//
// Extends v1 with a Show5mZones toggle.  Both timeframes share the same
// wick-rejection entry model (WickMinPct).
//
// Visual hierarchy — immediately tells you which TF a zone belongs to:
//   15m zones: solid proximal line (width 2), fill opacity 12
//    5m zones: dashed proximal line (width 1), fill opacity 7
// Both use the same crimson (sell) / blue (buy) palette.
//
// Settings:
//   WickMinPct  — wick fraction threshold for entry (default 0.35)
//   Show5mZones — detect and show 5m zones in addition to 15m (default true)
//
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
    public class DEEP6_ZoneEntry_v2 : Indicator
    {
        // ── Settings ─────────────────────────────────────────────────────────────
        [NinjaScriptProperty]
        [Range(0.10, 0.80)]
        [Display(Name        = "Wick Min %",
                 Description = "Wick into zone must be ≥ this fraction of bar range (0.35 = 35%)",
                 Order        = 0,
                 GroupName    = "Entry Signal")]
        public double WickMinPct { get; set; } = 0.35;

        [NinjaScriptProperty]
        [Display(Name        = "Show 5m Zones",
                 Description = "Detect and show 5-minute zones alongside the 15-minute zones",
                 Order        = 1,
                 GroupName    = "Entry Signal")]
        public bool Show5mZones { get; set; } = true;

        // ── Zone record ──────────────────────────────────────────────────────────
        private enum ZoneKind { Supply, Demand, RBR, DBD }

        private class Zone
        {
            public ZoneKind Kind;
            public double   Top, Bot, Proximal, Distal;
            public bool     IsBull;
            public bool     Is15m;              // true = 15m zone, false = 5m zone
            public DateTime StartTime;
            public DateTime ValidAfter;
            public bool     Active     = true;
            public bool     EntryFired = false;
            public int      TouchCount = 0;
            public string   RectTag, LineTag;
        }

        private readonly List<Zone> _zones = new List<Zone>();

        // Series indices — set during Configure based on chart TF
        private int _5mBip  = -1;   // -1 = disabled
        private int _15mBip =  0;

        // ── Hardcoded constants ──────────────────────────────────────────────────
        private const double SmallBodyRatio  = 0.50;
        private const int    MinZoneTicks    = 4;
        private const int    MaxTouches      = 2;
        private const int    CloseBufTicks   = 2;
        private const int    MinEntryTicks   = 8;
        private const int    RightOffsetBars = -3;

        // ── Colors ───────────────────────────────────────────────────────────────
        private static readonly Brush _sellBrush = MkBrush(220,  60,  60);   // crimson
        private static readonly Brush _buyBrush  = MkBrush( 50, 160, 220);   // blue
        private static readonly Brush _sellArrow = MkBrush(255,  80,  80);
        private static readonly Brush _buyArrow  = MkBrush( 80, 230,  80);
        private static readonly Brush _transparent;

        static DEEP6_ZoneEntry_v2()
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
                Name                     = "DEEP6 Zone Entry v2";
                Description              = "15m + optional 5m zones, wick exhaustion entry arrows";
                Calculate                = Calculate.OnBarClose;
                IsOverlay                = true;
                IsSuspendedWhileInactive = true;
            }
            else if (State == State.Configure)
            {
                int nextBip = 1;
                int chartMin = (BarsPeriod.BarsPeriodType == BarsPeriodType.Minute)
                               ? BarsPeriod.Value : 0;

                // 5m series
                if (Show5mZones)
                {
                    if (chartMin == 5)
                        _5mBip = 0;                                    // primary IS 5m
                    else
                    {
                        AddDataSeries(BarsPeriodType.Minute, 5);
                        _5mBip = nextBip++;
                    }
                }
                else _5mBip = -1;

                // 15m series
                if (chartMin == 15)
                    _15mBip = 0;                                       // primary IS 15m
                else
                {
                    AddDataSeries(BarsPeriodType.Minute, 15);
                    _15mBip = nextBip;
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
            if (_5mBip >= 0 && BarsInProgress == _5mBip && _5mBip != _15mBip)
                DetectZones(_5mBip, is15m: false);

            if (BarsInProgress == _15mBip)
                DetectZones(_15mBip, is15m: true);

            if (BarsInProgress == 0)
            {
                ProcessZones();
                RedrawZones();
            }
        }

        // ── Zone detection ────────────────────────────────────────────────────────
        private void DetectZones(int bip, bool is15m)
        {
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

            bool pG = pC > pO, pR = pC < pO, bR = bC < bO;
            DateTime ts        = Times[bip][0];
            int      skipMins  = is15m ? 15 : 5;
            string   prefix    = is15m ? "15" : "5";

            double nBodyMax = Math.Max(nO, nC);
            double nBodyMin = Math.Min(nO, nC);

            if (pG && bR  && nBodyMax <= bH + 1e-9) AddZone(bH, bC, false, ZoneKind.Supply, ts, is15m, skipMins, prefix);
            if (pR && !bR && nBodyMin >= bL - 1e-9) AddZone(bC, bL, true,  ZoneKind.Demand, ts, is15m, skipMins, prefix);
            if (pG        && nBodyMax >  bH + 1e-9) AddZone(bH, bL, true,  ZoneKind.RBR,    ts, is15m, skipMins, prefix);
            if (pR        && nBodyMin <  bL - 1e-9) AddZone(bH, bL, false, ZoneKind.DBD,    ts, is15m, skipMins, prefix);
        }

        private void AddZone(double top, double bot, bool isBull, ZoneKind kind,
                             DateTime ts, bool is15m, int skipMins, string prefix)
        {
            if (top - bot < MinZoneTicks * TickSize) return;

            foreach (var z in _zones)
            {
                if (!z.Active || z.Kind != kind || z.Is15m != is15m) continue;
                if (bot <= z.Top + 1e-9 && top >= z.Bot - 1e-9) return;
            }

            string id = prefix + "_" + kind + "_" + ts.ToString("yyyyMMddHHmm");
            _zones.Add(new Zone
            {
                Kind       = kind,
                Top        = top,
                Bot        = bot,
                Proximal   = isBull ? top : bot,
                Distal     = isBull ? bot : top,
                IsBull     = isBull,
                Is15m      = is15m,
                StartTime  = ts,
                ValidAfter = ts.AddMinutes(skipMins),
                RectTag    = "ZR_" + id,
                LineTag    = "ZL_" + id,
            });
        }

        // ── Entry signal check ────────────────────────────────────────────────────
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

                // Invalidation
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

                // Touch tracking
                if (h >= z.Bot - 1e-9 && l <= z.Top + 1e-9)
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

                if (!z.IsBull)
                {
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

        // ── Zone drawing ──────────────────────────────────────────────────────────
        private void RedrawZones()
        {
            foreach (var z in _zones)
            {
                if (!z.Active) continue;

                int startAgo = PrimaryBarsAgo(z.StartTime);
                if (startAgo < 0) continue;

                Brush       color   = z.IsBull ? _buyBrush : _sellBrush;
                int         opacity = z.Is15m ? 12 : 7;
                int         width   = z.Is15m ? 2  : 1;
                DashStyleHelper dash = z.Is15m ? DashStyleHelper.Solid : DashStyleHelper.Dash;

                Draw.Rectangle(this, z.RectTag, false,
                    startAgo, z.Top, RightOffsetBars, z.Bot,
                    _transparent, color, opacity);

                Draw.Line(this, z.LineTag, false,
                    startAgo, z.Proximal, RightOffsetBars, z.Proximal,
                    color, dash, width);
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
        private DEEP6_ZoneEntry_v2[] cacheDEEP6_ZoneEntry_v2;

        public DEEP6_ZoneEntry_v2 DEEP6_ZoneEntry_v2(double wickMinPct, bool show5mZones)
        {
            return DEEP6_ZoneEntry_v2(Input, wickMinPct, show5mZones);
        }

        public DEEP6_ZoneEntry_v2 DEEP6_ZoneEntry_v2(ISeries<double> input, double wickMinPct, bool show5mZones)
        {
            if (cacheDEEP6_ZoneEntry_v2 != null)
                foreach (var c in cacheDEEP6_ZoneEntry_v2)
                    if (c != null && Math.Abs(c.WickMinPct - wickMinPct) < 1e-9
                        && c.Show5mZones == show5mZones && c.EqualsInput(input))
                        return c;
            return CacheIndicator<DEEP6_ZoneEntry_v2>(
                new DEEP6_ZoneEntry_v2 { WickMinPct = wickMinPct, Show5mZones = show5mZones },
                input, ref cacheDEEP6_ZoneEntry_v2);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6_ZoneEntry_v2 DEEP6_ZoneEntry_v2(double wickMinPct, bool show5mZones)
            => indicator.DEEP6_ZoneEntry_v2(Input, wickMinPct, show5mZones);

        public Indicators.DEEP6_ZoneEntry_v2 DEEP6_ZoneEntry_v2(ISeries<double> input, double wickMinPct, bool show5mZones)
            => indicator.DEEP6_ZoneEntry_v2(input, wickMinPct, show5mZones);
    }
}

namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        public Indicators.DEEP6_ZoneEntry_v2 DEEP6_ZoneEntry_v2(double wickMinPct, bool show5mZones)
            => indicator.DEEP6_ZoneEntry_v2(Input, wickMinPct, show5mZones);

        public Indicators.DEEP6_ZoneEntry_v2 DEEP6_ZoneEntry_v2(ISeries<double> input, double wickMinPct, bool show5mZones)
            => indicator.DEEP6_ZoneEntry_v2(input, wickMinPct, show5mZones);
    }
}
#endregion

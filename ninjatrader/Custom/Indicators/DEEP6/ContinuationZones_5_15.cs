// ContinuationZones_5_15 â€” RBR/DBD continuation zones on 5m and 15m.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class ContinuationZones_5_15 : Indicator
    {
        private enum ZoneKind
        {
            RBR,
            DBD
        }

        private sealed class Zone
        {
            public ZoneKind Kind;
            public int TimeframeMinutes;
            public string FrameLabel;
            public DateTime BaseTime;
            public string BaseTag;
            public double Top;
            public double Bottom;
            public int TouchCount;
            public int CreationBarPrimary;
            public double OpacityFactor;
            public bool IsActive;
            public bool WasInsideOnPriorBar;
            public int Score;
            public int ScoreFreshness;
            public int ScoreDeparture;
            public int ScoreBase;
            public int ScoreTrend;
            public int ScoreHeight;
        }

        private static class BrushUtil
        {
            public static Brush MakeSolid(Color color)
            {
                var brush = new SolidColorBrush(color);
                if (brush.CanFreeze)
                    brush.Freeze();
                return brush;
            }

            public static Brush Frozen(Brush brush)
            {
                if (brush == null)
                    return null;

                if (brush.IsFrozen)
                    return brush;

                Brush clone = brush.Clone();
                if (clone.CanFreeze)
                    clone.Freeze();
                return clone;
            }
        }

        private readonly List<Zone> zones = new List<Zone>();
        private EMA ema5;
        private EMA ema15;
        private bool primaryIsFiveMinute;
        private bool _isRealTime;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "RBR/DBD continuation zones on 5m and 15m with dissipation and scoring.";
                Name = "ContinuationZones_5_15";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;

                SmallBodyRatio = 0.35;
                MinZoneTicks = 2;
                MinScoreToDisplay = 5;

                MaxAgeBars5m = 300;
                MaxAgeBars15m = 100;
                MaxTouchCount = 3;
                MaxActiveZones = 8;

                FillOpacity = 40;
                ShowLabels = true;
                ShowEntryLines = true;
                RightOffsetBars = -4;

                Show5m = true;
                Show15m = true;

                RBR5 = BrushUtil.MakeSolid(Colors.LimeGreen);
                DBD5 = BrushUtil.MakeSolid(Colors.Crimson);
                RBR15 = BrushUtil.MakeSolid(Colors.Cyan);
                DBD15 = BrushUtil.MakeSolid(Colors.DeepPink);
            }
            else if (State == State.Configure)
            {
                primaryIsFiveMinute = BarsPeriod.BarsPeriodType == BarsPeriodType.Minute && BarsPeriod.Value == 5;
                AddDataSeries(BarsPeriodType.Minute, 15);
            }
            else if (State == State.DataLoaded)
            {
                ema5 = EMA(Closes[0], 50);
                ema15 = EMA(Closes[1], 50);
                zones.Clear();
                RemoveDrawObjects();
                _isRealTime = false;
            }
            else if (State == State.Realtime)
            {
                // History is now complete — enable drawing and do initial render
                _isRealTime = true;
                RemoveDrawObjects();
                RedrawAllZones();
            }
            else if (State == State.Terminated)
            {
                zones.Clear();
            }
        }

        protected override void OnBarUpdate()
        {
            if (!primaryIsFiveMinute)
                return;

            if (BarsInProgress == 0)
            {
                if (Show5m)
                    DetectContinuationOnSeries(0, 5, ema5);

                InvalidateAndTouchZones();
                UpdateZoneLifecycle();

                // Only draw during real-time — history accumulates zones in memory only.
                // _isRealTime is set true in OnStateChange(State.Realtime).
                if (_isRealTime)
                {
                    // Purge stale inactive zones to keep list bounded
                    if (zones.Count > 100)
                        zones.RemoveAll(z => !z.IsActive);

                    RedrawAllZones();
                }
                return;
            }

            if (BarsInProgress == 1 && Show15m)
                DetectContinuationOnSeries(1, 15, ema15);
        }

        private void DetectContinuationOnSeries(int bip, int timeframeMinutes, EMA ema)
        {
            if (CurrentBars[bip] < 52)
                return;

            double prevOpen = Opens[bip][2];
            double prevClose = Closes[bip][2];
            double baseOpen = Opens[bip][1];
            double baseClose = Closes[bip][1];
            double baseHigh = Highs[bip][1];
            double baseLow = Lows[bip][1];
            double nextOpen = Opens[bip][0];
            double nextClose = Closes[bip][0];
            double nextBodyMax = Math.Max(nextOpen, nextClose);
            double nextBodyMin = Math.Min(nextOpen, nextClose);
            double prevBody = Math.Abs(prevClose - prevOpen);
            double baseBody = Math.Abs(baseClose - baseOpen);
            double baseRange = baseHigh - baseLow;

            if (prevBody <= 0 || baseRange <= 0)
                return;

            int baseBodyBp = ToBasisPoints(baseBody, baseRange);
            bool isSmallBase = baseBodyBp <= (int)Math.Round(SmallBodyRatio * 10000.0, MidpointRounding.AwayFromZero);
            int baseRangeTicks = ToTickCount(baseRange);
            if (!isSmallBase || baseRangeTicks < MinZoneTicks)
                return;

            bool prevUp = prevClose > prevOpen;
            bool prevDown = prevClose < prevOpen;
            DateTime baseTime = Times[bip][1];
            int creationBarPrimary = ResolvePrimaryBarIndex(baseTime);
            if (creationBarPrimary < 0)
                return;

            if (prevUp && nextBodyMax > baseHigh + TickSize * 1e-6)
            {
                double top = Math.Max(baseOpen, baseClose);
                double bottom = baseLow;
                CreateZone(ZoneKind.RBR, timeframeMinutes, baseTime, creationBarPrimary, top, bottom, baseOpen, baseClose, baseHigh, baseLow, nextClose, ema, bip);
            }

            if (prevDown && nextBodyMin < baseLow - TickSize * 1e-6)
            {
                double top = baseHigh;
                double bottom = Math.Min(baseOpen, baseClose);
                CreateZone(ZoneKind.DBD, timeframeMinutes, baseTime, creationBarPrimary, top, bottom, baseOpen, baseClose, baseHigh, baseLow, nextClose, ema, bip);
            }
        }

        private void CreateZone(
            ZoneKind kind,
            int timeframeMinutes,
            DateTime baseTime,
            int creationBarPrimary,
            double top,
            double bottom,
            double baseOpen,
            double baseClose,
            double baseHigh,
            double baseLow,
            double nextClose,
            EMA ema,
            int bip)
        {
            if (top <= bottom)
                return;

            foreach (Zone existing in zones)
            {
                if (!existing.IsActive || existing.Kind != kind || existing.TimeframeMinutes != timeframeMinutes)
                    continue;

                if (Math.Abs(existing.Top - top) < TickSize * 0.5 && Math.Abs(existing.Bottom - bottom) < TickSize * 0.5)
                    return;

                bool overlaps = bottom <= existing.Top + TickSize * 1e-6 && top >= existing.Bottom - TickSize * 1e-6;
                if (overlaps)
                    return;
            }

            double zoneHeight = top - bottom;
            int departureBodyBp = ToBasisPoints(Math.Abs(nextClose - baseClose), zoneHeight);
            double zoneEdge = kind == ZoneKind.RBR ? baseHigh : baseLow;
            int departureExtensionBp = ToBasisPoints(Math.Abs(nextClose - zoneEdge), zoneHeight);
            int baseBodyBp = ToBasisPoints(Math.Abs(baseClose - baseOpen), baseHigh - baseLow);
            double emaAtBase = ema[1];
            double emaPrev = ema[2];
            double emaPrev2 = ema[3];
            bool trendCloseOk = kind == ZoneKind.RBR ? baseClose > emaAtBase : baseClose < emaAtBase;
            bool trendSlopeOk = kind == ZoneKind.RBR ? emaPrev > emaPrev2 : emaPrev < emaPrev2;
            int heightTicks = ToTickCount(zoneHeight);

            Zone zone = new Zone
            {
                Kind = kind,
                TimeframeMinutes = timeframeMinutes,
                FrameLabel = timeframeMinutes == 5 ? "5m" : "15m",
                BaseTime = baseTime,
                BaseTag = string.Format("CZ_{0}_{1}_{2:yyyyMMdd_HHmmss}", timeframeMinutes, kind, baseTime),
                Top = top,
                Bottom = bottom,
                TouchCount = 0,
                CreationBarPrimary = creationBarPrimary,
                OpacityFactor = 1.0,
                IsActive = true,
                WasInsideOnPriorBar = false,
                ScoreDeparture = ScoreDeparture(departureBodyBp, departureExtensionBp),
                ScoreBase = ScoreBaseQuality(baseBodyBp),
                ScoreTrend = ScoreTrendAlignment(trendCloseOk, trendSlopeOk),
                ScoreHeight = ScoreZoneHeight(timeframeMinutes, heightTicks)
            };

            UpdateDynamicScore(zone);
            zones.Add(zone);
        }

        private void InvalidateAndTouchZones()
        {
            if (CurrentBar < 0)
                return;

            double bodyMax = Math.Max(Open[0], Close[0]);
            double bodyMin = Math.Min(Open[0], Close[0]);
            double high = High[0];
            double low = Low[0];

            foreach (Zone zone in zones)
            {
                if (!zone.IsActive || CurrentBar <= zone.CreationBarPrimary)
                    continue;

                bool invalidated = zone.Kind == ZoneKind.RBR
                    ? bodyMin < zone.Bottom - TickSize * 1e-6
                    : bodyMax > zone.Top + TickSize * 1e-6;

                if (invalidated)
                {
                    zone.IsActive = false;
                    continue;
                }

                bool overlaps = high >= zone.Bottom - TickSize * 1e-6 && low <= zone.Top + TickSize * 1e-6;
                if (overlaps && !zone.WasInsideOnPriorBar)
                    zone.TouchCount++;

                zone.WasInsideOnPriorBar = overlaps;
            }
        }

        private void UpdateZoneLifecycle()
        {
            foreach (Zone zone in zones)
            {
                if (!zone.IsActive)
                    continue;

                int ageBars = Math.Max(0, CurrentBar - zone.CreationBarPrimary);
                int maxAge = zone.TimeframeMinutes == 5 ? MaxAgeBars5m : MaxAgeBars15m;
                zone.OpacityFactor = Math.Pow(0.98, ageBars) * Math.Max(0.0, 1.0 - zone.TouchCount * 0.20);
                UpdateDynamicScore(zone);

                if (ageBars > maxAge || zone.TouchCount >= MaxTouchCount || zone.OpacityFactor < 0.05)
                    zone.IsActive = false;
            }

            List<Zone> active = zones.Where(z => z.IsActive).OrderBy(z => GetDisplayOpacity(z)).ThenBy(z => z.CreationBarPrimary).ToList();
            while (active.Count > MaxActiveZones)
            {
                active[0].IsActive = false;
                active.RemoveAt(0);
            }
        }

        private void UpdateDynamicScore(Zone zone)
        {
            zone.ScoreFreshness = zone.TouchCount == 0 ? 2 : zone.TouchCount == 1 ? 1 : 0;
            zone.Score = zone.ScoreFreshness + zone.ScoreDeparture + zone.ScoreBase + zone.ScoreTrend + zone.ScoreHeight;
        }

        private void RedrawAllZones()
        {
            foreach (Zone zone in zones)
            {
                ClearZoneDrawings(zone);
                if (!zone.IsActive)
                    continue;

                if ((zone.TimeframeMinutes == 5 && !Show5m) || (zone.TimeframeMinutes == 15 && !Show15m))
                    continue;

                int startBarsAgo = CurrentBar - zone.CreationBarPrimary;
                if (startBarsAgo < 0)
                    continue;

                double drawOpacity = GetDisplayOpacity(zone);
                Color stageColor = GetStageColor(zone);
                Brush fillBrush = BrushUtil.MakeSolid(stageColor);
                Brush borderBrush = BrushUtil.MakeSolid(WithOpacity(stageColor, drawOpacity));
                Brush entryBrush = BrushUtil.MakeSolid(WithOpacity(stageColor, 1.0));
                DashStyleHelper borderDash = zone.TouchCount == 0 ? DashStyleHelper.Solid : DashStyleHelper.Dash;
                int areaOpacity = Math.Max(1, Math.Min(100, (int)Math.Round(FillOpacity * drawOpacity, MidpointRounding.AwayFromZero)));

                Draw.Rectangle(this, zone.BaseTag + "_RECT", false,
                    startBarsAgo, zone.Top, RightOffsetBars, zone.Bottom,
                    Brushes.Transparent, fillBrush, areaOpacity);

                Draw.Line(this, zone.BaseTag + "_TOP", false,
                    startBarsAgo, zone.Top, RightOffsetBars, zone.Top,
                    borderBrush, borderDash, 1);
                Draw.Line(this, zone.BaseTag + "_BOT", false,
                    startBarsAgo, zone.Bottom, RightOffsetBars, zone.Bottom,
                    borderBrush, borderDash, 1);
                Draw.Line(this, zone.BaseTag + "_LEFT", false,
                    startBarsAgo, zone.Top, startBarsAgo, zone.Bottom,
                    borderBrush, borderDash, 1);
                Draw.Line(this, zone.BaseTag + "_RIGHT", false,
                    RightOffsetBars, zone.Top, RightOffsetBars, zone.Bottom,
                    borderBrush, borderDash, 1);

                if (ShowEntryLines)
                {
                    double entryPrice = zone.Kind == ZoneKind.RBR ? zone.Bottom : zone.Top;
                    Draw.Line(this, GetEntryTag(zone), false,
                        startBarsAgo, entryPrice, RightOffsetBars, entryPrice,
                        entryBrush, DashStyleHelper.Dot, 1);
                    Draw.Text(this, GetEntryTag(zone) + "_LBL", false, "LIMIT", RightOffsetBars, entryPrice, 0,
                        entryBrush, new SimpleFont("Segoe UI", 8), System.Windows.TextAlignment.Left, null, null, 0);
                }

                if (ShowLabels && zone.Score >= MinScoreToDisplay)
                {
                    Brush labelBrush = zone.Score >= 7 ? Brushes.White : zone.Score >= 5 ? Brushes.Yellow : Brushes.Gray;
                    string label = string.Format("{0} {1} [{2}]", zone.Kind, zone.FrameLabel, zone.Score);
                    Draw.Text(this, zone.BaseTag + "_SCORE", false, label, RightOffsetBars, zone.Top + TickSize, 0,
                        labelBrush, new SimpleFont("Segoe UI", 8), System.Windows.TextAlignment.Left, null, null, 0);
                }
            }
        }

        private void ClearZoneDrawings(Zone zone)
        {
            RemoveDrawObject(zone.BaseTag + "_RECT");
            RemoveDrawObject(zone.BaseTag + "_TOP");
            RemoveDrawObject(zone.BaseTag + "_BOT");
            RemoveDrawObject(zone.BaseTag + "_LEFT");
            RemoveDrawObject(zone.BaseTag + "_RIGHT");
            RemoveDrawObject(zone.BaseTag + "_SCORE");
            RemoveDrawObject(GetEntryTag(zone));
            RemoveDrawObject(GetEntryTag(zone) + "_LBL");
        }

        private string GetEntryTag(Zone zone)
        {
            return string.Format("IZ_ENTRY_{0}_{1:yyyyMMdd_HHmmss}", zone.TimeframeMinutes, zone.BaseTime);
        }

        private double GetDisplayOpacity(Zone zone)
        {
            double stageOpacity;
            if (zone.TouchCount == 0)
                stageOpacity = 1.0;
            else if (zone.TouchCount == 1)
                stageOpacity = 0.8;
            else
                stageOpacity = 0.4;

            double effective = Math.Min(stageOpacity, zone.OpacityFactor);
            if (zone.Score < MinScoreToDisplay)
                effective = Math.Min(effective, 0.10);
            return Math.Max(0.0, Math.Min(1.0, effective));
        }

        private Color GetStageColor(Zone zone)
        {
            Color baseColor = GetBaseColor(zone);
            if (zone.TouchCount >= 2)
                return Blend(baseColor, Colors.Gray, 0.55);
            return baseColor;
        }

        private Color GetBaseColor(Zone zone)
        {
            Brush brush = zone.TimeframeMinutes == 5
                ? (zone.Kind == ZoneKind.RBR ? RBR5 : DBD5)
                : (zone.Kind == ZoneKind.RBR ? RBR15 : DBD15);

            SolidColorBrush solid = brush as SolidColorBrush;
            return solid != null ? solid.Color : Colors.Gray;
        }

        private static Color WithOpacity(Color color, double opacity)
        {
            byte a = (byte)Math.Max(0, Math.Min(255, (int)Math.Round(opacity * 255.0, MidpointRounding.AwayFromZero)));
            return Color.FromArgb(a, color.R, color.G, color.B);
        }

        private static Color Blend(Color left, Color right, double rightWeight)
        {
            double clamped = Math.Max(0.0, Math.Min(1.0, rightWeight));
            double leftWeight = 1.0 - clamped;
            return Color.FromArgb(
                255,
                (byte)Math.Round(left.R * leftWeight + right.R * clamped, MidpointRounding.AwayFromZero),
                (byte)Math.Round(left.G * leftWeight + right.G * clamped, MidpointRounding.AwayFromZero),
                (byte)Math.Round(left.B * leftWeight + right.B * clamped, MidpointRounding.AwayFromZero));
        }

        private int ResolvePrimaryBarIndex(DateTime time)
        {
            int barIndex = BarsArray[0].GetBar(time);
            if (barIndex >= 0)
                return barIndex;

            for (int barsAgo = 0; barsAgo <= Math.Min(CurrentBar, 2000); barsAgo++)
            {
                if (Times[0][barsAgo] <= time)
                    return CurrentBar - barsAgo;
            }

            return -1;
        }

        private int ScoreDeparture(int departureBodyBp, int departureExtensionBp)
        {
            if (departureBodyBp >= 15000 && departureExtensionBp >= 5000)
                return 2;
            if (departureBodyBp >= 10000 && departureExtensionBp > 0)
                return 1;
            return 0;
        }

        private int ScoreBaseQuality(int baseBodyBp)
        {
            if (baseBodyBp <= 3500)
                return 2;
            if (baseBodyBp <= 5000)
                return 1;
            return 0;
        }

        private int ScoreTrendAlignment(bool trendCloseOk, bool trendSlopeOk)
        {
            if (trendCloseOk && trendSlopeOk)
                return 2;
            if (trendCloseOk ^ trendSlopeOk)
                return 1;
            return 0;
        }

        private int ScoreZoneHeight(int timeframeMinutes, int heightTicks)
        {
            if (timeframeMinutes == 5)
            {
                if (heightTicks >= 4 && heightTicks <= 10)
                    return 2;
                if (heightTicks >= 3 && heightTicks <= 12)
                    return 1;
                return 0;
            }

            if (heightTicks >= 6 && heightTicks <= 14)
                return 2;
            if (heightTicks >= 5 && heightTicks <= 18)
                return 1;
            return 0;
        }

        private int ToBasisPoints(double numerator, double denominator)
        {
            if (denominator <= 0)
                return 0;
            return (int)Math.Round((numerator / denominator) * 10000.0, MidpointRounding.AwayFromZero);
        }

        private int ToTickCount(double priceDistance)
        {
            return (int)Math.Round(priceDistance / TickSize, MidpointRounding.AwayFromZero);
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(0.1, 0.8)]
        [Display(Name = "SmallBodyRatio", GroupName = "Logic", Order = 0)]
        public double SmallBodyRatio { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "MinZoneTicks", GroupName = "Logic", Order = 1)]
        public int MinZoneTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "MinScoreToDisplay", GroupName = "Logic", Order = 2)]
        public int MinScoreToDisplay { get; set; }

        [NinjaScriptProperty]
        [Range(10, 500)]
        [Display(Name = "MaxAgeBars5m", GroupName = "Dissipation", Order = 0)]
        public int MaxAgeBars5m { get; set; }

        [NinjaScriptProperty]
        [Range(5, 200)]
        [Display(Name = "MaxAgeBars15m", GroupName = "Dissipation", Order = 1)]
        public int MaxAgeBars15m { get; set; }

        [NinjaScriptProperty]
        [Range(1, 5)]
        [Display(Name = "MaxTouchCount", GroupName = "Dissipation", Order = 2)]
        public int MaxTouchCount { get; set; }

        [NinjaScriptProperty]
        [Range(4, 20)]
        [Display(Name = "MaxActiveZones", GroupName = "Dissipation", Order = 3)]
        public int MaxActiveZones { get; set; }

        [NinjaScriptProperty]
        [Range(10, 80)]
        [Display(Name = "FillOpacity", GroupName = "Style", Order = 0)]
        public int FillOpacity { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowLabels", GroupName = "Style", Order = 1)]
        public bool ShowLabels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowEntryLines", GroupName = "Style", Order = 2)]
        public bool ShowEntryLines { get; set; }

        [NinjaScriptProperty]
        [Range(-50, -1)]
        [Display(Name = "RightOffsetBars", GroupName = "Style", Order = 3)]
        public int RightOffsetBars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show5m", GroupName = "Timeframes", Order = 0)]
        public bool Show5m { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Show15m", GroupName = "Timeframes", Order = 1)]
        public bool Show15m { get; set; }

        [XmlIgnore]
        [NinjaScriptProperty]
        [Display(Name = "RBR5", GroupName = "Colors", Order = 0)]
        public Brush RBR5 { get; set; }

        [Browsable(false)]
        public string RBR5Serializable
        {
            get { return Serialize.BrushToString(RBR5); }
            set { RBR5 = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [NinjaScriptProperty]
        [Display(Name = "DBD5", GroupName = "Colors", Order = 1)]
        public Brush DBD5 { get; set; }

        [Browsable(false)]
        public string DBD5Serializable
        {
            get { return Serialize.BrushToString(DBD5); }
            set { DBD5 = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [NinjaScriptProperty]
        [Display(Name = "RBR15", GroupName = "Colors", Order = 2)]
        public Brush RBR15 { get; set; }

        [Browsable(false)]
        public string RBR15Serializable
        {
            get { return Serialize.BrushToString(RBR15); }
            set { RBR15 = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [NinjaScriptProperty]
        [Display(Name = "DBD15", GroupName = "Colors", Order = 3)]
        public Brush DBD15 { get; set; }

        [Browsable(false)]
        public string DBD15Serializable
        {
            get { return Serialize.BrushToString(DBD15); }
            set { DBD15 = Serialize.StringToBrush(value); }
        }
        #endregion
    }
}


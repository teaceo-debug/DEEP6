// DEEP6LVNZones — session-based volume profile Low Volume Node zones
// Detects LVN zones from RTH session profile, renders as semi-transparent rectangles.
// Prior sessions persist with dimming opacity. Zone boundaries = adjacent HVN peaks.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6LVNZones : Indicator
    {
        private sealed class LvnZone
        {
            public double Top;
            public double Bottom;
            public double LvnPrice;
            public double ValleyDepth; // ratio: 1.0 - (lvnVol / avgHvnVol) — higher = deeper valley
        }

        private sealed class SessionZoneData
        {
            public int PeriodKey;
            public DateTime SessionStart;
            public List<LvnZone> Zones = new List<LvnZone>();
        }

        private struct BarHLV { public double H, L, V; }

        // Profile data
        private List<BarHLV>          _periodBars;
        private double[]              _vpValues;
        private double[]              _vpYVol;
        private SessionIterator       _sessionIterator;
        private DateTime              _lastSessionBegin;

        // Zone data
        private List<LvnZone>         _currentZones;
        private List<SessionZoneData>  _sessionHistory;
        private List<LvnZone>         _allZones;

        // SharpDX rendering
        private SharpDX.Direct2D1.SolidColorBrush[] _zoneFillBrushes;
        private SharpDX.Direct2D1.SolidColorBrush[] _zoneBorderBrushes;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description       = "LVN Zones — session-based volume profile low-volume node zones with SharpDX rendering";
                Name              = "DEEP6 LVN Zones";
                Calculate         = Calculate.OnBarClose;
                IsOverlay         = true;
                DisplayInDataBox  = false;

                Rows              = 200;
                LvnStrength       = 12;
                MaxSessions       = 2;
                ZoneOpacity       = 22;
                MinBarsForProfile = 30;
                MaxZonesPerSession = 3;
                MinValleyDepthPct  = 40;
                MinZoneHeightTicks = 8;

                ZoneBrush = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0x1E, 0x90, 0xFF)); // DodgerBlue
                ZoneBrush.Freeze();
                ZoneBorderBrush = new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0x00, 0xE0, 0xFF)); // Cyan
                ZoneBorderBrush.Freeze();
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 1);
            }
            else if (State == State.DataLoaded)
            {
                if (ZoneBrush != null && !ZoneBrush.IsFrozen)
                    ZoneBrush.Freeze();
                if (ZoneBorderBrush != null && !ZoneBorderBrush.IsFrozen)
                    ZoneBorderBrush.Freeze();

                _periodBars       = new List<BarHLV>();
                _currentZones     = new List<LvnZone>();
                _sessionHistory   = new List<SessionZoneData>();
                _allZones         = new List<LvnZone>();
                _vpValues         = new double[Rows + 1];
                _vpYVol           = new double[Rows + 1];
                _sessionIterator  = new SessionIterator(Bars);
                _lastSessionBegin = DateTime.MinValue;
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                _periodBars.Add(new BarHLV { H = High[0], L = Low[0], V = Volume[0] });
                return;
            }

            if (CurrentBar < 1)
                return;

            _sessionIterator.GetNextSession(Time[0], true);
            DateTime sessionBegin = _sessionIterator.ActualSessionBegin;

            bool isNewSession = sessionBegin != _lastSessionBegin && _lastSessionBegin != DateTime.MinValue;

            if (isNewSession)
            {
                // Archive current session zones to _sessionHistory
                if (_currentZones.Count > 0 && _periodBars.Count >= MinBarsForProfile)
                {
                    var archived = new SessionZoneData
                    {
                        PeriodKey    = _lastSessionBegin.Year * 10000 + _lastSessionBegin.DayOfYear,
                        SessionStart = _lastSessionBegin,
                        Zones        = new List<LvnZone>(_currentZones)
                    };
                    _sessionHistory.Add(archived);

                    // Prune oldest when over limit (also clears all when MaxSessions == 0)
                    while (_sessionHistory.Count > MaxSessions)
                        _sessionHistory.RemoveAt(0);
                }

                // Clear profile for new session
                _periodBars.Clear();
                Array.Clear(_vpValues, 0, _vpValues.Length);
                Array.Clear(_vpYVol, 0, _vpYVol.Length);
                _currentZones.Clear();

                // Update combined zone list after archival
                UpdateAllZones();
            }

            _lastSessionBegin = sessionBegin;

            if (Time[0] < _sessionIterator.ActualSessionBegin || Time[0] > _sessionIterator.ActualSessionEnd)
                return;

            RebuildProfile();
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            base.OnRender(chartControl, chartScale);

            if (IsInHitTest) return;
            if (RenderTarget == null || ChartBars == null) return;
            if (_zoneFillBrushes == null || _zoneBorderBrushes == null) return;
            if (_allZones == null || _allZones.Count == 0) return;

            RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;

            float panelLeft  = (float)ChartPanel.X;
            float panelRight = (float)(ChartPanel.X + ChartPanel.W);
            float zoneWidth  = panelRight - panelLeft;

            // Render prior session zones FIRST (drawn behind), oldest to newest
            for (int s = 0; s < _sessionHistory.Count; s++)
            {
                int sessionAge = _sessionHistory.Count - 1 - s;
                int tierIndex  = Math.Min(sessionAge + 1, _zoneFillBrushes.Length - 1);

                foreach (LvnZone zone in _sessionHistory[s].Zones)
                {
                    float topY = (float)chartScale.GetYByValue(zone.Top);
                    float botY = (float)chartScale.GetYByValue(zone.Bottom);
                    if (botY <= topY) continue;

                    var rect = new SharpDX.RectangleF(panelLeft, topY, zoneWidth, botY - topY);
                    RenderTarget.FillRectangle(rect, _zoneFillBrushes[tierIndex]);
                    RenderTarget.DrawRectangle(rect, _zoneBorderBrushes[tierIndex], 1f);
                }
            }

            // Render current session zones LAST (drawn on top, brightest)
            foreach (LvnZone zone in _currentZones)
            {
                float topY = (float)chartScale.GetYByValue(zone.Top);
                float botY = (float)chartScale.GetYByValue(zone.Bottom);
                if (botY <= topY) continue;

                var rect = new SharpDX.RectangleF(panelLeft, topY, zoneWidth, botY - topY);
                RenderTarget.FillRectangle(rect, _zoneFillBrushes[0]);
                RenderTarget.DrawRectangle(rect, _zoneBorderBrushes[0], 1f);
            }
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;

            int tiers = MaxSessions + 1;
            _zoneFillBrushes   = new SharpDX.Direct2D1.SolidColorBrush[tiers];
            _zoneBorderBrushes = new SharpDX.Direct2D1.SolidColorBrush[tiers];

            float baseAlpha   = ZoneOpacity / 100f;
            float dimFactor   = (MaxSessions > 0) ? (baseAlpha * 0.6f / MaxSessions) : 0f;
            float borderAlpha = Math.Min(baseAlpha * 3.0f, 0.85f);

            for (int i = 0; i < tiers; i++)
            {
                float fillAlpha = Math.Max(0.03f, baseAlpha - i * dimFactor);
                float brdAlpha  = Math.Max(0.10f, borderAlpha - i * dimFactor * 2f);

                _zoneFillBrushes[i] = new SharpDX.Direct2D1.SolidColorBrush(
                    RenderTarget,
                    ExtractColor4(ZoneBrush, 0x1E, 0x90, 0xFF, fillAlpha));

                _zoneBorderBrushes[i] = new SharpDX.Direct2D1.SolidColorBrush(
                    RenderTarget,
                    ExtractColor4(ZoneBorderBrush, 0x00, 0xE0, 0xFF, brdAlpha));
            }
        }

        private void RebuildProfile()
        {
            if (_periodBars.Count < MinBarsForProfile)
                return;

            double yMax = double.MinValue;
            double yMin = double.MaxValue;
            foreach (BarHLV b in _periodBars)
            {
                if (b.H > yMax) yMax = b.H;
                if (b.L < yMin) yMin = b.L;
            }

            if (yMax <= yMin)
                return;

            double step = (yMax - yMin) / Rows;
            if (step < TickSize) step = TickSize;

            int size = Rows + 1;
            if (size <= LvnStrength * 2 + 1)
                return;

            for (int i = 0; i <= Rows; i++)
                _vpYVol[i] = yMin + i * (yMax - yMin) / Rows;

            Array.Clear(_vpValues, 0, _vpValues.Length);

            foreach (BarHLV b in _periodBars)
            {
                if (b.V <= 0) continue;
                int r1 = (int)Math.Floor((Math.Min(b.L, b.H) - yMin) / step);
                int r2 = (int)Math.Floor((Math.Max(b.L, b.H) - yMin) / step);
                r1 = Math.Max(0, Math.Min(r1, Rows));
                r2 = Math.Max(0, Math.Min(r2, Rows));
                int span = r2 - r1 + 1;
                double addV = span > 0 ? b.V / span : 0.0;
                for (int r = r1; r <= r2; r++)
                    _vpValues[r] += addV;
            }

            DetectLvnZones();
        }

        private void DetectLvnZones()
        {
            _currentZones.Clear();

            int size = Rows + 1;
            if (_vpValues == null || _vpValues.Length < size) return;
            if (size <= LvnStrength * 2 + 1) return;

            // Compute mean profile volume for depth threshold
            double sumVol = 0;
            int nonZeroCount = 0;
            for (int i = 0; i < size; i++)
            {
                if (_vpValues[i] > 0) { sumVol += _vpValues[i]; nonZeroCount++; }
            }
            double meanVol = nonZeroCount > 0 ? sumVol / nonZeroCount : 0;
            double depthThreshold = meanVol * (MinValleyDepthPct / 100.0);

            // Step 1: Detect LVN indices (local minima) — exact VPLowTFLVNLevels algorithm
            var lvnIndices = new List<int>();
            for (int i = 0; i < size; i++)
            {
                double val = _vpValues[i];
                if (val <= 0) continue;

                bool isLvn = true;
                for (int j = -LvnStrength; j <= LvnStrength; j++)
                {
                    if (j == 0) continue;
                    int k = i + j;
                    if (k < 0 || k >= size) continue;
                    if (_vpValues[k] <= 0) continue;
                    if (_vpValues[k] < val) { isLvn = false; break; }
                }
                if (isLvn) lvnIndices.Add(i);
            }

            if (lvnIndices.Count == 0)
            {
                UpdateAllZones();
                return;
            }

            // Step 2: Build candidate zones with valley depth scoring
            var candidates = new List<LvnZone>();
            foreach (int lvnIdx in lvnIndices)
            {
                double lvnVol   = _vpValues[lvnIdx];
                double lvnPrice = _vpYVol[lvnIdx];

                // FILTER: Valley depth threshold — skip shallow LVNs
                if (lvnVol > depthThreshold) continue;

                // Find zone boundaries (adjacent local maxima)
                int topIdx = -1;
                for (int i = lvnIdx + 1; i < size; i++)
                {
                    if (_vpValues[i] <= 0) continue;
                    if (IsLocalMax(i, size)) { topIdx = i; break; }
                }
                double zoneTop = (topIdx >= 0) ? _vpYVol[topIdx] : _vpYVol[size - 1];

                int botIdx = -1;
                for (int i = lvnIdx - 1; i >= 0; i--)
                {
                    if (_vpValues[i] <= 0) continue;
                    if (IsLocalMax(i, size)) { botIdx = i; break; }
                }
                double zoneBottom = (botIdx >= 0) ? _vpYVol[botIdx] : _vpYVol[0];

                if (zoneTop <= zoneBottom) continue;
                if (lvnPrice <= zoneBottom || lvnPrice >= zoneTop) continue;

                // FILTER: Minimum zone height in ticks
                double zoneHeightTicks = (zoneTop - zoneBottom) / TickSize;
                if (zoneHeightTicks < MinZoneHeightTicks) continue;

                // Compute valley depth score: average of adjacent HVN volumes vs LVN volume
                double topVol = (topIdx >= 0) ? _vpValues[topIdx] : meanVol;
                double botVol = (botIdx >= 0) ? _vpValues[botIdx] : meanVol;
                double avgHvnVol = (topVol + botVol) / 2.0;
                double valleyDepth = avgHvnVol > 0 ? 1.0 - (lvnVol / avgHvnVol) : 0;

                candidates.Add(new LvnZone
                {
                    Top         = zoneTop,
                    Bottom      = zoneBottom,
                    LvnPrice    = lvnPrice,
                    ValleyDepth = valleyDepth
                });
            }

            // Step 3: Rank by valley depth (deepest first), take top N
            candidates.Sort((a, b) => b.ValleyDepth.CompareTo(a.ValleyDepth));
            int maxZones = Math.Max(1, MaxZonesPerSession);
            for (int i = 0; i < Math.Min(candidates.Count, maxZones); i++)
                _currentZones.Add(candidates[i]);

            UpdateAllZones();
        }

        private bool IsLocalMax(int i, int size)
        {
            double val = _vpValues[i];
            if (val <= 0) return false;

            for (int j = -LvnStrength; j <= LvnStrength; j++)
            {
                if (j == 0) continue;
                int k = i + j;
                if (k < 0 || k >= size) continue;
                if (_vpValues[k] <= 0) continue;
                if (_vpValues[k] > val) return false;
            }
            return true;
        }

        private void UpdateAllZones()
        {
            _allZones.Clear();
            _allZones.AddRange(_currentZones);
            for (int s = _sessionHistory.Count - 1; s >= 0; s--)
                _allZones.AddRange(_sessionHistory[s].Zones);
        }

        private SharpDX.Color4 ExtractColor4(System.Windows.Media.Brush wpfBrush, byte r, byte g, byte b, float alpha)
        {
            var scb = wpfBrush as System.Windows.Media.SolidColorBrush;
            if (scb != null)
            {
                return new SharpDX.Color4(
                    scb.Color.R / 255f,
                    scb.Color.G / 255f,
                    scb.Color.B / 255f,
                    alpha);
            }
            return new SharpDX.Color4(r / 255f, g / 255f, b / 255f, alpha);
        }

        private void DisposeDx()
        {
            if (_zoneFillBrushes != null)
            {
                for (int i = 0; i < _zoneFillBrushes.Length; i++)
                {
                    if (_zoneFillBrushes[i] != null)
                    {
                        _zoneFillBrushes[i].Dispose();
                        _zoneFillBrushes[i] = null;
                    }
                }
                _zoneFillBrushes = null;
            }
            if (_zoneBorderBrushes != null)
            {
                for (int i = 0; i < _zoneBorderBrushes.Length; i++)
                {
                    if (_zoneBorderBrushes[i] != null)
                    {
                        _zoneBorderBrushes[i].Dispose();
                        _zoneBorderBrushes[i] = null;
                    }
                }
                _zoneBorderBrushes = null;
            }
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "Profile Rows", Description = "Number of price bins in the volume profile", Order = 1, GroupName = "1. Profile")]
        public int Rows { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "LVN Strength", Description = "Window of bins that must have higher volume to qualify as LVN", Order = 2, GroupName = "1. Profile")]
        public int LvnStrength { get; set; }

        [NinjaScriptProperty]
        [Range(0, 10)]
        [Display(Name = "Prior Sessions", Description = "Number of prior RTH sessions to display (0 = current only)", Order = 3, GroupName = "1. Profile")]
        public int MaxSessions { get; set; }

        [NinjaScriptProperty]
        [Range(10, 200)]
        [Display(Name = "Min Bars for Profile", Description = "Minimum 1-min bars required before zone detection runs", Order = 4, GroupName = "1. Profile")]
        public int MinBarsForProfile { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Max Zones per Session", Description = "Only show the N deepest LVN valleys per session (ranked by depth)", Order = 5, GroupName = "1. Profile")]
        public int MaxZonesPerSession { get; set; }

        [NinjaScriptProperty]
        [Range(10, 90)]
        [Display(Name = "Min Valley Depth %", Description = "LVN volume must be below this % of mean profile volume to qualify", Order = 6, GroupName = "1. Profile")]
        public int MinValleyDepthPct { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Min Zone Height (Ticks)", Description = "Zones narrower than this many ticks are filtered out", Order = 7, GroupName = "1. Profile")]
        public int MinZoneHeightTicks { get; set; }

        [NinjaScriptProperty]
        [Range(5, 80)]
        [Display(Name = "Zone Opacity %", Description = "Fill opacity for current session zones (prior sessions dim further)", Order = 1, GroupName = "2. Display")]
        public int ZoneOpacity { get; set; }

        [XmlIgnore]
        [Display(Name = "Zone Fill Color", Order = 2, GroupName = "2. Display")]
        public System.Windows.Media.Brush ZoneBrush { get; set; }

        [Browsable(false)]
        public string ZoneBrushSerializable
        {
            get { return Serialize.BrushToString(ZoneBrush); }
            set { ZoneBrush = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Zone Border Color", Order = 3, GroupName = "2. Display")]
        public System.Windows.Media.Brush ZoneBorderBrush { get; set; }

        [Browsable(false)]
        public string ZoneBorderBrushSerializable
        {
            get { return Serialize.BrushToString(ZoneBorderBrush); }
            set { ZoneBorderBrush = Serialize.StringToBrush(value); }
        }

        /// <summary>
        /// All active LVN zones (current session + prior sessions).
        /// Updated each bar. Expose for strategy consumption.
        /// </summary>
        [Browsable(false)]
        [XmlIgnore]
        public IReadOnlyList<(double Top, double Bottom, double LvnPrice)> LvnZones
        {
            get
            {
                if (_allZones == null || _allZones.Count == 0)
                    return Array.Empty<(double, double, double)>();
                return _allZones.Select(z => (z.Top, z.Bottom, z.LvnPrice)).ToList();
            }
        }

        #endregion
    }
}

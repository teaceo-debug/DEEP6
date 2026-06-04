// VPLowTFLVNLevels — Volume Profile Low Volume Node Levels
//
// Builds a volume profile from lower-timeframe (default: 1-min) bars over a
// configurable period (Daily, Weekly, Monthly) and marks Low Volume Node price
// levels as horizontal lines on the chart.
// Bull color = LVN is overhead (price below); Bear color = LVN is support (price above).
// Lowest-volume LVN gets a solid line; all others are dashed. Resets each period.
//
// Install: copy to
//   %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\VPLowTFLVNLevels.cs
// then F5 in the NinjaScript Editor.

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript
{
    public enum VPProfilePeriod { Daily, Weekly, Monthly }
}

namespace NinjaTrader.NinjaScript.Indicators
{
    public class VPLowTFLVNLevels : Indicator
    {
        private struct BarHLV { public double H, L, V; }

        private List<BarHLV> _periodBars;
        private double[]     _vpValues;
        private double[]     _vpYVol;
        private List<string> _lvnTags;
        private List<double> _lvnPrices;
        private int          _lastPeriodKey;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description      = "Volume Profile LVN — configurable period profile from LTF bars; marks low-volume node levels as horizontal lines";
                Name             = "VP LowTF LVN";
                Calculate        = Calculate.OnBarClose;
                IsOverlay        = true;
                DisplayInDataBox = false;

                ProfilePeriod     = VPProfilePeriod.Weekly;
                Rows              = 200;
                LvnStrength       = 5;
                LvnWidth          = 2;
                ResolutionMinutes = 1;
                LvnColorBull      = new SolidColorBrush(Color.FromRgb(0x1E, 0x3A, 0x8A));
                LvnColorBull.Freeze();
                LvnColorBear      = new SolidColorBrush(Color.FromRgb(0x25, 0x63, 0xEB));
                LvnColorBear.Freeze();
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, ResolutionMinutes);
            }
            else if (State == State.DataLoaded)
            {
                // Freeze user-modified brushes for cross-thread safety
                if (LvnColorBull != null && !LvnColorBull.IsFrozen)
                    LvnColorBull.Freeze();
                if (LvnColorBear != null && !LvnColorBear.IsFrozen)
                    LvnColorBear.Freeze();

                _vpValues      = new double[Rows + 1];
                _vpYVol        = new double[Rows + 1];
                _periodBars    = new List<BarHLV>();
                _lvnTags       = new List<string>();
                _lvnPrices     = new List<double>();
                _lastPeriodKey = -1;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                _periodBars.Add(new BarHLV { H = High[0], L = Low[0], V = Volume[0] });
                return;
            }

            if (CurrentBar < 1) return;

            int periodKey;
            switch (ProfilePeriod)
            {
                case VPProfilePeriod.Daily:
                    periodKey = Time[0].Year * 1000 + Time[0].DayOfYear;
                    break;
                case VPProfilePeriod.Weekly:
                    int dow = ((int)Time[0].DayOfWeek + 6) % 7; // Mon=0 .. Sun=6
                    DateTime monday = Time[0].Date.AddDays(-dow);
                    periodKey = monday.Year * 1000 + monday.DayOfYear;
                    break;
                default: // Monthly
                    periodKey = Time[0].Year * 12 + Time[0].Month;
                    break;
            }

            if (_lastPeriodKey != -1 && periodKey != _lastPeriodKey)
            {
                foreach (string t in _lvnTags) RemoveDrawObject(t);
                _lvnTags.Clear();
                _periodBars.Clear();
                Array.Clear(_vpValues, 0, _vpValues.Length);
            }

            _lastPeriodKey = periodKey;

            RebuildProfile();
            DrawLVNLines();
        }

        private void RebuildProfile()
        {
            if (_periodBars.Count == 0) return;

            double yMax = double.MinValue;
            double yMin = double.MaxValue;
            foreach (BarHLV b in _periodBars)
            {
                if (b.H > yMax) yMax = b.H;
                if (b.L < yMin) yMin = b.L;
            }

            if (yMax <= yMin) return;

            double step = (yMax - yMin) / Rows;
            if (step < TickSize) step = TickSize;

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
                int    span = r2 - r1 + 1;
                double addV = span > 0 ? b.V / span : 0.0;
                for (int r = r1; r <= r2; r++)
                    _vpValues[r] += addV;
            }
        }

        private void DrawLVNLines()
        {
            foreach (string t in _lvnTags) RemoveDrawObject(t);
            _lvnTags.Clear();
            _lvnPrices.Clear();

            int size = Rows + 1;
            if (size <= LvnStrength * 2 + 1) return;

            // Collect LVN indices: bins that are local minima among non-zero bins
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

            if (lvnIndices.Count == 0) return;

            // Lowest-volume LVN (global minimum in profile) gets solid line — matches Pine Script
            double globalMinVol = double.MaxValue;
            for (int i = 0; i < size; i++)
                if (_vpValues[i] > 0 && _vpValues[i] < globalMinVol) globalMinVol = _vpValues[i];

            int drawIdx = 0;
            foreach (int i in lvnIndices)
            {
                double price    = _vpYVol[i];
                double val      = _vpValues[i];
                Brush  color    = Close[0] > price ? LvnColorBear : LvnColorBull;
                DashStyleHelper dash = Math.Abs(val - globalMinVol) < globalMinVol * 0.001
                    ? DashStyleHelper.Solid
                    : DashStyleHelper.Dash;

                string tag = "LVN_" + drawIdx++;
                _lvnTags.Add(tag);
                _lvnPrices.Add(price);
                Draw.HorizontalLine(this, tag, false, price, color, dash, LvnWidth);
            }
        }

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Profile Period", Description = "Reset period for the volume profile", Order = 0, GroupName = "Volume Profile")]
        public VPProfilePeriod ProfilePeriod { get; set; }

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "Rows", Description = "Number of price bins in the volume profile", Order = 1, GroupName = "Volume Profile")]
        public int Rows { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Resolution (Minutes)", Description = "LTF bar size used to build the profile", Order = 2, GroupName = "Volume Profile")]
        public int ResolutionMinutes { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "LVN Strength", Description = "Neighboring bins that must have higher volume to qualify as LVN", Order = 1, GroupName = "LVN Settings")]
        public int LvnStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "Line Width", Order = 2, GroupName = "LVN Settings")]
        public int LvnWidth { get; set; }

        [XmlIgnore]
        [Display(Name = "Bull Color (price below LVN)", Order = 3, GroupName = "LVN Settings")]
        public Brush LvnColorBull { get; set; }

        [Browsable(false)]
        public string LvnColorBullSerializable
        {
            get { return Serialize.BrushToString(LvnColorBull); }
            set { LvnColorBull = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "Bear Color (price above LVN)", Order = 4, GroupName = "LVN Settings")]
        public Brush LvnColorBear { get; set; }

        [Browsable(false)]
        public string LvnColorBearSerializable
        {
            get { return Serialize.BrushToString(LvnColorBear); }
            set { LvnColorBear = Serialize.StringToBrush(value); }
        }

        /// <summary>
        /// Active LVN price levels for the current profile period.
        /// Updated each bar. Consumed by DEEP6LVNRadarStrategy for entry qualification.
        /// </summary>
        [Browsable(false)]
        [XmlIgnore]
        public List<double> LvnPrices { get { return _lvnPrices ?? new List<double>(); } }

        #endregion
    }
}

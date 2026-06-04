#region Using declarations
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.BarsTypes;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public class DEEP6Core : Indicator
    {
        private double _avgDelta;
        private double _avgVolume;
        private double _avgRange;
        private double _prevDelta;
        private double _peakDelta;
        private double _peakAbsDelta;
        private int _peakDeltaBar = -100;
        private double _cvd;
        private double _bestBid = double.NaN;
        private double _bestAsk = double.NaN;
        private int _sessionBars;

        private readonly double[] _closeRing = new double[20];
        private readonly double[] _cvdRing = new double[20];
        private int _ringIdx;
        private int _ringCount;

        private int _lastSignalDir;
        private int _lastSignalCats;
        private string _lastSignalTime = "--:--";
        private bool _lastAbs;
        private bool _lastExh;
        private bool _lastImb;
        private bool _lastDel;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6Core";
                Description = "Focused self-contained footprint signal indicator for NQ volumetric bars.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
				ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 20;

                MinCategories = 3;
                PlaySound = true;
                ShowHUD = true;
                ShowAlerts = true;
                LongColor = Brushes.Lime;
                ShortColor = Brushes.OrangeRed;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;
            if (CurrentBar < BarsRequiredToPlot)
            {
                UpdateHud(SpreadTicks());
                return;
            }

            if (Bars.IsFirstBarOfSession)
                _sessionBars = 0;
            _sessionBars++;

            VolumetricBarsType vbt = Bars.BarsType as VolumetricBarsType;
            if (vbt == null || vbt.Volumes == null || CurrentBar >= vbt.Volumes.Length)
            {
                UpdateHud(SpreadTicks());
                return;
            }

            var vol = vbt.Volumes[CurrentBar];
            if (vol == null)
            {
                UpdateHud(SpreadTicks());
                return;
            }

            double bidVol = vol.TotalBuyingVolume;
            double askVol = vol.TotalSellingVolume;
            double delta = bidVol - askVol;
            double totalVol = bidVol + askVol;
            double barRange = Math.Max(High[0] - Low[0], TickSize);
            double rangeTicks = barRange / TickSize;
            double bodyTicks = Math.Abs(Close[0] - Open[0]) / TickSize;
            double deltaRatio = totalVol > 0 ? delta / totalVol : 0;
            double upperWickPct = (High[0] - Math.Max(Open[0], Close[0])) / barRange;
            double lowerWickPct = (Math.Min(Open[0], Close[0]) - Low[0]) / barRange;
            double bodyPct = Math.Abs(Close[0] - Open[0]) / barRange;
            int spreadTicks = SpreadTicks();

            _cvd += delta;
            _avgDelta = _avgDelta * 0.95 + Math.Abs(delta) * 0.05;
            _avgVolume = _avgVolume * 0.95 + totalVol * 0.05;
            _avgRange = _avgRange * 0.95 + rangeTicks * 0.05;

            if (Math.Abs(delta) > _peakAbsDelta)
            {
                _peakAbsDelta = Math.Abs(delta);
                _peakDelta = delta;
                _peakDeltaBar = CurrentBar;
            }
            _peakAbsDelta *= 0.99;

            _closeRing[_ringIdx] = Close[0];
            _cvdRing[_ringIdx] = _cvd;
            _ringIdx = (_ringIdx + 1) % _closeRing.Length;
            if (_ringCount < _closeRing.Length)
                _ringCount++;

            double absBull = 0;
            double absBear = 0;
            double exhBull = 0;
            double exhBear = 0;
            double imbBull = 0;
            double imbBear = 0;
            double delBull = 0;
            double delBear = 0;

            if (_avgVolume > 50 && totalVol > 1.8 * _avgVolume && rangeTicks < 0.6 * Math.Max(_avgRange, 1))
                AddAbsorptionVote(-Math.Sign(delta), 1.5, ref absBull, ref absBear);
            if (totalVol > 200 && rangeTicks < 4 && Math.Abs(deltaRatio) < 0.18)
                AddAbsorptionVote(-Math.Sign(delta), 1.2, ref absBull, ref absBear);
            if (askVol > 0 && bidVol > 2.5 * askVol && totalVol > 150 && Close[0] <= Close[1] + TickSize)
                absBull += 1.3;
            if (bidVol > 0 && askVol > 2.5 * bidVol && totalVol > 150 && Close[0] >= Close[1] - TickSize)
                absBear += 1.3;
            if (Math.Sign(Close[0] - Close[1]) != Math.Sign(delta) && Math.Abs(delta) > 0.7 * Math.Max(_avgDelta, 1) && _avgDelta > 30)
                AddAbsorptionVote(Math.Sign(Close[0] - Close[1]), 1.4, ref absBull, ref absBear);
            if (totalVol > 2.0 * Math.Max(_avgVolume, 1) && Math.Abs(deltaRatio) > 0.5 && bodyPct < 0.40)
                AddAbsorptionVote(-Math.Sign(delta), 1.6, ref absBull, ref absBear);

            if (totalVol > 2.2 * Math.Max(_avgVolume, 1) && Math.Abs(deltaRatio) > 0.4 && (upperWickPct > 0.35 || lowerWickPct > 0.35))
                AddExhaustionVote(upperWickPct > lowerWickPct ? -1 : 1, 1.7, ref exhBull, ref exhBear);
            if (CurrentBar - _peakDeltaBar >= 2 && CurrentBar - _peakDeltaBar <= 4 && _peakAbsDelta > 0 && Math.Abs(delta) < 0.4 * _peakAbsDelta)
                AddExhaustionVote(-Math.Sign(_peakDelta), 1.4, ref exhBull, ref exhBear);
            if (rangeTicks > 1.5 * Math.Max(_avgRange, 1) && Math.Sign(Close[0] - Open[0]) != Math.Sign(Close[1] - Open[1]))
                AddExhaustionVote(Math.Sign(Close[0] - Open[0]), 1.0, ref exhBull, ref exhBear);
            if (bodyPct > 0.70 && rangeTicks > 1.3 * Math.Max(_avgRange, 1) && Math.Sign(Close[0] - Open[0]) != Math.Sign(delta))
                AddExhaustionVote(-Math.Sign(Close[0] - Open[0]), 1.1, ref exhBull, ref exhBear);

            if (deltaRatio > 0.30 && totalVol > 100)
                imbBull += 1.0;
            else if (deltaRatio < -0.30 && totalVol > 100)
                imbBear += 1.0;
            if (Math.Abs(delta) > 2.0 * Math.Max(_avgDelta, 1) && _avgDelta > 30)
                AddVote(Math.Sign(delta), 0.8, ref imbBull, ref imbBear);

            if (_ringCount >= 5)
            {
                int five = (_ringIdx - 5 + _closeRing.Length) % _closeRing.Length;
                double dPrice = Close[0] - _closeRing[five];
                double dCvd = _cvd - _cvdRing[five];
                if (Math.Sign(dPrice) != Math.Sign(dCvd) && Math.Abs(dCvd) > 100)
                    AddVote(Math.Sign(dPrice), 1.3, ref delBull, ref delBear);
            }
            if (Math.Abs(delta - _prevDelta) > 1.5 * Math.Max(_avgDelta, 1) && Math.Sign(delta) != Math.Sign(_prevDelta) && Math.Abs(_prevDelta) > 40)
                AddVote(Math.Sign(delta), 1.2, ref delBull, ref delBear);
            if (CurrentBar > 0 && Math.Abs(_prevDelta) > 1.4 * Math.Max(_avgDelta, 1) && Math.Sign(Close[0] - Open[0]) == -Math.Sign(_prevDelta) && bodyTicks > 1)
                AddVote(Math.Sign(Close[0] - Open[0]), 1.1, ref delBull, ref delBear);

            int absDir = Dominant(absBull, absBear);
            int exhDir = Dominant(exhBull, exhBear);
            int imbDir = Dominant(imbBull, imbBear);
            int delDir = Dominant(delBull, delBear);

            int weightedDir = absDir + exhDir + imbDir + delDir;
            int dominantDir = weightedDir > 0 ? 1 : (weightedDir < 0 ? -1 : 0);
            int categoryCount = 0;
            bool hitAbs = absDir == dominantDir && dominantDir != 0;
            bool hitExh = exhDir == dominantDir && dominantDir != 0;
            bool hitImb = imbDir == dominantDir && dominantDir != 0;
            bool hitDel = delDir == dominantDir && dominantDir != 0;

            if (hitAbs) categoryCount++;
            if (hitExh) categoryCount++;
            if (hitImb) categoryCount++;
            if (hitDel) categoryCount++;

            bool veto = spreadTicks > 3;
            bool signal = !veto && dominantDir != 0 && categoryCount >= MinCategories;
            bool alert = !veto && dominantDir != 0 && categoryCount == 2 && ShowAlerts;

            if (signal)
            {
                DrawSignalArrow(dominantDir);
                RememberSignal(dominantDir, categoryCount, hitAbs, hitExh, hitImb, hitDel);
                if (PlaySound)
                    Alert("DEEP6CoreSignal" + CurrentBar, Priority.High, "DEEP6 CORE signal", NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav", 10, Brushes.White, Brushes.Black);
            }
            else if (alert)
            {
                DrawAlertDot(dominantDir);
                RememberSignal(dominantDir, categoryCount, hitAbs, hitExh, hitImb, hitDel);
            }

            _prevDelta = delta;
            UpdateHud(spreadTicks);
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (e == null)
                return;
            if (e.MarketDataType == MarketDataType.Bid)
                _bestBid = e.Price;
            else if (e.MarketDataType == MarketDataType.Ask)
                _bestAsk = e.Price;
        }

        private void DrawSignalArrow(int direction)
        {
            if (direction > 0)
                Draw.ArrowUp(this, "DEEP6CoreLong" + CurrentBar, true, 0, Low[0] - 2 * TickSize, LongColor);
            else
                Draw.ArrowDown(this, "DEEP6CoreShort" + CurrentBar, true, 0, High[0] + 2 * TickSize, ShortColor);
        }

        private void DrawAlertDot(int direction)
        {
            if (direction > 0)
                Draw.Dot(this, "DEEP6CoreAlertLong" + CurrentBar, true, 0, Low[0] - TickSize, LongColor);
            else
                Draw.Dot(this, "DEEP6CoreAlertShort" + CurrentBar, true, 0, High[0] + TickSize, ShortColor);
        }

        private void RememberSignal(int direction, int cats, bool abs, bool exh, bool imb, bool del)
        {
            _lastSignalDir = direction;
            _lastSignalCats = cats;
            _lastSignalTime = Time[0].ToString("HH:mm");
            _lastAbs = abs;
            _lastExh = exh;
            _lastImb = imb;
            _lastDel = del;
        }

        private void UpdateHud(int spreadTicks)
        {
            if (!ShowHUD)
            {
                RemoveDrawObject("DEEP6CoreHUD");
                return;
            }

            string dirText = _lastSignalDir > 0 ? "LONG" : (_lastSignalDir < 0 ? "SHORT" : "NONE");
            string hud = "DEEP6 CORE\n"
                + "Last: " + dirText + " | " + _lastSignalCats + " cats | " + _lastSignalTime + "\n"
                + "ABS " + Mark(_lastAbs) + "  EXH " + Mark(_lastExh) + "  IMB " + Mark(_lastImb) + "  DEL " + Mark(_lastDel) + "\n"
                + "Spread: " + spreadTicks + "t | Bars: " + _sessionBars;

            Draw.TextFixed(this, "DEEP6CoreHUD", hud, TextPosition.TopRight, Brushes.White,
                new SimpleFont("Consolas", 11), Brushes.Transparent, Brushes.Transparent, 0);
        }

        private static string Mark(bool on)
        {
            return on ? "✓" : "·";
        }

        private int SpreadTicks()
        {
            if (double.IsNaN(_bestBid) || double.IsNaN(_bestAsk) || _bestAsk <= _bestBid || TickSize <= 0)
                return 0;
            return (int)Math.Round((_bestAsk - _bestBid) / TickSize);
        }

        private static int Dominant(double bull, double bear)
        {
            if (bull > bear && bull > 0)
                return 1;
            if (bear > bull && bear > 0)
                return -1;
            return 0;
        }

        private static void AddVote(int direction, double weight, ref double bull, ref double bear)
        {
            if (direction > 0)
                bull += weight;
            else if (direction < 0)
                bear += weight;
        }

        private static void AddAbsorptionVote(int direction, double weight, ref double bull, ref double bear)
        {
            AddVote(direction, weight, ref bull, ref bear);
        }

        private static void AddExhaustionVote(int direction, double weight, ref double bull, ref double bear)
        {
            AddVote(direction, weight, ref bull, ref bear);
        }

        #region Properties
        [NinjaScriptProperty]
        [Range(2, 4)]
        [Display(Name = "MinCategories", Order = 1, GroupName = "Parameters")]
        public int MinCategories { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "PlaySound", Order = 2, GroupName = "Parameters")]
        public bool PlaySound { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowHUD", Order = 3, GroupName = "Parameters")]
        public bool ShowHUD { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowAlerts", Order = 4, GroupName = "Parameters")]
        public bool ShowAlerts { get; set; }

        [XmlIgnore]
        [Display(Name = "LongColor", Order = 1, GroupName = "Colors")]
        public Brush LongColor { get; set; }

        [Browsable(false)]
        [XmlIgnore]
        public string LongColorSerializable
        {
            get { return Serialize.BrushToString(LongColor); }
            set { LongColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [Display(Name = "ShortColor", Order = 2, GroupName = "Colors")]
        public Brush ShortColor { get; set; }

        [Browsable(false)]
        [XmlIgnore]
        public string ShortColorSerializable
        {
            get { return Serialize.BrushToString(ShortColor); }
            set { ShortColor = Serialize.StringToBrush(value); }
        }
        #endregion
    }
}

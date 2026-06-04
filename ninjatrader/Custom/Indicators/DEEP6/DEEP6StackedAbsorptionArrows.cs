#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public enum LevelType
    {
        None,
        Support,
        Resistance,
        Magnet,
        Neutral
    }

    public class DEEP6StackedAbsorptionArrows : Indicator
    {
        private const string LogPrefix = "[DEEP6SAC]";
        private const int MaxLevels = 30;
        private const int NqVolBip = 1;
        private const int EsVolBip = 2;

        private class TelegramLevel
        {
            public double Price;
            public LevelType Type;
            public bool SignalFired;
            public bool WasAway;
        }

        private readonly List<TelegramLevel> _levels = new List<TelegramLevel>();

        private NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType _nqVolBars;
        private NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType _esVolBars;

        private bool _warnedNoLevels;
        private bool _levelsLoaded;

        private bool _nqBullAbsorption;
        private bool _nqBearAbsorption;
        private bool _esBullAbsorption;
        private bool _esBearAbsorption;

        private int _nqBullAbsorptionBar = -999;
        private int _nqBearAbsorptionBar = -999;
        private int _esBullAbsorptionBar = -999;
        private int _esBearAbsorptionBar = -999;

        private TelegramLevel _nqBullLevel;
        private TelegramLevel _nqBearLevel;
        private TelegramLevel _esBullLevel;
        private TelegramLevel _esBearLevel;
        private TelegramLevel _pendingBullLevel;
        private TelegramLevel _pendingBearLevel;

        private double _lastNqBullVolume;
        private double _lastNqBearVolume;
        private double _lastEsBullVolume;
        private double _lastEsBearVolume;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6StackedAbsorptionArrows";
                Description = "NQ/ES stacked absorption confluence arrows near active session levels.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = false;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 20;
                ScaleJustification = ScaleJustification.Right;

                NqInstrument = string.Empty;
                EsInstrument = "ES 09-26";
                VolBarPeriod = 1;

                ManualLevel1 = 0.0;
                ManualLevel1Type = LevelType.None;
                ManualLevel2 = 0.0;
                ManualLevel2Type = LevelType.None;
                ManualLevel3 = 0.0;
                ManualLevel3Type = LevelType.None;
                ManualLevel4 = 0.0;
                ManualLevel4Type = LevelType.None;
                ManualLevel5 = 0.0;
                ManualLevel5Type = LevelType.None;
                CsvFilePath = string.Empty;

                MinStackedLevels = 3;
                MinVolumePerLevel_NQ = 500;
                MinVolumePerLevel_ES = 1000;
                MinTotalAbsorbedVolume = 1500;
                ProximityTicks = 10;

                ConfirmationWindow = 3;
                RequireConfirmationCandle = false;

                SessionStartTime = 83000;
                SessionEndTime = 153000;
                ResetDistanceTicks = 20;

                EnableAlerts = true;
                EnableSoundAlert = true;
                EnablePopupAlert = true;
            }
            else if (State == State.Configure)
            {
                string nqName = string.IsNullOrWhiteSpace(NqInstrument) ? Instrument.FullName : NqInstrument;
                AddVolumetric(nqName, BarsPeriodType.Minute, VolBarPeriod, VolumetricDeltaType.BidAsk, 1);
                AddVolumetric(EsInstrument, BarsPeriodType.Minute, VolBarPeriod, VolumetricDeltaType.BidAsk, 1);
            }
            else if (State == State.DataLoaded)
            {
                _nqVolBars = BarsArray.Length > NqVolBip
                    ? BarsArray[NqVolBip].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType
                    : null;
                _esVolBars = BarsArray.Length > EsVolBip
                    ? BarsArray[EsVolBip].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType
                    : null;

                LoadConfiguredLevels();
                ResetDetectionState();
            }
            else if (State == State.Terminated)
            {
                _levels.Clear();
                _nqVolBars = null;
                _esVolBars = null;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == NqVolBip)
            {
                ProcessNqVolumetricBar();
                return;
            }

            if (BarsInProgress == EsVolBip)
            {
                ProcessEsVolumetricBar();
                return;
            }

            if (BarsInProgress != 0)
                return;

            ProcessPrimaryBar();
        }

        private void ProcessPrimaryBar()
        {
            if (CurrentBar < BarsRequiredToPlot)
                return;

            if (CurrentBars.Length < 3 || CurrentBars[NqVolBip] < 0 || CurrentBars[EsVolBip] < 0)
                return;

            if (Bars.IsFirstBarOfSession)
            {
                foreach (TelegramLevel lv in _levels)
                {
                    lv.SignalFired = false;
                    lv.WasAway = false;
                }

                ResetDetectionState();
                Print(LogPrefix + " Session reset — levels refreshed");
            }

            if (_levels.Count == 0)
            {
                WarnNoLevels();
                return;
            }

            int t = ToTime(Time[0]);
            if (t < SessionStartTime || t > SessionEndTime)
                return;

            ApplyLevelResetLogic();

            if (RequireConfirmationCandle)
            {
                if (_pendingBullLevel != null && Close[0] <= Open[0])
                    _pendingBullLevel = null;
                if (_pendingBearLevel != null && Close[0] >= Open[0])
                    _pendingBearLevel = null;
            }

            TryDrawBullishSignal();
            TryDrawBearishSignal();
        }

        private void ProcessNqVolumetricBar()
        {
            if (_nqVolBars == null || _esVolBars == null)
                return;

            if (_levels.Count == 0)
            {
                WarnNoLevels();
                return;
            }

            if (CurrentBars[NqVolBip] < BarsRequiredToPlot)
                return;

            int barIdx = CurrentBars[NqVolBip];
            if (_nqVolBars.Volumes == null || barIdx < 0 || barIdx >= _nqVolBars.Volumes.Length)
                return;

            int primaryBar = GetPrimaryBarIndex(Times[NqVolBip][0]);
            double referenceClose;
            if (!TryGetPrimaryClose(primaryBar, out referenceClose))
                return;

            double nqTickSize = Instruments[NqVolBip].MasterInstrument.TickSize;

            TelegramLevel bullLevel;
            double bullVolume;
            if (TryDetectStackedAbsorption(_nqVolBars, NqVolBip, barIdx, referenceClose, true, nqTickSize, MinVolumePerLevel_NQ, out bullLevel, out bullVolume))
            {
                _nqBullAbsorption = true;
                _nqBullAbsorptionBar = primaryBar;
                _nqBullLevel = bullLevel;
                _lastNqBullVolume = bullVolume;
                _pendingBullLevel = ChoosePreferredLevel(_pendingBullLevel, bullLevel, referenceClose);
                Print(string.Format(CultureInfo.InvariantCulture, "{0} NQ bullish stacked absorption bar={1} primaryBar={2} close={3:F2} level={4:F2} volume={5:F0}", LogPrefix, barIdx, primaryBar, referenceClose, bullLevel.Price, bullVolume));
            }

            TelegramLevel bearLevel;
            double bearVolume;
            if (TryDetectStackedAbsorption(_nqVolBars, NqVolBip, barIdx, referenceClose, false, nqTickSize, MinVolumePerLevel_NQ, out bearLevel, out bearVolume))
            {
                _nqBearAbsorption = true;
                _nqBearAbsorptionBar = primaryBar;
                _nqBearLevel = bearLevel;
                _lastNqBearVolume = bearVolume;
                _pendingBearLevel = ChoosePreferredLevel(_pendingBearLevel, bearLevel, referenceClose);
                Print(string.Format(CultureInfo.InvariantCulture, "{0} NQ bearish stacked absorption bar={1} primaryBar={2} close={3:F2} level={4:F2} volume={5:F0}", LogPrefix, barIdx, primaryBar, referenceClose, bearLevel.Price, bearVolume));
            }
        }

        private void ProcessEsVolumetricBar()
        {
            if (_nqVolBars == null || _esVolBars == null)
                return;

            if (_levels.Count == 0)
            {
                WarnNoLevels();
                return;
            }

            if (CurrentBars[EsVolBip] < BarsRequiredToPlot)
                return;

            int barIdx = CurrentBars[EsVolBip];
            if (_esVolBars.Volumes == null || barIdx < 0 || barIdx >= _esVolBars.Volumes.Length)
                return;

            int primaryBar = GetPrimaryBarIndex(Times[EsVolBip][0]);
            double referenceClose;
            if (!TryGetPrimaryClose(primaryBar, out referenceClose))
                return;

            double esTickSize = Instruments[EsVolBip].MasterInstrument.TickSize;

            TelegramLevel bullLevel;
            double bullVolume;
            if (TryDetectStackedAbsorption(_esVolBars, EsVolBip, barIdx, referenceClose, true, esTickSize, MinVolumePerLevel_ES, out bullLevel, out bullVolume))
            {
                _esBullAbsorption = true;
                _esBullAbsorptionBar = primaryBar;
                _esBullLevel = bullLevel;
                _lastEsBullVolume = bullVolume;
                _pendingBullLevel = ChoosePreferredLevel(_pendingBullLevel, bullLevel, referenceClose);
                Print(string.Format(CultureInfo.InvariantCulture, "{0} ES bullish stacked absorption bar={1} primaryBar={2} close={3:F2} level={4:F2} volume={5:F0}", LogPrefix, barIdx, primaryBar, referenceClose, bullLevel.Price, bullVolume));
            }

            TelegramLevel bearLevel;
            double bearVolume;
            if (TryDetectStackedAbsorption(_esVolBars, EsVolBip, barIdx, referenceClose, false, esTickSize, MinVolumePerLevel_ES, out bearLevel, out bearVolume))
            {
                _esBearAbsorption = true;
                _esBearAbsorptionBar = primaryBar;
                _esBearLevel = bearLevel;
                _lastEsBearVolume = bearVolume;
                _pendingBearLevel = ChoosePreferredLevel(_pendingBearLevel, bearLevel, referenceClose);
                Print(string.Format(CultureInfo.InvariantCulture, "{0} ES bearish stacked absorption bar={1} primaryBar={2} close={3:F2} level={4:F2} volume={5:F0}", LogPrefix, barIdx, primaryBar, referenceClose, bearLevel.Price, bearVolume));
            }
        }

        private bool TryDetectStackedAbsorption(
            NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType volBars,
            int bipIndex,
            int barIdx,
            double referenceClose,
            bool isBullish,
            double instrTickSize,
            int minVolPerLevel,
            out TelegramLevel matchedLevel,
            out double totalAbsorbedVolume)
        {
            matchedLevel = null;
            totalAbsorbedVolume = 0.0;

            if (volBars == null || volBars.Volumes == null)
                return false;

            if (barIdx < 0 || barIdx >= volBars.Volumes.Length)
                return false;

            double barLow = Lows[bipIndex][0];
            double barHigh = Highs[bipIndex][0];
            if (barHigh < barLow)
                return false;

            int levelCount = (int)Math.Round((barHigh - barLow) / instrTickSize, MidpointRounding.AwayFromZero) + 1;
            if (levelCount <= 0)
                return false;

            foreach (TelegramLevel level in _levels)
            {
                if (!LevelAllowsDirection(level.Type, isBullish))
                    continue;

                if (Math.Abs(referenceClose - level.Price) > ProximityTicks * instrTickSize)
                    continue;

                int stackCount = 0;
                double detectedVolume = 0.0;

                for (int i = 0; i < levelCount; i++)
                {
                    double price = RoundToInstrumentTick(barLow + i * instrTickSize, instrTickSize);
                    double bidVol = volBars.Volumes[barIdx].GetBidVolumeForPrice(price);
                    double askVol = volBars.Volumes[barIdx].GetAskVolumeForPrice(price);
                    double checkVol = isBullish ? bidVol : askVol;

                    if (checkVol >= minVolPerLevel)
                    {
                        stackCount++;
                        detectedVolume += checkVol;
                    }
                }

                if (stackCount >= MinStackedLevels && detectedVolume >= MinTotalAbsorbedVolume)
                {
                    matchedLevel = level;
                    totalAbsorbedVolume = detectedVolume;
                    return true;
                }
            }

            return false;
        }

        private void TryDrawBullishSignal()
        {
            if (!_nqBullAbsorption || !_esBullAbsorption)
                return;

            if (_pendingBullLevel == null || _pendingBullLevel.SignalFired)
                return;

            if ((CurrentBar - _nqBullAbsorptionBar) > ConfirmationWindow)
                return;

            if ((CurrentBar - _esBullAbsorptionBar) > ConfirmationWindow)
                return;

            if (RequireConfirmationCandle && Close[0] <= Open[0])
                return;

            Draw.ArrowUp(this, "DEEP6SAC_Bull_" + CurrentBar, true, 0, Low[0] - 4 * TickSize, Brushes.Lime);
            _pendingBullLevel.SignalFired = true;
            _pendingBullLevel.WasAway = false;

            if (EnableAlerts && (EnablePopupAlert || EnableSoundAlert))
            {
                Alert(
                    "DEEP6SAC_Bull_" + CurrentBar,
                    Priority.High,
                    "Bullish ES/NQ stacked absorption confirmed near active session level.",
                    EnableSoundAlert ? NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav" : string.Empty,
                    10,
                    Brushes.Lime,
                    Brushes.Black);
            }

            Print(string.Format(
                CultureInfo.InvariantCulture,
                "{0} BULLISH SIGNAL bar={1} price={2:F2} level={3:F2} nqVol={4:F0} esVol={5:F0}",
                LogPrefix,
                CurrentBar,
                Close[0],
                _pendingBullLevel.Price,
                _lastNqBullVolume,
                _lastEsBullVolume));

            _nqBullAbsorption = false;
            _esBullAbsorption = false;
            _nqBullLevel = null;
            _esBullLevel = null;
            _pendingBullLevel = null;
            _nqBullAbsorptionBar = -999;
            _esBullAbsorptionBar = -999;
        }

        private void TryDrawBearishSignal()
        {
            if (!_nqBearAbsorption || !_esBearAbsorption)
                return;

            if (_pendingBearLevel == null || _pendingBearLevel.SignalFired)
                return;

            if ((CurrentBar - _nqBearAbsorptionBar) > ConfirmationWindow)
                return;

            if ((CurrentBar - _esBearAbsorptionBar) > ConfirmationWindow)
                return;

            if (RequireConfirmationCandle && Close[0] >= Open[0])
                return;

            Draw.ArrowDown(this, "DEEP6SAC_Bear_" + CurrentBar, true, 0, High[0] + 4 * TickSize, Brushes.Red);
            _pendingBearLevel.SignalFired = true;
            _pendingBearLevel.WasAway = false;

            if (EnableAlerts && (EnablePopupAlert || EnableSoundAlert))
            {
                Alert(
                    "DEEP6SAC_Bear_" + CurrentBar,
                    Priority.High,
                    "Bearish ES/NQ stacked absorption confirmed near active session level.",
                    EnableSoundAlert ? NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert1.wav" : string.Empty,
                    10,
                    Brushes.Red,
                    Brushes.Black);
            }

            Print(string.Format(
                CultureInfo.InvariantCulture,
                "{0} BEARISH SIGNAL bar={1} price={2:F2} level={3:F2} nqVol={4:F0} esVol={5:F0}",
                LogPrefix,
                CurrentBar,
                Close[0],
                _pendingBearLevel.Price,
                _lastNqBearVolume,
                _lastEsBearVolume));

            _nqBearAbsorption = false;
            _esBearAbsorption = false;
            _nqBearLevel = null;
            _esBearLevel = null;
            _pendingBearLevel = null;
            _nqBearAbsorptionBar = -999;
            _esBearAbsorptionBar = -999;
        }

        private void ApplyLevelResetLogic()
        {
            foreach (TelegramLevel lv in _levels)
            {
                if (!lv.SignalFired)
                    continue;

                double dist = Math.Abs(Close[0] - lv.Price) / TickSize;
                if (!lv.WasAway && dist >= ResetDistanceTicks)
                    lv.WasAway = true;
                else if (lv.WasAway && dist <= ProximityTicks)
                {
                    lv.SignalFired = false;
                    lv.WasAway = false;
                    Print(string.Format(CultureInfo.InvariantCulture, "{0} Level {1:F2} reset — price returned after moving away", LogPrefix, lv.Price));
                }
            }
        }

        private void LoadConfiguredLevels()
        {
            if (_levelsLoaded)
                return;

            _levels.Clear();

            AddManualLevel(ManualLevel1, ManualLevel1Type);
            AddManualLevel(ManualLevel2, ManualLevel2Type);
            AddManualLevel(ManualLevel3, ManualLevel3Type);
            AddManualLevel(ManualLevel4, ManualLevel4Type);
            AddManualLevel(ManualLevel5, ManualLevel5Type);
            LoadLevelsFromCsv();

            _levelsLoaded = true;
            Print(string.Format(CultureInfo.InvariantCulture, "{0} Active levels loaded: {1}", LogPrefix, _levels.Count));
        }

        private void AddManualLevel(double price, LevelType type)
        {
            if (price <= 0 || type == LevelType.None)
                return;

            if (_levels.Count >= MaxLevels)
                return;

            _levels.Add(new TelegramLevel
            {
                Price = Instrument.MasterInstrument.RoundToTickSize(price),
                Type = type,
                SignalFired = false,
                WasAway = false
            });
        }

        private void LoadLevelsFromCsv()
        {
            if (string.IsNullOrWhiteSpace(CsvFilePath))
                return;

            if (!File.Exists(CsvFilePath))
            {
                Print(LogPrefix + " CSV file not found: " + CsvFilePath);
                return;
            }

            string[] lines;
            try
            {
                lines = File.ReadAllLines(CsvFilePath);
            }
            catch (Exception ex)
            {
                Print(string.Format(CultureInfo.InvariantCulture, "{0} CSV read error: {1}", LogPrefix, ex.Message));
                return;
            }

            int loaded = 0;
            foreach (string line in lines)
            {
                if (string.IsNullOrWhiteSpace(line))
                    continue;

                string[] parts = line.Split(',');
                if (parts.Length < 2)
                {
                    Print(LogPrefix + " CSV bad line: " + line);
                    continue;
                }

                double price;
                if (!double.TryParse(parts[0].Trim(), NumberStyles.Any, CultureInfo.InvariantCulture, out price))
                {
                    Print(LogPrefix + " CSV bad price: " + parts[0]);
                    continue;
                }

                LevelType levelType = ParseLevelType(parts[1].Trim());
                if (levelType == LevelType.None)
                {
                    Print(LogPrefix + " CSV skipped inactive type: " + line);
                    continue;
                }

                if (_levels.Count >= MaxLevels)
                {
                    Print(LogPrefix + " CSV: max 30 levels reached, truncating");
                    break;
                }

                _levels.Add(new TelegramLevel
                {
                    Price = Instrument.MasterInstrument.RoundToTickSize(price),
                    Type = levelType,
                    SignalFired = false,
                    WasAway = false
                });
                loaded++;
            }

            Print(string.Format(CultureInfo.InvariantCulture, "{0} Loaded {1} levels from CSV", LogPrefix, loaded));
        }

        private LevelType ParseLevelType(string raw)
        {
            if (string.IsNullOrWhiteSpace(raw))
                return LevelType.None;

            LevelType parsed;
            if (Enum.TryParse(raw, true, out parsed))
                return parsed;

            string normalized = raw.Trim().ToLowerInvariant();
            if (normalized == "s") return LevelType.Support;
            if (normalized == "r") return LevelType.Resistance;
            if (normalized == "m") return LevelType.Magnet;
            if (normalized == "n") return LevelType.Neutral;
            return LevelType.None;
        }

        private static bool LevelAllowsDirection(LevelType levelType, bool isBullish)
        {
            switch (levelType)
            {
                case LevelType.Support:
                    return isBullish;
                case LevelType.Resistance:
                    return !isBullish;
                case LevelType.Magnet:
                case LevelType.Neutral:
                    return true;
                default:
                    return false;
            }
        }

        private int GetPrimaryBarIndex(DateTime barTime)
        {
            if (BarsArray == null || BarsArray.Length == 0 || BarsArray[0] == null)
                return -1;

            return BarsArray[0].GetBar(barTime);
        }

        private bool TryGetPrimaryClose(int primaryBar, out double close)
        {
            close = 0.0;
            if (primaryBar < 0 || CurrentBars[0] < primaryBar)
                return false;

            int barsAgo = CurrentBars[0] - primaryBar;
            if (barsAgo < 0)
                return false;

            close = Closes[0][barsAgo];
            return true;
        }

        private TelegramLevel ChoosePreferredLevel(TelegramLevel existingLevel, TelegramLevel candidateLevel, double referenceClose)
        {
            if (candidateLevel == null)
                return existingLevel;

            if (existingLevel == null)
                return candidateLevel;

            double existingDist = Math.Abs(referenceClose - existingLevel.Price);
            double candidateDist = Math.Abs(referenceClose - candidateLevel.Price);
            return candidateDist <= existingDist ? candidateLevel : existingLevel;
        }

        private static double RoundToInstrumentTick(double price, double tickSize)
        {
            if (tickSize <= 0)
                return price;

            return Math.Round(price / tickSize, MidpointRounding.AwayFromZero) * tickSize;
        }

        private void WarnNoLevels()
        {
            if (_warnedNoLevels)
                return;

            Print(LogPrefix + " WARNING: No levels configured — indicator inactive. Add levels via settings or CSV.");
            _warnedNoLevels = true;
        }

        private void ResetDetectionState()
        {
            _nqBullAbsorption = false;
            _nqBearAbsorption = false;
            _esBullAbsorption = false;
            _esBearAbsorption = false;

            _nqBullAbsorptionBar = -999;
            _nqBearAbsorptionBar = -999;
            _esBullAbsorptionBar = -999;
            _esBearAbsorptionBar = -999;

            _nqBullLevel = null;
            _nqBearLevel = null;
            _esBullLevel = null;
            _esBearLevel = null;
            _pendingBullLevel = null;
            _pendingBearLevel = null;

            _lastNqBullVolume = 0.0;
            _lastNqBearVolume = 0.0;
            _lastEsBullVolume = 0.0;
            _lastEsBearVolume = 0.0;
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "NQ Instrument (blank = chart)", GroupName = "1. Instruments", Order = 0)]
        public string NqInstrument { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ES Instrument", GroupName = "1. Instruments", Order = 1)]
        public string EsInstrument { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "Vol Bar Period", GroupName = "1. Instruments", Order = 2)]
        public int VolBarPeriod { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 1", GroupName = "2. Manual Levels", Order = 1)]
        public double ManualLevel1 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 1 Type", GroupName = "2. Manual Levels", Order = 2)]
        public LevelType ManualLevel1Type { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 2", GroupName = "2. Manual Levels", Order = 3)]
        public double ManualLevel2 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 2 Type", GroupName = "2. Manual Levels", Order = 4)]
        public LevelType ManualLevel2Type { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 3", GroupName = "2. Manual Levels", Order = 5)]
        public double ManualLevel3 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 3 Type", GroupName = "2. Manual Levels", Order = 6)]
        public LevelType ManualLevel3Type { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 4", GroupName = "2. Manual Levels", Order = 7)]
        public double ManualLevel4 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 4 Type", GroupName = "2. Manual Levels", Order = 8)]
        public LevelType ManualLevel4Type { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 5", GroupName = "2. Manual Levels", Order = 9)]
        public double ManualLevel5 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Manual Level 5 Type", GroupName = "2. Manual Levels", Order = 10)]
        public LevelType ManualLevel5Type { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "CSV File Path", GroupName = "2. Manual Levels", Order = 11)]
        public string CsvFilePath { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Min Stacked Levels", GroupName = "3. Absorption", Order = 1)]
        public int MinStackedLevels { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Min Volume Per Level NQ", GroupName = "3. Absorption", Order = 2)]
        public int MinVolumePerLevel_NQ { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Min Volume Per Level ES", GroupName = "3. Absorption", Order = 3)]
        public int MinVolumePerLevel_ES { get; set; }

        [NinjaScriptProperty]
        [Range(1, int.MaxValue)]
        [Display(Name = "Min Total Absorbed Volume", GroupName = "3. Absorption", Order = 4)]
        public int MinTotalAbsorbedVolume { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "Proximity Ticks", GroupName = "3. Absorption", Order = 5)]
        public int ProximityTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "Confirmation Window", GroupName = "4. Confluence", Order = 1)]
        public int ConfirmationWindow { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Require Confirmation Candle", GroupName = "4. Confluence", Order = 2)]
        public bool RequireConfirmationCandle { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "Session Start Time", GroupName = "5. Session", Order = 1)]
        public int SessionStartTime { get; set; }

        [NinjaScriptProperty]
        [Range(0, 235959)]
        [Display(Name = "Session End Time", GroupName = "5. Session", Order = 2)]
        public int SessionEndTime { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "Reset Distance Ticks", GroupName = "5. Session", Order = 3)]
        public int ResetDistanceTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Alerts", GroupName = "6. Alerts", Order = 1)]
        public bool EnableAlerts { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Sound Alert", GroupName = "6. Alerts", Order = 2)]
        public bool EnableSoundAlert { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Enable Popup Alert", GroupName = "6. Alerts", Order = 3)]
        public bool EnablePopupAlert { get; set; }
        #endregion
    }
}

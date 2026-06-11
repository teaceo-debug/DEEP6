#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.Windows.Media;
using NinjaTrader.Data;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6CompoundSignalsV3 : Indicator
    {
        private const string LogPrefix = "[DEEP6CompoundSignalsV3]";
        private const int Hour60Bip = 1;
        private const int Min15Bip = 2;

        private class VolumetricSnapshot
        {
            public long BarDelta;
            public long TotalVolume;
            public double Open;
            public double High;
            public double Low;
            public double Close;
        }

        private NinjaTrader.NinjaScript.Indicators.ATR _atr20;

        private readonly Queue<double> _volumeHistory = new Queue<double>();
        private readonly Queue<double> _atrHistory = new Queue<double>();
        private readonly Queue<double> _volOfVolHistory = new Queue<double>();
        private readonly Queue<double> _deltaVolRatioHistory = new Queue<double>();
        private readonly Queue<double> _sameDirDeltaAbsHistory = new Queue<double>();

        private double _volumeEma20;
        private bool _volumeEmaSeeded;

        private bool _openingRangeReady;
        private double _openingRangeHigh;
        private double _openingRangeLow;
        private double _sessionOpen;
        private double _priorSessionClose;

        private double _sessionLowPrice;
        private long _sessionLowCvd;
        private double _sessionHighPrice;
        private long _sessionHighCvd;
        private long _sessionCvd;
        private bool _sessionExtremesSeeded;

        private int _lastSignalBar = -1;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "DEEP6CompoundSignalsV3";
                Description = "DEEP6 compound signal indicator V3: ultra-selective reversal prints using only backtest-screened trigger families by default.";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DrawOnPricePanel = true;
                DisplayInDataBox = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = true;
                BarsRequiredToPlot = 60;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;

                EnableTier1 = true;
                EnableTier2 = false;
                EnableTier3 = false;
                EnableAlerts = true;
                ShowPatternLabels = true;
                ExcludeLunch = true;
                FirstHourOnly = true;
                ShowKillerZone = false;
                EnableFailedORTrigger = false;
                EnableCvdDojiTrigger = false;
                EnableAdaptiveDojiTrigger = true;
                RequireCleanContext = true;

                ExtremeThreshold = 0.10;
                MiddleRangeLow = 0.40;
                MiddleRangeHigh = 0.60;
                VolumeSpikeMultiplier = 2.0;
                LowDeltaVolThreshold = 0.035;
                DeltaVolQuantileLookback = 60;
                StableVolLookback = 50;
                VolOfVolLookback = 12;
                StableVolPercentile = 0.20;
                SmallOvernightMovePoints = 5.0;
                ScoreTier1 = 56;
                ScoreTier2 = 50;
                ScoreTier3 = 45;
                StopTicks = 80;
                AbsorptionStopTicks = 40;

                AddPlot(Brushes.Transparent, "SignalDirection");
                AddPlot(Brushes.Transparent, "CompositeScore");
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 60);
                AddDataSeries(BarsPeriodType.Minute, 15);
            }
            else if (State == State.DataLoaded)
            {
                _atr20 = ATR(20);
                ResetSessionState();
            }
            else if (State == State.Terminated)
            {
                _atr20 = null;
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            if (CurrentBar < BarsRequiredToPlot)
                return;

            if (CurrentBars.Length < 3 || CurrentBars[Hour60Bip] < 0 || CurrentBars[Min15Bip] < 0)
                return;

            if (Bars.IsFirstBarOfSession)
            {
                _priorSessionClose = CurrentBar > 0 ? Close[1] : Close[0];
                ResetSessionState();
                _sessionOpen = Open[0];
            }

            UpdateOpeningRange();

            VolumetricSnapshot snapshot = BuildPrimaryBarSnapshot();

            UpdateRollingMetrics(snapshot);

            SignalDecision bull = BuildBullishDecision(snapshot);
            SignalDecision bear = BuildBearishDecision(snapshot);

            Values[0][0] = 0.0;
            Values[1][0] = 0.0;

            if (bull.IsValid && bear.IsValid)
            {
                if (bull.Score > bear.Score)
                    bear.IsValid = false;
                else if (bear.Score > bull.Score)
                    bull.IsValid = false;
                else
                {
                    bull.IsValid = false;
                    bear.IsValid = false;
                }
            }

            if (bull.IsValid)
                RenderDecision(bull, true);
            else if (bear.IsValid)
                RenderDecision(bear, false);

            UpdateSessionDivergenceAnchors(snapshot);
        }

        private VolumetricSnapshot BuildPrimaryBarSnapshot()
        {
            VolumetricSnapshot snap = new VolumetricSnapshot();
            snap.TotalVolume = (long)Volume[0];
            snap.Open = Open[0];
            snap.High = High[0];
            snap.Low = Low[0];
            snap.Close = Close[0];
            snap.BarDelta = (long)Math.Round(ComputeBarDeltaProxy(), MidpointRounding.AwayFromZero);
            return snap;
        }

        private double ComputeBarDeltaProxy()
        {
            double range = Math.Max(TickSize, High[0] - Low[0]);
            double body = Close[0] - Open[0];
            double bodyBias = body / range;
            double closeLocation = ((Close[0] - Low[0]) / range) - 0.5;
            double combined = (bodyBias * 0.7) + (closeLocation * 0.6);
            return Volume[0] * combined;
        }

        private void UpdateOpeningRange()
        {
            int t = ToTime(Time[0]);
            if (t >= 93000 && t <= 94500)
            {
                if (!_openingRangeReady)
                {
                    _openingRangeHigh = High[0];
                    _openingRangeLow = Low[0];
                    _openingRangeReady = true;
                }
                else
                {
                    if (High[0] > _openingRangeHigh)
                        _openingRangeHigh = High[0];
                    if (Low[0] < _openingRangeLow)
                        _openingRangeLow = Low[0];
                }
            }
        }

        private void UpdateRollingMetrics(VolumetricSnapshot snapshot)
        {
            double volumeNow = Math.Max(1.0, Volume[0]);
            UpdateVolumeEma(volumeNow);

            double atrNow = _atr20 != null ? _atr20[0] : (High[0] - Low[0]);
            PushBounded(_atrHistory, atrNow, Math.Max(VolOfVolLookback + 5, StableVolLookback));

            if (_atrHistory.Count >= VolOfVolLookback)
            {
                double volOfVol = ComputeStdDevFromQueueTail(_atrHistory, VolOfVolLookback);
                PushBounded(_volOfVolHistory, volOfVol, StableVolLookback);
            }

            double deltaVolRatio = snapshot.TotalVolume > 0
                ? Math.Abs(snapshot.BarDelta) / Math.Max(1.0, snapshot.TotalVolume)
                : 1.0;
            PushBounded(_deltaVolRatioHistory, deltaVolRatio, Math.Max(DeltaVolQuantileLookback, 60));

            if (snapshot.BarDelta != 0)
                PushBounded(_sameDirDeltaAbsHistory, Math.Abs(snapshot.BarDelta), 90);

            _sessionCvd += snapshot.BarDelta;
        }

        private SignalDecision BuildBullishDecision(VolumetricSnapshot snapshot)
        {
            SignalDecision d = new SignalDecision();
            d.Direction = 1;

            if (!IsBullishExtreme())
                return d;
            if (!IsFifteenMinuteTrendAligned(1))
                return d;
            if (FirstHourOnly && !IsFirstHour())
                return d;
            if (ExcludeLunch && IsLunch())
                return d;

            double pos60 = GetBullishPosIn60m();
            bool inMiddle = pos60 >= MiddleRangeLow && pos60 <= MiddleRangeHigh;
            bool volumeSpike = Volume[0] > (_volumeEma20 * VolumeSpikeMultiplier);
            bool sameDirDeltaSpike = snapshot.BarDelta > 0 && Math.Abs(snapshot.BarDelta) > GetPercentile(_sameDirDeltaAbsHistory, 0.90);
            bool notKillers = !inMiddle && !volumeSpike && !sameDirDeltaSpike;

            bool isDoji = IsDoji();
            bool bullishDoji = isDoji && snapshot.BarDelta > 0;
            bool bullishCvdDiv = IsBullishCvdDivergence();
            bool bullishFailedOR = IsBullishFailedOpeningRangeBreakdown();
            bool adaptiveLowDelta = IsAdaptiveLowDeltaVolume(snapshot);
            bool stableVol = IsStableVolatility();
            bool narrowing = IsThreeNarrowingRanges();
            bool firstHour = IsFirstHour();
            bool notLunch = !IsLunch();

            bool triggerFailedOr = EnableFailedORTrigger && bullishFailedOR;
            bool triggerCvdDoji = EnableCvdDojiTrigger && bullishCvdDiv && bullishDoji;
            bool triggerAdaptiveDoji = EnableAdaptiveDojiTrigger && adaptiveLowDelta && isDoji;

            int triggerCount = (triggerFailedOr ? 1 : 0)
                + (triggerCvdDoji ? 1 : 0)
                + (triggerAdaptiveDoji ? 1 : 0);

            if (triggerCount == 0)
                return d;
            if (RequireCleanContext && !notKillers)
                return d;

            int score = 0;
            score += triggerFailedOr ? 40 : 0;
            score += triggerCvdDoji ? 38 : 0;
            score += triggerAdaptiveDoji ? 34 : 0;
            score += firstHour ? 8 : 0;
            score += notKillers ? 6 : -12;
            score += notLunch ? 4 : -8;
            score += narrowing && bullishCvdDiv ? 4 : 0;
            score += adaptiveLowDelta ? 4 : 0;
            score += stableVol ? 4 : 0;
            score += triggerCount >= 2 ? 6 : 0;
            score += bullishCvdDiv && bullishFailedOR ? 5 : 0;

            int tier = 1;
            if (!IsTierEnabled(tier))
                return d;
            if (score < ScoreTier1)
                return d;

            d.IsValid = true;
            d.Score = score;
            d.Tier = tier;
            d.Tag = BuildTag("BULL", tier);
            d.Price = Low[0] - (4 * TickSize);
            d.Label = BuildBullishLabel(false, bullishDoji, bullishCvdDiv, narrowing, false, bullishFailedOR, adaptiveLowDelta);
            return d;
        }

        private SignalDecision BuildBearishDecision(VolumetricSnapshot snapshot)
        {
            SignalDecision d = new SignalDecision();
            d.Direction = -1;

            if (!IsBearishExtreme())
                return d;
            if (!IsFifteenMinuteTrendAligned(-1))
                return d;
            if (FirstHourOnly && !IsFirstHour())
                return d;
            if (ExcludeLunch && IsLunch())
                return d;

            double pos60 = GetBearishPosIn60m();
            bool inMiddle = pos60 >= MiddleRangeLow && pos60 <= MiddleRangeHigh;
            bool volumeSpike = Volume[0] > (_volumeEma20 * VolumeSpikeMultiplier);
            bool sameDirDeltaSpike = snapshot.BarDelta < 0 && Math.Abs(snapshot.BarDelta) > GetPercentile(_sameDirDeltaAbsHistory, 0.90);
            bool notKillers = !inMiddle && !volumeSpike && !sameDirDeltaSpike;

            bool isDoji = IsDoji();
            bool bearishDoji = isDoji && snapshot.BarDelta < 0;
            bool bearishCvdDiv = IsBearishCvdDivergence();
            bool bearishFailedOR = IsBearishFailedOpeningRangeBreakout();
            bool adaptiveLowDelta = IsAdaptiveLowDeltaVolume(snapshot);
            bool stableVol = IsStableVolatility();
            bool narrowing = IsThreeNarrowingRanges();
            bool firstHour = IsFirstHour();
            bool notLunch = !IsLunch();

            bool triggerFailedOr = EnableFailedORTrigger && bearishFailedOR;
            bool triggerCvdDoji = EnableCvdDojiTrigger && bearishCvdDiv && bearishDoji;
            bool triggerAdaptiveDoji = EnableAdaptiveDojiTrigger && adaptiveLowDelta && isDoji;

            int triggerCount = (triggerFailedOr ? 1 : 0)
                + (triggerCvdDoji ? 1 : 0)
                + (triggerAdaptiveDoji ? 1 : 0);

            if (triggerCount == 0)
                return d;
            if (RequireCleanContext && !notKillers)
                return d;

            int score = 0;
            score += triggerFailedOr ? 40 : 0;
            score += triggerCvdDoji ? 38 : 0;
            score += triggerAdaptiveDoji ? 34 : 0;
            score += firstHour ? 8 : 0;
            score += notKillers ? 6 : -12;
            score += notLunch ? 4 : -8;
            score += narrowing && bearishCvdDiv ? 4 : 0;
            score += adaptiveLowDelta ? 4 : 0;
            score += stableVol ? 4 : 0;
            score += triggerCount >= 2 ? 6 : 0;
            score += bearishCvdDiv && bearishFailedOR ? 5 : 0;

            int tier = 1;
            if (!IsTierEnabled(tier))
                return d;
            if (score < ScoreTier1)
                return d;

            d.IsValid = true;
            d.Score = score;
            d.Tier = tier;
            d.Tag = BuildTag("BEAR", tier);
            d.Price = High[0] + (4 * TickSize);
            d.Label = BuildBearishLabel(false, bearishDoji, bearishCvdDiv, narrowing, false, bearishFailedOR, adaptiveLowDelta);
            return d;
        }

        private void RenderDecision(SignalDecision decision, bool bullish)
        {
            if (CurrentBar == _lastSignalBar)
                return;

            Brush brush = GetTierBrush(decision.Tier);
            Values[0][0] = decision.Direction;
            Values[1][0] = decision.Score;

            if (bullish)
                Draw.ArrowUp(this, decision.Tag, true, 0, decision.Price, brush);
            else
                Draw.ArrowDown(this, decision.Tag, true, 0, decision.Price, brush);

            if (ShowPatternLabels)
            {
                Draw.Text(this, decision.Tag + "_TXT", decision.Label + "  S=" + decision.Score.ToString(CultureInfo.InvariantCulture), 0,
                    bullish ? (decision.Price - (4 * TickSize)) : (decision.Price + (4 * TickSize)), brush);
            }

            if (EnableAlerts && decision.Tier == 1)
            {
                Alert(decision.Tag + "_ALERT", Priority.Medium,
                    (bullish ? "BULL" : "BEAR") + " DEEP6 compound Tier " + decision.Tier + " " + decision.Label,
                    NinjaTrader.Core.Globals.InstallDir + @"\sounds\Alert4.wav", 0, brush, Brushes.Black);
            }

            if (ShowKillerZone)
                DrawKillerZone();

            Print(string.Format(CultureInfo.InvariantCulture,
                "{0} {1} tier={2} score={3} close={4:F2} stopTicks={5} absStopTicks={6} label={7}",
                LogPrefix, bullish ? "LONG" : "SHORT", decision.Tier, decision.Score, Close[0], StopTicks, AbsorptionStopTicks, decision.Label));

            _lastSignalBar = CurrentBar;
        }

        private void DrawKillerZone()
        {
            double high60 = Highs[Hour60Bip][0];
            double low60 = Lows[Hour60Bip][0];
            double range60 = Math.Max(TickSize, high60 - low60);
            double zoneLow = low60 + (range60 * MiddleRangeLow);
            double zoneHigh = low60 + (range60 * MiddleRangeHigh);
            Draw.Rectangle(this, "KILLER_" + CurrentBar, false, 0, zoneHigh, 0, zoneLow, Brushes.Transparent, Brushes.Red, 10);
        }

        private bool IsBullishExtreme()
        {
            return GetBullishPosIn60m() <= ExtremeThreshold;
        }

        private bool IsBearishExtreme()
        {
            return GetBearishPosIn60m() >= (1.0 - ExtremeThreshold);
        }

        private double GetBullishPosIn60m()
        {
            double high60 = Highs[Hour60Bip][0];
            double low60 = Lows[Hour60Bip][0];
            double range60 = Math.Max(TickSize, high60 - low60);
            return (Low[0] - low60) / range60;
        }

        private double GetBearishPosIn60m()
        {
            double high60 = Highs[Hour60Bip][0];
            double low60 = Lows[Hour60Bip][0];
            double range60 = Math.Max(TickSize, high60 - low60);
            return (High[0] - low60) / range60;
        }

        private bool IsFifteenMinuteTrendAligned(int direction)
        {
            double diff = Closes[Min15Bip][0] - Opens[Min15Bip][0];
            if (direction > 0)
                return diff > 0;
            return diff < 0;
        }

        private bool IsFirstHour()
        {
            int t = ToTime(Time[0]);
            return t >= 93000 && t <= 103000;
        }

        private bool IsLunch()
        {
            int t = ToTime(Time[0]);
            return t >= 120000 && t <= 140000;
        }

        private bool IsDoji()
        {
            double range = Math.Max(TickSize, High[0] - Low[0]);
            double body = Math.Abs(Close[0] - Open[0]);
            return range > 0 && (body / range) < 0.10;
        }

        private bool IsThreeNarrowingRanges()
        {
            if (CurrentBar < 2)
                return false;
            double r0 = High[0] - Low[0];
            double r1 = High[1] - Low[1];
            double r2 = High[2] - Low[2];
            return r0 < r1 && r1 < r2;
        }

        private bool IsBullishMorningStar()
        {
            if (CurrentBar < 2)
                return false;
            double range1 = Math.Max(TickSize, High[1] - Low[1]);
            double body1 = Math.Abs(Close[1] - Open[1]);
            double midpoint = (Open[2] + Close[2]) * 0.5;
            return Close[2] < Open[2]
                && (body1 / range1) < 0.10
                && Close[0] > Open[0]
                && Close[0] > midpoint;
        }

        private bool IsBearishEveningStar()
        {
            if (CurrentBar < 2)
                return false;
            double range1 = Math.Max(TickSize, High[1] - Low[1]);
            double body1 = Math.Abs(Close[1] - Open[1]);
            double midpoint = (Open[2] + Close[2]) * 0.5;
            return Close[2] > Open[2]
                && (body1 / range1) < 0.10
                && Close[0] < Open[0]
                && Close[0] < midpoint;
        }

        private bool IsBullishHammer()
        {
            double body = Math.Abs(Close[0] - Open[0]);
            double lowerWick = Math.Min(Open[0], Close[0]) - Low[0];
            double upperWick = High[0] - Math.Max(Open[0], Close[0]);
            return lowerWick > (2.0 * body) && upperWick < (0.5 * Math.Max(body, TickSize)) && Close[0] > Open[0];
        }

        private bool IsBearishShootingStar()
        {
            double body = Math.Abs(Close[0] - Open[0]);
            double lowerWick = Math.Min(Open[0], Close[0]) - Low[0];
            double upperWick = High[0] - Math.Max(Open[0], Close[0]);
            return upperWick > (2.0 * body) && lowerWick < (0.5 * Math.Max(body, TickSize)) && Close[0] < Open[0];
        }

        private bool IsBullishEngulfing()
        {
            if (CurrentBar < 1)
                return false;
            double currentHigh = Math.Max(Open[0], Close[0]);
            double currentLow = Math.Min(Open[0], Close[0]);
            double priorHigh = Math.Max(Open[1], Close[1]);
            double priorLow = Math.Min(Open[1], Close[1]);
            return Close[0] > Open[0] && currentHigh > priorHigh && currentLow < priorLow;
        }

        private bool IsBearishEngulfing()
        {
            if (CurrentBar < 1)
                return false;
            double currentHigh = Math.Max(Open[0], Close[0]);
            double currentLow = Math.Min(Open[0], Close[0]);
            double priorHigh = Math.Max(Open[1], Close[1]);
            double priorLow = Math.Min(Open[1], Close[1]);
            return Close[0] < Open[0] && currentHigh > priorHigh && currentLow < priorLow;
        }

        private bool IsBullishCvdDivergence()
        {
            if (!_sessionExtremesSeeded)
                return false;
            return Low[0] <= _sessionLowPrice && _sessionCvd > _sessionLowCvd;
        }

        private bool IsBearishCvdDivergence()
        {
            if (!_sessionExtremesSeeded)
                return false;
            return High[0] >= _sessionHighPrice && _sessionCvd < _sessionHighCvd;
        }

        private bool IsBullishFailedOpeningRangeBreakdown()
        {
            if (!_openingRangeReady)
                return false;
            return Low[0] < _openingRangeLow && Close[0] > _openingRangeLow;
        }

        private bool IsBearishFailedOpeningRangeBreakout()
        {
            if (!_openingRangeReady)
                return false;
            return High[0] > _openingRangeHigh && Close[0] < _openingRangeHigh;
        }

        private bool IsStableVolatility()
        {
            if (_volOfVolHistory.Count < Math.Max(10, StableVolLookback / 2))
                return false;
            double current = GetLastFromQueue(_volOfVolHistory);
            double threshold = GetPercentile(_volOfVolHistory, StableVolPercentile);
            return current <= threshold;
        }

        private bool IsLowDeltaVolume(VolumetricSnapshot snapshot)
        {
            if (snapshot.TotalVolume <= 0)
                return false;
            return (Math.Abs(snapshot.BarDelta) / Math.Max(1.0, snapshot.TotalVolume)) < LowDeltaVolThreshold;
        }

        private bool IsAdaptiveLowDeltaVolume(VolumetricSnapshot snapshot)
        {
            if (_deltaVolRatioHistory.Count < Math.Max(10, DeltaVolQuantileLookback / 2) || snapshot.TotalVolume <= 0)
                return false;
            double ratio = Math.Abs(snapshot.BarDelta) / Math.Max(1.0, snapshot.TotalVolume);
            return ratio <= GetPercentile(_deltaVolRatioHistory, 0.10);
        }

        private bool IsSmallOvernightMove()
        {
            if (_priorSessionClose <= 0 || _sessionOpen <= 0)
                return false;
            return Math.Abs(_sessionOpen - _priorSessionClose) < SmallOvernightMovePoints;
        }

        private bool IsBullishAbsorptionProxy(VolumetricSnapshot snapshot)
        {
            if (snapshot.TotalVolume <= 0)
                return false;
            double ratio = Math.Abs(snapshot.BarDelta) / Math.Max(1.0, snapshot.TotalVolume);
            double lowerWick = Math.Min(Open[0], Close[0]) - Low[0];
            double body = Math.Abs(Close[0] - Open[0]);
            return ratio < LowDeltaVolThreshold && lowerWick > (1.5 * Math.Max(body, TickSize)) && Close[0] >= Open[0];
        }

        private bool IsBearishAbsorptionProxy(VolumetricSnapshot snapshot)
        {
            if (snapshot.TotalVolume <= 0)
                return false;
            double ratio = Math.Abs(snapshot.BarDelta) / Math.Max(1.0, snapshot.TotalVolume);
            double upperWick = High[0] - Math.Max(Open[0], Close[0]);
            double body = Math.Abs(Close[0] - Open[0]);
            return ratio < LowDeltaVolThreshold && upperWick > (1.5 * Math.Max(body, TickSize)) && Close[0] <= Open[0];
        }

        private bool IsPriorWideRangeDay()
        {
            if (CurrentBar < 20)
                return false;
            double priorRange = High[1] - Low[1];
            double avgRange = 0.0;
            int count = 0;
            for (int i = 2; i <= Math.Min(CurrentBar, 21); i++)
            {
                avgRange += (High[i] - Low[i]);
                count++;
            }
            if (count == 0)
                return false;
            avgRange /= count;
            return priorRange > (1.5 * avgRange);
        }

        private bool IsWeeklyBreakout()
        {
            if (CurrentBar < 20)
                return false;
            double highest = MAX(High, 20)[1];
            double lowest = MIN(Low, 20)[1];
            return High[0] > highest || Low[0] < lowest;
        }

        private bool IsApproxFomcWindow()
        {
            int t = ToTime(Time[0]);
            if (t < 133000 || t > 143500)
                return false;
            return Time[0].DayOfWeek == DayOfWeek.Wednesday;
        }

        private void UpdateSessionDivergenceAnchors(VolumetricSnapshot snapshot)
        {
            if (!_sessionExtremesSeeded)
            {
                _sessionLowPrice = Low[0];
                _sessionLowCvd = _sessionCvd;
                _sessionHighPrice = High[0];
                _sessionHighCvd = _sessionCvd;
                _sessionExtremesSeeded = true;
                return;
            }

            if (Low[0] < _sessionLowPrice)
            {
                _sessionLowPrice = Low[0];
                _sessionLowCvd = _sessionCvd;
            }

            if (High[0] > _sessionHighPrice)
            {
                _sessionHighPrice = High[0];
                _sessionHighCvd = _sessionCvd;
            }
        }

        private int ResolveTier(int score, bool premiumCombo, bool absorptionProxy)
        {
            if ((premiumCombo || absorptionProxy) && score >= ScoreTier1)
                return 1;
            if (score >= ScoreTier1)
                return 1;
            if (score >= ScoreTier2)
                return 2;
            return 3;
        }

        private bool IsTierEnabled(int tier)
        {
            if (tier == 1)
                return EnableTier1;
            if (tier == 2)
                return EnableTier2;
            return EnableTier3;
        }

        private string BuildBullishLabel(bool stableVol, bool doji, bool cvdDiv, bool narrowing, bool absorptionProxy, bool failedOr, bool adaptiveLowDelta)
        {
            if (absorptionProxy)
                return stableVol ? "ABS+STABLE" : "ABS";
            if (cvdDiv && doji)
                return "CVD+DOJI";
            if (narrowing && cvdDiv)
                return "NARROW+CVD";
            if (adaptiveLowDelta && doji)
                return "Q10+DOJI";
            if (failedOr)
                return "FAILED OR";
            if (doji)
                return "DOJI";
            if (stableVol)
                return "WORKHORSE";
            return "CORE LONG";
        }

        private string BuildBearishLabel(bool stableVol, bool doji, bool cvdDiv, bool narrowing, bool absorptionProxy, bool failedOr, bool adaptiveLowDelta)
        {
            if (absorptionProxy)
                return stableVol ? "ABS+STABLE" : "ABS";
            if (cvdDiv && doji)
                return "CVD+DOJI";
            if (narrowing && cvdDiv)
                return "NARROW+CVD";
            if (adaptiveLowDelta && doji)
                return "Q10+DOJI";
            if (failedOr)
                return "FAILED OR";
            if (doji)
                return "DOJI";
            if (stableVol)
                return "WORKHORSE";
            return "CORE SHORT";
        }

        private string BuildTag(string side, int tier)
        {
            return "DEEP6CompoundSignalsV3_" + side + "_T" + tier.ToString(CultureInfo.InvariantCulture) + "_" + CurrentBar.ToString(CultureInfo.InvariantCulture);
        }

        private Brush GetTierBrush(int tier)
        {
            if (tier == 1)
                return Brushes.LimeGreen;
            if (tier == 2)
                return Brushes.Gold;
            return Brushes.Orange;
        }

        private void UpdateVolumeEma(double volumeNow)
        {
            if (!_volumeEmaSeeded)
            {
                _volumeEma20 = volumeNow;
                _volumeEmaSeeded = true;
            }
            else
            {
                double alpha = 2.0 / 21.0;
                _volumeEma20 = (_volumeEma20 * (1.0 - alpha)) + (volumeNow * alpha);
            }

            PushBounded(_volumeHistory, volumeNow, 40);
        }

        private void ResetSessionState()
        {
            _openingRangeReady = false;
            _openingRangeHigh = 0.0;
            _openingRangeLow = 0.0;
            _sessionOpen = 0.0;
            _sessionCvd = 0;
            _sessionLowPrice = 0.0;
            _sessionLowCvd = 0;
            _sessionHighPrice = 0.0;
            _sessionHighCvd = 0;
            _sessionExtremesSeeded = false;
            _lastSignalBar = -1;
        }

        private void PushBounded(Queue<double> queue, double value, int max)
        {
            queue.Enqueue(value);
            while (queue.Count > max)
                queue.Dequeue();
        }

        private double ComputeStdDevFromQueueTail(Queue<double> queue, int tailCount)
        {
            double[] values = queue.ToArray();
            int start = Math.Max(0, values.Length - tailCount);
            int count = values.Length - start;
            if (count <= 1)
                return 0.0;

            double mean = 0.0;
            int i;
            for (i = start; i < values.Length; i++)
                mean += values[i];
            mean /= count;

            double sumSq = 0.0;
            for (i = start; i < values.Length; i++)
            {
                double diff = values[i] - mean;
                sumSq += diff * diff;
            }

            return Math.Sqrt(sumSq / count);
        }

        private double GetPercentile(Queue<double> queue, double percentile)
        {
            if (queue.Count == 0)
                return 0.0;
            List<double> values = new List<double>(queue);
            values.Sort();
            int index = (int)Math.Round((values.Count - 1) * percentile);
            if (index < 0)
                index = 0;
            if (index >= values.Count)
                index = values.Count - 1;
            return values[index];
        }

        private double GetLastFromQueue(Queue<double> queue)
        {
            double last = 0.0;
            foreach (double value in queue)
                last = value;
            return last;
        }

        private struct SignalDecision
        {
            public bool IsValid;
            public int Direction;
            public int Score;
            public int Tier;
            public string Tag;
            public string Label;
            public double Price;
        }

        [NinjaScriptProperty]
        [Display(Name = "EnableTier1", GroupName = "Parameters", Order = 0)]
        public bool EnableTier1 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableTier2", GroupName = "Parameters", Order = 1)]
        public bool EnableTier2 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableTier3", GroupName = "Parameters", Order = 2)]
        public bool EnableTier3 { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableAlerts", GroupName = "Parameters", Order = 3)]
        public bool EnableAlerts { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowPatternLabels", GroupName = "Parameters", Order = 4)]
        public bool ShowPatternLabels { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ExcludeLunch", GroupName = "Parameters", Order = 5)]
        public bool ExcludeLunch { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "FirstHourOnly", GroupName = "Parameters", Order = 6)]
        public bool FirstHourOnly { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ShowKillerZone", GroupName = "Parameters", Order = 7)]
        public bool ShowKillerZone { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableFailedORTrigger", GroupName = "Parameters", Order = 8)]
        public bool EnableFailedORTrigger { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableCvdDojiTrigger", GroupName = "Parameters", Order = 9)]
        public bool EnableCvdDojiTrigger { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableAdaptiveDojiTrigger", GroupName = "Parameters", Order = 10)]
        public bool EnableAdaptiveDojiTrigger { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "RequireCleanContext", GroupName = "Parameters", Order = 11)]
        public bool RequireCleanContext { get; set; }

        [NinjaScriptProperty]
        [Range(0.05, 0.40)]
        [Display(Name = "ExtremeThreshold", GroupName = "Logic", Order = 12)]
        public double ExtremeThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(0.10, 0.49)]
        [Display(Name = "MiddleRangeLow", GroupName = "Logic", Order = 9)]
        public double MiddleRangeLow { get; set; }

        [NinjaScriptProperty]
        [Range(0.51, 0.90)]
        [Display(Name = "MiddleRangeHigh", GroupName = "Logic", Order = 10)]
        public double MiddleRangeHigh { get; set; }

        [NinjaScriptProperty]
        [Range(1.5, 6.0)]
        [Display(Name = "VolumeSpikeMultiplier", GroupName = "Logic", Order = 11)]
        public double VolumeSpikeMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(0.01, 0.20)]
        [Display(Name = "LowDeltaVolThreshold", GroupName = "Logic", Order = 12)]
        public double LowDeltaVolThreshold { get; set; }

        [NinjaScriptProperty]
        [Range(20, 100)]
        [Display(Name = "DeltaVolQuantileLookback", GroupName = "Logic", Order = 13)]
        public int DeltaVolQuantileLookback { get; set; }

        [NinjaScriptProperty]
        [Range(20, 100)]
        [Display(Name = "StableVolLookback", GroupName = "Logic", Order = 14)]
        public int StableVolLookback { get; set; }

        [NinjaScriptProperty]
        [Range(5, 30)]
        [Display(Name = "VolOfVolLookback", GroupName = "Logic", Order = 15)]
        public int VolOfVolLookback { get; set; }

        [NinjaScriptProperty]
        [Range(0.05, 0.50)]
        [Display(Name = "StableVolPercentile", GroupName = "Logic", Order = 16)]
        public double StableVolPercentile { get; set; }

        [NinjaScriptProperty]
        [Range(1.0, 20.0)]
        [Display(Name = "SmallOvernightMovePoints", GroupName = "Logic", Order = 17)]
        public double SmallOvernightMovePoints { get; set; }

        [NinjaScriptProperty]
        [Range(50, 100)]
        [Display(Name = "ScoreTier1", GroupName = "Scoring", Order = 18)]
        public int ScoreTier1 { get; set; }

        [NinjaScriptProperty]
        [Range(40, 90)]
        [Display(Name = "ScoreTier2", GroupName = "Scoring", Order = 19)]
        public int ScoreTier2 { get; set; }

        [NinjaScriptProperty]
        [Range(30, 80)]
        [Display(Name = "ScoreTier3", GroupName = "Scoring", Order = 20)]
        public int ScoreTier3 { get; set; }

        [NinjaScriptProperty]
        [Range(20, 200)]
        [Display(Name = "StopTicks", GroupName = "Risk", Order = 21)]
        public int StopTicks { get; set; }

        [NinjaScriptProperty]
        [Range(10, 100)]
        [Display(Name = "AbsorptionStopTicks", GroupName = "Risk", Order = 22)]
        public int AbsorptionStopTicks { get; set; }
    }
}

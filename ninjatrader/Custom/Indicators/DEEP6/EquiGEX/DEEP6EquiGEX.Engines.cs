#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public partial class DEEP6EquiGEX
    {
        private const int TrendLeftStrength = 5;
        private const int TrendRightStrength = 2;
        private const int MaxSwingPoints = 5;

        private static readonly TimeZoneInfo _easternTimeZone = TimeZoneInfo.FindSystemTimeZoneById("Eastern Standard Time");

        private readonly List<(int barIndex, double price)> _swingHighs = new List<(int barIndex, double price)>();
        private readonly List<(int barIndex, double price)> _swingLows = new List<(int barIndex, double price)>();
        private readonly Dictionary<int, (double sfv, double premium, double discount)> _sfvHistory =
            new Dictionary<int, (double sfv, double premium, double discount)>();

        private double _avwapAccumPV;
        private double _avwapAccumVol;
        private double _currentAVWAP;
        private DateTime _avwapAnchorTime;
        private bool _avwapValid;
        private TrendDirection _currentTrend = TrendDirection.Neutral;
        private GammaRegime _gammaRegime = GammaRegime.Unknown;
        private int _biasScore;

        private void UpdateAVWAP()
        {
            DateTime barTime = Time[0];
            DateTime weeklyAnchor = GetWeeklyAnchorTime(barTime);

            if (_avwapAnchorTime != weeklyAnchor)
            {
                _avwapAnchorTime = weeklyAnchor;
                _avwapAccumPV = 0;
                _avwapAccumVol = 0;
                _currentAVWAP = 0;
                _avwapValid = false;

                if (ShowDebugValues)
                    Print("[EquiGEX] Weekly AVWAP reset at " + _avwapAnchorTime);
            }

            double volume = Volume[0];
            if (volume > 0)
            {
                double typicalPrice = (High[0] + Low[0] + Close[0]) / 3.0;
                _avwapAccumPV += typicalPrice * volume;
                _avwapAccumVol += volume;

                if (_avwapAccumVol > 0)
                {
                    _currentAVWAP = _avwapAccumPV / _avwapAccumVol;
                    _avwapValid = true;
                }
            }

            if (ShowDebugValues && _avwapValid)
                Print("[EquiGEX] AVWAP=" + _currentAVWAP.ToString("F2") + " Anchor=" + _avwapAnchorTime);
        }

        private void UpdateTrend()
        {
            if (CurrentBar < TrendLeftStrength + TrendRightStrength)
            {
                _currentTrend = TrendDirection.Neutral;
                if (ShowDebugValues)
                    Print("[EquiGEX] Trend=" + _currentTrend + " SwingHi=" + _swingHighs.Count + " SwingLo=" + _swingLows.Count);
                return;
            }

            int pivotBarIndex = CurrentBar - TrendRightStrength;
            if (IsSwingHigh(TrendRightStrength, TrendLeftStrength, TrendRightStrength))
                AddSwingPoint(_swingHighs, pivotBarIndex, High[TrendRightStrength]);

            if (IsSwingLow(TrendRightStrength, TrendLeftStrength, TrendRightStrength))
                AddSwingPoint(_swingLows, pivotBarIndex, Low[TrendRightStrength]);

            _currentTrend = TrendDirection.Neutral;

            if (_swingHighs.Count >= 2 && _swingLows.Count >= 2)
            {
                var previousHigh = _swingHighs[_swingHighs.Count - 2];
                var lastHigh = _swingHighs[_swingHighs.Count - 1];
                var previousLow = _swingLows[_swingLows.Count - 2];
                var lastLow = _swingLows[_swingLows.Count - 1];

                if (lastHigh.price > previousHigh.price && lastLow.price > previousLow.price)
                    _currentTrend = TrendDirection.Bullish;
                else if (lastHigh.price < previousHigh.price && lastLow.price < previousLow.price)
                    _currentTrend = TrendDirection.Bearish;
            }

            if (ShowDebugValues)
                Print("[EquiGEX] Trend=" + _currentTrend + " SwingHi=" + _swingHighs.Count + " SwingLo=" + _swingLows.Count);
        }

        private void UpdateSFVAndZones()
        {
            GexState gexState = GetGexState();
            bool hasGexData = gexState != null && gexState.HasData && gexState.Snapshot != null;
            GexSnapshot snapshot = hasGexData ? gexState.Snapshot : null;

            double weeklyZeroGamma = snapshot != null && snapshot.weekly != null ? snapshot.weekly.zero_gamma : 0;
            double dailyZeroGamma = snapshot != null && snapshot.daily != null ? snapshot.daily.zero_gamma : 0;
            double weeklyNetGex = snapshot != null && snapshot.weekly != null ? snapshot.weekly.net_gex : 0;
            double dailyNetGex = snapshot != null && snapshot.daily != null ? snapshot.daily.net_gex : 0;

            NormalizeWeights();

            double weightedSum = 0;
            double activeWeight = 0;

            if (weeklyZeroGamma != 0)
            {
                weightedSum += weeklyZeroGamma * _wW;
                activeWeight += _wW;
            }

            if (dailyZeroGamma != 0)
            {
                weightedSum += dailyZeroGamma * _wD;
                activeWeight += _wD;
            }

            if (_avwapValid)
            {
                weightedSum += _currentAVWAP * _wA;
                activeWeight += _wA;
            }

            if (activeWeight > 0)
                CurrentSFV = weightedSum / activeWeight;
            else
                CurrentSFV = Close[0];

            double atr = 0;
            if (_atr != null)
            {
                double atrValue = _atr[0];
                if (!double.IsNaN(atrValue) && !double.IsInfinity(atrValue) && atrValue > 0)
                    atr = atrValue;
            }

            double sigma = atr * VolMultiplier;
            CurrentPremiumBand = CurrentSFV + sigma;
            CurrentDiscountBand = CurrentSFV - sigma;

            if (Close[0] > CurrentPremiumBand)
                CurrentZone = ZoneType.Premium;
            else if (Close[0] < CurrentDiscountBand)
                CurrentZone = ZoneType.Discount;
            else
                CurrentZone = ZoneType.Equilibrium;

            double combinedNetGex = weeklyNetGex + dailyNetGex;
            if (combinedNetGex > 0)
                _gammaRegime = GammaRegime.Positive;
            else if (combinedNetGex < 0)
                _gammaRegime = GammaRegime.Negative;
            else
                _gammaRegime = GammaRegime.Unknown;

            _sfvHistory[CurrentBar] = (CurrentSFV, CurrentPremiumBand, CurrentDiscountBand);

            if (ShowDebugValues)
            {
                Print("[EquiGEX] SFV=" + CurrentSFV.ToString("F2")
                    + " Premium=" + CurrentPremiumBand.ToString("F2")
                    + " Discount=" + CurrentDiscountBand.ToString("F2")
                    + " Zone=" + CurrentZone
                    + " ATR=" + atr.ToString("F2"));
            }
        }

        private void UpdateBiasChip()
        {
            int trendScore = 0;
            if (_currentTrend == TrendDirection.Bullish)
                trendScore = 1;
            else if (_currentTrend == TrendDirection.Bearish)
                trendScore = -1;

            int zoneScore = 0;
            if (CurrentZone == ZoneType.Discount)
                zoneScore = 1;
            else if (CurrentZone == ZoneType.Premium)
                zoneScore = -1;

            GexState gexState = GetGexState();
            GexSnapshot snapshot = gexState != null ? gexState.Snapshot : null;
            bool hasGexData = gexState != null && gexState.HasData && snapshot != null;

            int gammaScore = 0;
            int dailyZeroGammaScore = 0;

            if (hasGexData)
            {
                if (_gammaRegime == GammaRegime.Positive)
                    gammaScore = 1;
                else if (_gammaRegime == GammaRegime.Negative)
                    gammaScore = -1;

                double dailyZeroGamma = snapshot.daily != null ? snapshot.daily.zero_gamma : 0;
                if (dailyZeroGamma != 0)
                {
                    if (Close[0] > dailyZeroGamma)
                        dailyZeroGammaScore = 1;
                    else if (Close[0] < dailyZeroGamma)
                        dailyZeroGammaScore = -1;
                }
            }

            _biasScore = trendScore + zoneScore + gammaScore + dailyZeroGammaScore;

            if (_biasScore >= 2)
                CurrentBias = BiasDirection.Bullish;
            else if (_biasScore <= -2)
                CurrentBias = BiasDirection.Bearish;
            else
                CurrentBias = BiasDirection.Neutral;

            if (ShowDebugValues)
            {
                Print("[EquiGEX] Bias=" + CurrentBias
                    + " Score=" + _biasScore
                    + " [T:" + trendScore
                    + " Z:" + zoneScore
                    + " G:" + gammaScore
                    + " D:" + dailyZeroGammaScore + "]");
            }
        }

        private void NormalizeWeights()
        {
            double total = WeightWeekly + WeightDaily + WeightAVWAP;
            if (total > 0)
            {
                _wW = WeightWeekly / total;
                _wD = WeightDaily / total;
                _wA = WeightAVWAP / total;
            }
            else
            {
                _wW = 1.0 / 3.0;
                _wD = 1.0 / 3.0;
                _wA = 1.0 / 3.0;
            }
        }

        private DateTime GetWeeklyAnchorTime(DateTime barTime)
        {
            DateTime easternTime = TimeZoneInfo.ConvertTime(barTime, _easternTimeZone);
            int daysSinceSunday = (int)easternTime.DayOfWeek;
            DateTime anchorTime = easternTime.Date.AddDays(-daysSinceSunday).AddHours(18);

            if (easternTime < anchorTime)
                anchorTime = anchorTime.AddDays(-7);

            return anchorTime;
        }

        private void AddSwingPoint(List<(int barIndex, double price)> swings, int barIndex, double price)
        {
            if (swings.Count > 0 && swings[swings.Count - 1].barIndex == barIndex)
            {
                swings[swings.Count - 1] = (barIndex, price);
                return;
            }

            swings.Add((barIndex, price));
            if (swings.Count > MaxSwingPoints)
                swings.RemoveAt(0);
        }

        private bool IsSwingHigh(int barsAgo, int leftStrength, int rightStrength)
        {
            double candidate = High[barsAgo];

            for (int i = 1; i <= leftStrength; i++)
            {
                if (candidate < High[barsAgo + i])
                    return false;
            }

            for (int i = 1; i <= rightStrength; i++)
            {
                if (candidate < High[barsAgo - i])
                    return false;
            }

            return true;
        }

        private bool IsSwingLow(int barsAgo, int leftStrength, int rightStrength)
        {
            double candidate = Low[barsAgo];

            for (int i = 1; i <= leftStrength; i++)
            {
                if (candidate > Low[barsAgo + i])
                    return false;
            }

            for (int i = 1; i <= rightStrength; i++)
            {
                if (candidate > Low[barsAgo - i])
                    return false;
            }

            return true;
        }
    }
}

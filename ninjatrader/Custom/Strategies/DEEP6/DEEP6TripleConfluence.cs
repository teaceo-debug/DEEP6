// DEEP6 Triple Confluence Strategy
//
// Self-contained Strategy Analyzer-ready strategy that combines:
//   - Daily low-timeframe LVN context from 1-minute bars
//   - Volumetric-bar absorption
//   - Session CVD divergence built from BarDelta
//
// Signal rule:
//   Long  = price near LVN + bullish absorption + bullish CVD divergence
//   Short = price near LVN + bearish absorption + bearish CVD divergence
//
// Visuals:
//   - Green up arrow for bullish confluence
//   - Red down arrow for bearish confluence

#region Using
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.DrawingTools;
using NinjaTrader.NinjaScript.Indicators;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class DEEP6TripleConfluence : Strategy
    {
        private const string LogPrefix = "[DEEP6TripleConfluence]";

        private struct BarHLV
        {
            public double H;
            public double L;
            public double V;
        }

        private readonly List<BarHLV> _periodBars = new List<BarHLV>();
        private readonly List<double> _lvnPrices = new List<double>();
        private readonly Dictionary<int, long> _cvdByPrimaryBar = new Dictionary<int, long>();
        private readonly Dictionary<int, double> _priceByPrimaryBar = new Dictionary<int, double>();
        private readonly Dictionary<int, double> _lowByPrimaryBar = new Dictionary<int, double>();
        private readonly Dictionary<int, double> _highByPrimaryBar = new Dictionary<int, double>();
        private readonly HashSet<string> _countedEntryOrderIds = new HashSet<string>();

        private double[] _vpValues;
        private double[] _vpYVol;

        private int _vpDayKey = -1;
        private int _flowDayKey = -1;
        private DateTime _tradeSessionDate = DateTime.MinValue;

        private int _lastVpPrimaryBar = -1;
        private int _lastVolPrimaryBar = -1;

        private int _tradesThisSession;
        private int _lastEntryBar = -1000;
        private double _sessionStartCumProfit;
        private bool _killSwitch;

        private long _sessionCvd;
        private long _cachedBarDelta;
        private long _cachedSessionCvd;
        private double _cachedVolClose;
        private double _cachedVolLow;
        private double _cachedVolHigh;
        private double _cachedAvgCellVol;
        private double _cachedAbsThreshold;

        private bool _cachedBullishAbsorption;
        private bool _cachedBearishAbsorption;
        private double _cachedBullishAbsorptionPrice;
        private double _cachedBearishAbsorptionPrice;
        private double _cachedBullishCombinedVol;
        private double _cachedBearishCombinedVol;

        private string _activeEntrySignal;
        private int _activeDirection;
        private double _entryPrice;
        private double _activeStopPrice;
        private bool _breakevenMoved;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Triple Confluence — daily LVN + absorption + CVD divergence strategy.";
                Name = "DEEP6 Triple Confluence";
                Calculate = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds = 30;
                IsFillLimitOnTouch = false;
                MaximumBarsLookBack = MaximumBarsLookBack.TwoHundredFiftySix;
                OrderFillResolution = OrderFillResolution.Standard;
                Slippage = 0;
                StartBehavior = StartBehavior.WaitUntilFlat;
                TimeInForce = TimeInForce.Day;
                TraceOrders = false;
                RealtimeErrorHandling = RealtimeErrorHandling.StopCancelClose;
                StopTargetHandling = StopTargetHandling.PerEntryExecution;
                BarsRequiredToTrade = 30;
                IsInstantiatedOnEachOptimizationIteration = false;

                VpRows = 200;
                LvnStrength = 5;
                LvnProximityTicks = 8;

                VolumetricPeriod = 5;
                AbsorptionMultiplier = 2.0;
                CvdDivLookback = 10;

                StopLossTicks = 20;
                TargetTicks = 40;
                MaxContracts = 1;
                MaxTradesPerSession = 5;
                MinBarsBetweenEntries = 3;
                DailyLossCapDollars = 500.0;
                BlackoutStart = 1530;
                BlackoutEnd = 1600;

                BreakevenEnabled = true;
                BreakevenActivationTicks = 12;
                BreakevenOffsetTicks = 2;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 1);
                AddVolumetric(Instrument.FullName, BarsPeriodType.Minute, VolumetricPeriod, VolumetricDeltaType.BidAsk, 1);
            }
            else if (State == State.DataLoaded)
            {
                int rows = Math.Max(10, VpRows);
                _vpValues = new double[rows + 1];
                _vpYVol = new double[rows + 1];

                ResetTradeState();
                ResetVpSession();
                ResetFlowSession();

                _tradeSessionDate = DateTime.MinValue;
                _tradesThisSession = 0;
                _lastEntryBar = -1000;
                _sessionStartCumProfit = 0.0;
                _killSwitch = false;
            }
            else if (State == State.Terminated)
            {
                _periodBars.Clear();
                _lvnPrices.Clear();
                _cvdByPrimaryBar.Clear();
                _priceByPrimaryBar.Clear();
                _lowByPrimaryBar.Clear();
                _highByPrimaryBar.Clear();
                _countedEntryOrderIds.Clear();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                ProcessVpBar();
                return;
            }

            if (BarsInProgress == 2)
            {
                ProcessVolumetricBar();
                return;
            }

            if (BarsInProgress != 0)
                return;

            if (CurrentBar < BarsRequiredToTrade)
                return;

            if (CurrentBars.Length < 3 || CurrentBars[1] < 0 || CurrentBars[2] < 0)
                return;

            HandleTradeSessionReset();
            UpdateSessionRiskLock();

            if (Position.MarketPosition != MarketPosition.Flat)
            {
                ManageOpenPosition();
                return;
            }

            ResetTradeState();

            int barTime = Time[0].Hour * 100 + Time[0].Minute;
            if (IsBlackoutTime(barTime))
                return;

            if (_killSwitch)
                return;

            if (_tradesThisSession >= MaxTradesPerSession)
                return;

            if (CurrentBar - _lastEntryBar < MinBarsBetweenEntries)
                return;

            if (!HasSynchronizedSecondaryData())
                return;

            RebuildProfile();
            if (_lvnPrices.Count == 0)
                return;

            double nearestLvn;
            double lvnDistanceTicks;
            if (!TryGetNearestLvn(Close[0], out nearestLvn, out lvnDistanceTicks))
                return;

            if (lvnDistanceTicks > LvnProximityTicks)
                return;

            if (CurrentBar < CvdDivLookback + 1)
                return;

            double priorPriceLow;
            long priorCvdLow;
            bool bullishDiv = HasBullishCvdDivergence(CurrentBar, out priorPriceLow, out priorCvdLow);

            double priorPriceHigh;
            long priorCvdHigh;
            bool bearishDiv = HasBearishCvdDivergence(CurrentBar, out priorPriceHigh, out priorCvdHigh);

            bool bullishSignal = _cachedBullishAbsorption && bullishDiv;
            bool bearishSignal = _cachedBearishAbsorption && bearishDiv;

            if (bullishSignal == bearishSignal)
                return;

            int direction = bullishSignal ? 1 : -1;
            string signalName = direction > 0 ? "TripleConfluenceLong" : "TripleConfluenceShort";

            SetStopLoss(CalculationMode.Ticks, StopLossTicks);
            SetProfitTarget(CalculationMode.Ticks, TargetTicks);

            if (direction > 0)
            {
                Draw.ArrowUp(this, "TCLong_" + CurrentBar, true, 0, Low[0] - 4 * TickSize, Brushes.Lime);
                EnterLong(MaxContracts, signalName);
            }
            else
            {
                Draw.ArrowDown(this, "TCShort_" + CurrentBar, true, 0, High[0] + 4 * TickSize, Brushes.Red);
                EnterShort(MaxContracts, signalName);
            }

            double absorptionPrice = direction > 0 ? _cachedBullishAbsorptionPrice : _cachedBearishAbsorptionPrice;
            double absorptionVol = direction > 0 ? _cachedBullishCombinedVol : _cachedBearishCombinedVol;
            double priorPriceRef = direction > 0 ? priorPriceLow : priorPriceHigh;
            long priorCvdRef = direction > 0 ? priorCvdLow : priorCvdHigh;

            Print(string.Format(
                "{0} SIGNAL {1} close={2:F2} lvn={3:F2} dist={4:F1}t absPrice={5:F2} absCell={6:F0} avgCell={7:F2} absThreshold={8:F2} barDelta={9} sessionCvd={10} priorPrice={11:F2} priorCvd={12}",
                LogPrefix,
                direction > 0 ? "LONG" : "SHORT",
                Close[0],
                nearestLvn,
                lvnDistanceTicks,
                absorptionPrice,
                absorptionVol,
                _cachedAvgCellVol,
                _cachedAbsThreshold,
                _cachedBarDelta,
                _cachedSessionCvd,
                priorPriceRef,
                priorCvdRef));
        }

        private void ProcessVpBar()
        {
            if (CurrentBars[1] < 0)
                return;

            DateTime barTime = Time[0];
            int dayKey = barTime.Year * 1000 + barTime.DayOfYear;
            if (_vpDayKey != -1 && dayKey != _vpDayKey)
                ResetVpSession();

            _vpDayKey = dayKey;
            _periodBars.Add(new BarHLV { H = High[0], L = Low[0], V = Volume[0] });

            int primaryBar = GetPrimaryBarIndex(barTime);
            if (primaryBar >= 0)
                _lastVpPrimaryBar = primaryBar;
        }

        private void ProcessVolumetricBar()
        {
            NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType volBars =
                BarsArray[2].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            if (volBars == null || volBars.Volumes == null)
                return;

            if (CurrentBars[2] < 0 || CurrentBars[2] >= volBars.Volumes.Length)
                return;

            DateTime barTime = Times[2][0];
            int dayKey = barTime.Year * 1000 + barTime.DayOfYear;
            if (_flowDayKey != -1 && dayKey != _flowDayKey)
                ResetFlowSession();
            _flowDayKey = dayKey;

            var volumeBar = volBars.Volumes[CurrentBars[2]];
            if (volumeBar == null)
                return;

            long barDelta = volumeBar.BarDelta;
            _sessionCvd += barDelta;

            double barLow = Lows[2][0];
            double barHigh = Highs[2][0];
            double barClose = Closes[2][0];
            if (barHigh < barLow)
                return;

            double totalCellVol = 0.0;
            int cellCount = 0;

            for (double price = RoundToTick(barLow); price <= barHigh + TickSize * 0.5; price += TickSize)
            {
                double rp = RoundToTick(price);
                long ask = volumeBar.GetAskVolumeForPrice(rp);
                long bid = volumeBar.GetBidVolumeForPrice(rp);
                totalCellVol += ask + bid;
                cellCount++;
            }

            double avgCellVol = cellCount > 0 ? totalCellVol / cellCount : 0.0;
            double absThreshold = avgCellVol * AbsorptionMultiplier;
            double barRange = barHigh - barLow;
            double barMid = barLow + barRange * 0.5;
            double lowerZoneHigh = barLow + Math.Max(TickSize, barRange * 0.35);
            double upperZoneLow = barHigh - Math.Max(TickSize, barRange * 0.35);

            bool bullishAbsorption = false;
            bool bearishAbsorption = false;
            double bullishPrice = 0.0;
            double bearishPrice = 0.0;
            double bullishCombinedVol = 0.0;
            double bearishCombinedVol = 0.0;

            if (absThreshold > 0.0)
            {
                bool closesUpperHalf = barClose >= barMid;
                bool closesLowerHalf = barClose <= barMid;

                for (double price = RoundToTick(barLow); price <= barHigh + TickSize * 0.5; price += TickSize)
                {
                    double rp = RoundToTick(price);
                    long ask = volumeBar.GetAskVolumeForPrice(rp);
                    long bid = volumeBar.GetBidVolumeForPrice(rp);
                    double total = ask + bid;

                    if (ask < absThreshold || bid < absThreshold)
                        continue;

                    if (closesUpperHalf && rp <= lowerZoneHigh && total > bullishCombinedVol)
                    {
                        bullishAbsorption = true;
                        bullishPrice = rp;
                        bullishCombinedVol = total;
                    }

                    if (closesLowerHalf && rp >= upperZoneLow && total > bearishCombinedVol)
                    {
                        bearishAbsorption = true;
                        bearishPrice = rp;
                        bearishCombinedVol = total;
                    }
                }
            }

            int primaryBar = GetPrimaryBarIndex(barTime);
            if (primaryBar < 0)
                return;

            _cachedBarDelta = barDelta;
            _cachedSessionCvd = _sessionCvd;
            _cachedVolClose = barClose;
            _cachedVolLow = barLow;
            _cachedVolHigh = barHigh;
            _cachedAvgCellVol = avgCellVol;
            _cachedAbsThreshold = absThreshold;
            _cachedBullishAbsorption = bullishAbsorption;
            _cachedBearishAbsorption = bearishAbsorption;
            _cachedBullishAbsorptionPrice = bullishPrice;
            _cachedBearishAbsorptionPrice = bearishPrice;
            _cachedBullishCombinedVol = bullishCombinedVol;
            _cachedBearishCombinedVol = bearishCombinedVol;

            _cvdByPrimaryBar[primaryBar] = _sessionCvd;
            _priceByPrimaryBar[primaryBar] = barClose;
            _lowByPrimaryBar[primaryBar] = barLow;
            _highByPrimaryBar[primaryBar] = barHigh;
            _lastVolPrimaryBar = primaryBar;
        }

        private bool HasSynchronizedSecondaryData()
        {
            if (_periodBars.Count == 0)
                return false;

            if (_lastVpPrimaryBar != CurrentBar)
                return false;

            if (_lastVolPrimaryBar != CurrentBar)
                return false;

            return true;
        }

        private void RebuildProfile()
        {
            _lvnPrices.Clear();
            if (_periodBars.Count == 0)
                return;

            int rows = Math.Max(10, VpRows);
            EnsureProfileArrays(rows + 1);

            double yMax = double.MinValue;
            double yMin = double.MaxValue;
            foreach (BarHLV b in _periodBars)
            {
                if (b.H > yMax) yMax = b.H;
                if (b.L < yMin) yMin = b.L;
            }

            if (yMax <= yMin)
                return;

            double step = (yMax - yMin) / rows;
            if (step < TickSize) step = TickSize;

            for (int i = 0; i <= rows; i++)
                _vpYVol[i] = yMin + i * (yMax - yMin) / rows;

            Array.Clear(_vpValues, 0, _vpValues.Length);

            foreach (BarHLV b in _periodBars)
            {
                if (b.V <= 0)
                    continue;

                int r1 = (int)Math.Floor((b.L - yMin) / step);
                int r2 = (int)Math.Floor((b.H - yMin) / step);
                r1 = Math.Max(0, Math.Min(r1, rows));
                r2 = Math.Max(0, Math.Min(r2, rows));

                double addV = (r2 - r1 + 1) > 0 ? b.V / (r2 - r1 + 1) : 0;
                for (int r = r1; r <= r2; r++)
                    _vpValues[r] += addV;
            }

            int size = rows + 1;
            if (size <= LvnStrength * 2 + 1)
                return;

            var seen = new HashSet<double>();
            for (int i = 0; i < size; i++)
            {
                if (_vpValues[i] <= 0)
                    continue;

                bool isLvn = true;
                for (int j = -LvnStrength; j <= LvnStrength; j++)
                {
                    if (j == 0)
                        continue;

                    int k = i + j;
                    if (k < 0 || k >= size)
                        continue;

                    if (_vpValues[k] <= 0)
                        continue;

                    if (_vpValues[k] < _vpValues[i])
                    {
                        isLvn = false;
                        break;
                    }
                }

                if (isLvn)
                {
                    double price = RoundToTick(_vpYVol[i]);
                    if (seen.Add(price))
                        _lvnPrices.Add(price);
                }
            }
        }

        private void EnsureProfileArrays(int size)
        {
            if (_vpValues == null || _vpValues.Length != size)
                _vpValues = new double[size];

            if (_vpYVol == null || _vpYVol.Length != size)
                _vpYVol = new double[size];
        }

        private bool TryGetNearestLvn(double price, out double nearestPrice, out double distanceTicks)
        {
            nearestPrice = 0.0;
            distanceTicks = double.MaxValue;

            if (_lvnPrices.Count == 0)
                return false;

            foreach (double level in _lvnPrices)
            {
                double distance = Math.Abs(price - level) / TickSize;
                if (distance < distanceTicks)
                {
                    distanceTicks = distance;
                    nearestPrice = level;
                }
            }

            return distanceTicks < double.MaxValue;
        }

        private bool HasBullishCvdDivergence(int primaryBar, out double priorPriceLow, out long priorCvdLow)
        {
            priorPriceLow = double.MaxValue;
            priorCvdLow = long.MaxValue;

            if (!_lowByPrimaryBar.ContainsKey(primaryBar) || !_cvdByPrimaryBar.ContainsKey(primaryBar))
                return false;

            bool hasHistory = false;
            for (int i = 1; i <= CvdDivLookback; i++)
            {
                int index = primaryBar - i;
                long cvd;
                double priceLow;
                if (!_cvdByPrimaryBar.TryGetValue(index, out cvd) || !_lowByPrimaryBar.TryGetValue(index, out priceLow))
                    continue;

                hasHistory = true;
                if (priceLow < priorPriceLow) priorPriceLow = priceLow;
                if (cvd < priorCvdLow) priorCvdLow = cvd;
            }

            if (!hasHistory)
                return false;

            return _lowByPrimaryBar[primaryBar] < priorPriceLow && _cvdByPrimaryBar[primaryBar] > priorCvdLow;
        }

        private bool HasBearishCvdDivergence(int primaryBar, out double priorPriceHigh, out long priorCvdHigh)
        {
            priorPriceHigh = double.MinValue;
            priorCvdHigh = long.MinValue;

            if (!_highByPrimaryBar.ContainsKey(primaryBar) || !_cvdByPrimaryBar.ContainsKey(primaryBar))
                return false;

            bool hasHistory = false;
            for (int i = 1; i <= CvdDivLookback; i++)
            {
                int index = primaryBar - i;
                long cvd;
                double priceHigh;
                if (!_cvdByPrimaryBar.TryGetValue(index, out cvd) || !_highByPrimaryBar.TryGetValue(index, out priceHigh))
                    continue;

                hasHistory = true;
                if (priceHigh > priorPriceHigh) priorPriceHigh = priceHigh;
                if (cvd > priorCvdHigh) priorCvdHigh = cvd;
            }

            if (!hasHistory)
                return false;

            return _highByPrimaryBar[primaryBar] > priorPriceHigh && _cvdByPrimaryBar[primaryBar] < priorCvdHigh;
        }

        private void ManageOpenPosition()
        {
            if (!BreakevenEnabled || _breakevenMoved || string.IsNullOrWhiteSpace(_activeEntrySignal))
                return;

            double mfeTicks = Position.MarketPosition == MarketPosition.Long
                ? (Close[0] - _entryPrice) / TickSize
                : (_entryPrice - Close[0]) / TickSize;

            if (mfeTicks < BreakevenActivationTicks)
                return;

            _activeStopPrice = Position.MarketPosition == MarketPosition.Long
                ? _entryPrice + BreakevenOffsetTicks * TickSize
                : _entryPrice - BreakevenOffsetTicks * TickSize;

            SetStopLoss(_activeEntrySignal, CalculationMode.Price, _activeStopPrice, false);
            _breakevenMoved = true;

            Print(string.Format(
                "{0} BREAKEVEN {1} entry={2:F2} newStop={3:F2} mfeTicks={4:F1}",
                LogPrefix,
                Position.MarketPosition,
                _entryPrice,
                _activeStopPrice,
                mfeTicks));
        }

        protected override void OnPositionUpdate(Position position, double averagePrice, int quantity, MarketPosition marketPosition)
        {
            if (marketPosition == MarketPosition.Flat && quantity == 0)
                ResetTradeState();
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
            MarketPosition marketPosition, string orderId, DateTime time)
        {
            if (execution == null || execution.Order == null)
                return;

            string orderName = execution.Order.Name ?? string.Empty;
            if (orderName != "TripleConfluenceLong" && orderName != "TripleConfluenceShort")
                return;

            string entryKey = string.IsNullOrWhiteSpace(orderId)
                ? orderName + "_" + time.Ticks.ToString()
                : orderId;

            if (!_countedEntryOrderIds.Add(entryKey))
                return;

            _tradesThisSession++;
            _lastEntryBar = CurrentBar;
            _activeEntrySignal = orderName;
            _activeDirection = orderName == "TripleConfluenceLong" ? 1 : -1;
            _entryPrice = price;
            _activeStopPrice = _activeDirection > 0
                ? _entryPrice - StopLossTicks * TickSize
                : _entryPrice + StopLossTicks * TickSize;
            _breakevenMoved = false;

            Print(string.Format(
                "{0} ENTRY {1} price={2:F2} qty={3} sessionTrades={4}/{5} orderId={6}",
                LogPrefix,
                orderName,
                price,
                quantity,
                _tradesThisSession,
                MaxTradesPerSession,
                entryKey));
        }

        private void HandleTradeSessionReset()
        {
            if (Time[0].Date == _tradeSessionDate)
                return;

            _tradeSessionDate = Time[0].Date;
            _tradesThisSession = 0;
            _killSwitch = false;
            _lastEntryBar = -1000;
            _sessionStartCumProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
            _countedEntryOrderIds.Clear();
            ResetTradeState();

            Print(string.Format("{0} Session reset {1:yyyy-MM-dd}.", LogPrefix, _tradeSessionDate));
        }

        private void UpdateSessionRiskLock()
        {
            double sessionCumProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - _sessionStartCumProfit;
            if (sessionCumProfit <= -Math.Abs(DailyLossCapDollars))
                _killSwitch = true;
        }

        private bool IsBlackoutTime(int hhmm)
        {
            if (BlackoutStart == BlackoutEnd)
                return false;

            if (BlackoutStart < BlackoutEnd)
                return hhmm >= BlackoutStart && hhmm <= BlackoutEnd;

            return hhmm >= BlackoutStart || hhmm <= BlackoutEnd;
        }

        private int GetPrimaryBarIndex(DateTime seriesTime)
        {
            if (BarsArray == null || BarsArray.Length == 0 || BarsArray[0] == null)
                return -1;

            return BarsArray[0].GetBar(seriesTime);
        }

        private void ResetVpSession()
        {
            _periodBars.Clear();
            _lvnPrices.Clear();
            _lastVpPrimaryBar = -1;

            if (_vpValues != null)
                Array.Clear(_vpValues, 0, _vpValues.Length);

            if (_vpYVol != null)
                Array.Clear(_vpYVol, 0, _vpYVol.Length);
        }

        private void ResetFlowSession()
        {
            _sessionCvd = 0;
            _cachedBarDelta = 0;
            _cachedSessionCvd = 0;
            _cachedVolClose = 0.0;
            _cachedVolLow = 0.0;
            _cachedVolHigh = 0.0;
            _cachedAvgCellVol = 0.0;
            _cachedAbsThreshold = 0.0;
            _cachedBullishAbsorption = false;
            _cachedBearishAbsorption = false;
            _cachedBullishAbsorptionPrice = 0.0;
            _cachedBearishAbsorptionPrice = 0.0;
            _cachedBullishCombinedVol = 0.0;
            _cachedBearishCombinedVol = 0.0;
            _lastVolPrimaryBar = -1;

            _cvdByPrimaryBar.Clear();
            _priceByPrimaryBar.Clear();
            _lowByPrimaryBar.Clear();
            _highByPrimaryBar.Clear();
        }

        private void ResetTradeState()
        {
            _activeEntrySignal = null;
            _activeDirection = 0;
            _entryPrice = 0.0;
            _activeStopPrice = 0.0;
            _breakevenMoved = false;
        }

        private double RoundToTick(double price)
        {
            if (TickSize <= 0)
                return price;

            return Math.Round(price / TickSize) * TickSize;
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "VpRows", Order = 0, GroupName = "Volume Profile")]
        public int VpRows { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "LvnStrength", Order = 1, GroupName = "Volume Profile")]
        public int LvnStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "LvnProximityTicks", Order = 2, GroupName = "Volume Profile")]
        public int LvnProximityTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "VolumetricPeriod", Order = 0, GroupName = "Order Flow")]
        public int VolumetricPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 20.0)]
        [Display(Name = "AbsorptionMultiplier", Order = 1, GroupName = "Order Flow")]
        public double AbsorptionMultiplier { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "CvdDivLookback", Order = 2, GroupName = "Order Flow")]
        public int CvdDivLookback { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "StopLossTicks", Order = 0, GroupName = "Trade Management")]
        public int StopLossTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 400)]
        [Display(Name = "TargetTicks", Order = 1, GroupName = "Trade Management")]
        public int TargetTicks { get; set; }

        [NinjaScriptProperty]
        [Range(1, 20)]
        [Display(Name = "MaxContracts", Order = 2, GroupName = "Trade Management")]
        public int MaxContracts { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "MaxTradesPerSession", Order = 3, GroupName = "Trade Management")]
        public int MaxTradesPerSession { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "MinBarsBetweenEntries", Order = 4, GroupName = "Trade Management")]
        public int MinBarsBetweenEntries { get; set; }

        [NinjaScriptProperty]
        [Range(0.0, double.MaxValue)]
        [Display(Name = "DailyLossCapDollars", Order = 5, GroupName = "Trade Management")]
        public double DailyLossCapDollars { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "BlackoutStart", Order = 6, GroupName = "Trade Management")]
        public int BlackoutStart { get; set; }

        [NinjaScriptProperty]
        [Range(0, 2359)]
        [Display(Name = "BlackoutEnd", Order = 7, GroupName = "Trade Management")]
        public int BlackoutEnd { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BreakevenEnabled", Order = 0, GroupName = "Breakeven")]
        public bool BreakevenEnabled { get; set; }

        [NinjaScriptProperty]
        [Range(1, 200)]
        [Display(Name = "BreakevenActivationTicks", Order = 1, GroupName = "Breakeven")]
        public int BreakevenActivationTicks { get; set; }

        [NinjaScriptProperty]
        [Range(0, 50)]
        [Display(Name = "BreakevenOffsetTicks", Order = 2, GroupName = "Breakeven")]
        public int BreakevenOffsetTicks { get; set; }

        #endregion
    }
}

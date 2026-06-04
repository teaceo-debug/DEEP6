// DEEP6 LVN×Radar Strategy
//
// Self-contained LVN cross strategy:
//   - Builds Daily / Weekly / Monthly LVN profiles internally from 1-minute bars.
//   - Triggers on price crossing active LVN levels.
//   - Uses Depth Radar genuine walls as optional adaptive T2 targets.
//   - Preserves ChartTrader WPF controls, risk gates, managed exits, and debug logging.

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
using NinjaTrader.NinjaScript.Indicators.DEEP6;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Strategies
{
    public class DEEP6LVNRadarStrategy : Strategy
    {
        private const string LogPrefix = "[DEEP6LVNRadarStrategy]";
        private static readonly string DebugLogPath = System.IO.Path.Combine(
            System.Environment.GetFolderPath(System.Environment.SpecialFolder.MyDocuments),
            "NinjaTrader 8", "DEEP6_AutoTrader_Logs", "LVNRadar_debug.log");

        private struct BarHLV
        {
            public double H;
            public double L;
            public double V;
        }

        private sealed class LvnCandidate
        {
            public double Price;
            public int Direction;
            public double DistanceTicks;
            public string Source;
        }

        private sealed class ProfileState
        {
            public VPProfilePeriod Period;
            public string Prefix;
            public List<BarHLV> Bars;
            public double[] VpValues;
            public double[] VpYVol;
            public List<double> LvnPrices;
            public List<string> DrawTags;
            public int LastPeriodKey;
        }

        private DEEP6DepthRadarV2 _depthRadar;
        private ATR _atr;
        private ProfileState _dailyProfile;
        private ProfileState _weeklyProfile;
        private ProfileState _monthlyProfile;

        private readonly List<double> _activeLvnPrices = new List<double>();
        private DateTime _sessionDate = DateTime.MinValue;
        private int _tradesThisSession;
        private int _lastEntryBar = -1000;
        private double _sessionStartCumProfit;
        private double _sessionAtrSum;
        private int _sessionAtrCount;
        private bool _killSwitch;

        private string _activeEntrySignal;
        private string _activeT1Signal;
        private string _activeT2Signal;
        private int _activeDirection;
        private int _entryBar = -1;
        private double _entryPrice;
        private double _stopPrice;
        private double _target1Price;
        private double _target2Price;
        private bool _breakevenMoved;

        private bool _showDailyLvn;
        private bool _showWeeklyLvn;
        private bool _showMonthlyLvn;
        private bool _radarTargetsEnabled;
        private bool _autoExecutionEnabled;
        private bool _allowLongEntries;
        private bool _allowShortEntries;

        private NinjaTrader.Gui.Chart.Chart _chartWindow;
        private ChartTab _chartTab;
        private ChartTrader _chartTraderControl;
        private Grid _chartGrid;
        private Grid _chartTraderGrid;
        private RowDefinition _chartTraderPanelRow;
        private Border _chartTraderPanelBorder;
        private ScrollViewer _chartTraderPanelScrollViewer;
        private bool _panelAttached;
        private bool _tabSelectionWired;

        private TextBlock _connectionStatusText;
        private TextBlock _marketStateText;
        private TextBlock _lvnStatusText;
        private TextBlock _atmSelectorText;
        private TextBlock _sessionPnLValueText;
        private TextBlock _tradesTodayValueText;
        private TextBlock _nearestLvnValueText;
        private TextBlock _nearestWallValueText;
        private TextBlock _autoExecuteText;
        private TextBlock _dryRunText;

        private Button _longToggleButton;
        private Button _shortToggleButton;
        private Button _breakevenButton;
        private Button _closeButton;
        private Button _lvnDailyButton;
        private Button _lvnWeeklyButton;
        private Button _lvnMonthlyButton;
        private Button _volumeFilterButton;
        private Button _radarTargetsButton;
        private Button _autoExecuteButton;
        private Button _dryRunButton;

        private TextBox _approachTicksTextBox;
        private TextBox _volumeFilterRatioTextBox;

        private bool _pendingBreakevenRequest;
        private bool _pendingCloseRequest;
        private string _lastNearestLvnDisplay = "—";
        private string _lastNearestWallDisplay = "—";
        private string _lastLvnStatusDisplay = "LVNs: 0 | nearest —";

        private void LogDebug(string msg)
        {
            try
            {
                string line = string.Format("{0:yyyy-MM-dd HH:mm:ss.fff} {1}\r\n", DateTime.Now, msg);
                System.IO.File.AppendAllText(DebugLogPath, line);
            }
            catch { }
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 LVN×Radar strategy — self-contained LVN cross engine + Depth Radar adaptive T2.";
                Name = "DEEP6 LVN Radar Strategy";
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
                BarsRequiredToTrade = 20;
                IsInstantiatedOnEachOptimizationIteration = false;

                LvnApproachTicks = 4;
                VolumeFilterEnabled = true;
                VolumeFilterRatio = 0.8;

                DefaultLvnPeriod = VPProfilePeriod.Monthly;
                LvnRows = 200;
                LvnStrength = 15;
                LvnResolutionMinutes = 1;

                StopLossTicks = 20;
                ScaleOutEnabled = true;
                ScaleOutTargetTicks = 16;
                TargetTicks = 32;
                BreakevenEnabled = true;
                BreakevenActivationTicks = 10;
                BreakevenOffsetTicks = 2;
                MaxBarsInTrade = 60;
                UseRadarTargets = true;

                MaxContractsPerTrade = 2;
                MaxTradesPerSession = 5;
                DailyLossCapDollars = 500.0;
                MinBarsBetweenEntries = 3;
                BlackoutWindowStart = 1530;
                BlackoutWindowEnd = 1600;

                EnableAutoExecution = false;
                DryRunMode = true;
            }
            else if (State == State.Configure)
            {
                AddDataSeries(BarsPeriodType.Minute, 1);
            }
            else if (State == State.DataLoaded)
            {
                _atr = ATR(20);
                _depthRadar = new DEEP6DepthRadarV2
                {
                    WallMinSize = 50,
                    WallStaleSec = 90,
                    MaxDepthLevels = 40,
                    GlowThreshold = 100,
                    StaleCrossTimeoutSec = 30,
                    ShowBids = false,
                    ShowAsks = false,
                    ShowLabels = false,
                    EnableML = true,
                };

                _dailyProfile = CreateProfileState(VPProfilePeriod.Daily, "D");
                _weeklyProfile = CreateProfileState(VPProfilePeriod.Weekly, "W");
                _monthlyProfile = CreateProfileState(VPProfilePeriod.Monthly, "M");

                AddChartIndicator(_depthRadar);

                _showDailyLvn = DefaultLvnPeriod == VPProfilePeriod.Daily;
                _showWeeklyLvn = DefaultLvnPeriod == VPProfilePeriod.Weekly;
                _showMonthlyLvn = DefaultLvnPeriod == VPProfilePeriod.Monthly;
                _radarTargetsEnabled = UseRadarTargets;
                _autoExecutionEnabled = true;
                _allowLongEntries = true;
                _allowShortEntries = true;

                ResetTradeState();
            }
            else if (State == State.Historical)
            {
                DispatchToUi(CreateOrAttachWpfPanel);
            }
            else if (State == State.Terminated)
            {
                DispatchToUi(RemoveWpfPanel);
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1)
            {
                CollectLtfBar();
                return;
            }

            if (BarsInProgress != 0)
                return;
            if (CurrentBar < BarsRequiredToTrade || CurrentBar < 20)
                return;
            if (CurrentBars.Length > 1 && CurrentBars[1] < 1)
                return;

            HandleSessionReset();
            UpdateSessionAtr();
            UpdateSessionRiskLock();
            ProcessPendingPanelActions();

            RebuildAllProfiles();
            UpdateActiveLvnPrices();
            RefreshAllLvnDrawings();
            UpdatePanelCaches();
            SchedulePanelUpdate();

            if (CurrentBar % 100 == 0)
                LogDebug(string.Format("HEARTBEAT bar={0} time={1} close={2:F2} pos={3}", CurrentBar, Time[0], Close[0], Position.MarketPosition));

            if (Position.MarketPosition != MarketPosition.Flat)
            {
                ManageOpenTrade();
                return;
            }

            ResetTradeState();

            int barTime = Time[0].Hour * 100 + Time[0].Minute;
            if (IsBlackoutTime(barTime))
            {
                LogDebug(string.Format("BLOCKED blackout window {0} at {1}", barTime, Time[0]));
                return;
            }
            if (_killSwitch)
            {
                Print(string.Format("{0} BLOCKED daily loss cap active.", LogPrefix));
                return;
            }
            if (_tradesThisSession >= MaxTradesPerSession)
            {
                Print(string.Format("{0} BLOCKED max trades reached {1}/{2}.", LogPrefix, _tradesThisSession, MaxTradesPerSession));
                return;
            }
            if (CurrentBar - _lastEntryBar < MinBarsBetweenEntries)
            {
                Print(string.Format("{0} BLOCKED cooldown active lastEntryBar={1} currentBar={2} minGap={3}.", LogPrefix, _lastEntryBar, CurrentBar, MinBarsBetweenEntries));
                return;
            }

            LvnCandidate candidate;
            if (!TryGetTriggeredLvnCross(out candidate))
                return;

            if (candidate.Direction > 0 && !_allowLongEntries)
            {
                Print(string.Format("{0} BLOCKED long toggle OFF for LVN {1:F2}.", LogPrefix, candidate.Price));
                return;
            }
            if (candidate.Direction < 0 && !_allowShortEntries)
            {
                Print(string.Format("{0} BLOCKED short toggle OFF for LVN {1:F2}.", LogPrefix, candidate.Price));
                return;
            }

            if (!PassesVolumeFilter(out double avgVolume))
            {
                LogDebug(string.Format("BLOCKED volume filter current={0} avg20={1:F2} ratio={2:F2}", Volume[0], avgVolume, VolumeFilterRatio));
                return;
            }

            double entryPrice = Close[0];
            ConfigureTradePlan(candidate.Direction, entryPrice);
            MaybeApplyRadarTarget(candidate.Direction, entryPrice);

            LogDebug(string.Format(
                "CANDIDATE {0} lvn={1:F2} source={2} dist={3:F1}t vol={4} avg20={5:F2} stop={6:F2} t1={7:F2} t2={8:F2}",
                candidate.Direction > 0 ? "LONG" : "SHORT",
                candidate.Price,
                candidate.Source,
                candidate.DistanceTicks,
                Volume[0],
                avgVolume,
                _stopPrice,
                _target1Price,
                _target2Price));

            TryEnterTrade(candidate.Direction);
        }

        private ProfileState CreateProfileState(VPProfilePeriod period, string prefix)
        {
            return new ProfileState
            {
                Period = period,
                Prefix = prefix,
                Bars = new List<BarHLV>(),
                VpValues = new double[Math.Max(10, LvnRows) + 1],
                VpYVol = new double[Math.Max(10, LvnRows) + 1],
                LvnPrices = new List<double>(),
                DrawTags = new List<string>(),
                LastPeriodKey = -1,
            };
        }

        private void CollectLtfBar()
        {
            if (CurrentBars[1] < 0)
                return;

            DateTime barTime = Time[0];
            BarHLV bar = new BarHLV { H = High[0], L = Low[0], V = Volume[0] };

            AddBarToProfile(_dailyProfile, barTime, bar);
            AddBarToProfile(_weeklyProfile, barTime, bar);
            AddBarToProfile(_monthlyProfile, barTime, bar);
        }

        private void AddBarToProfile(ProfileState profile, DateTime barTime, BarHLV bar)
        {
            if (profile == null)
                return;

            int periodKey = GetPeriodKey(profile.Period, barTime);
            if (profile.LastPeriodKey != -1 && periodKey != profile.LastPeriodKey)
                ClearProfile(profile);

            profile.LastPeriodKey = periodKey;
            profile.Bars.Add(bar);
        }

        private int GetPeriodKey(VPProfilePeriod period, DateTime time)
        {
            switch (period)
            {
                case VPProfilePeriod.Daily:
                    return time.Year * 1000 + time.DayOfYear;
                case VPProfilePeriod.Weekly:
                    int dow = ((int)time.DayOfWeek + 6) % 7;
                    DateTime monday = time.Date.AddDays(-dow);
                    return monday.Year * 1000 + monday.DayOfYear;
                default:
                    return time.Year * 12 + time.Month;
            }
        }

        private void ClearProfile(ProfileState profile)
        {
            if (profile == null)
                return;

            profile.Bars.Clear();
            profile.LvnPrices.Clear();
            Array.Clear(profile.VpValues, 0, profile.VpValues.Length);
            Array.Clear(profile.VpYVol, 0, profile.VpYVol.Length);
            ClearProfileDrawings(profile);
        }

        private void RebuildAllProfiles()
        {
            RebuildProfile(_dailyProfile);
            RebuildProfile(_weeklyProfile);
            RebuildProfile(_monthlyProfile);
        }

        private void RebuildProfile(ProfileState profile)
        {
            if (profile == null || profile.Bars.Count == 0)
                return;

            double yMax = double.MinValue;
            double yMin = double.MaxValue;
            foreach (BarHLV b in profile.Bars)
            {
                if (b.H > yMax) yMax = b.H;
                if (b.L < yMin) yMin = b.L;
            }

            if (yMax <= yMin)
                return;

            int rows = Math.Max(10, LvnRows);
            double step = (yMax - yMin) / rows;
            if (step < TickSize) step = TickSize;

            EnsureProfileArrays(profile, rows + 1);

            for (int i = 0; i <= rows; i++)
                profile.VpYVol[i] = yMin + i * (yMax - yMin) / rows;

            Array.Clear(profile.VpValues, 0, profile.VpValues.Length);

            foreach (BarHLV b in profile.Bars)
            {
                if (b.V <= 0) continue;
                int r1 = (int)Math.Floor((Math.Min(b.L, b.H) - yMin) / step);
                int r2 = (int)Math.Floor((Math.Max(b.L, b.H) - yMin) / step);
                r1 = Math.Max(0, Math.Min(r1, rows));
                r2 = Math.Max(0, Math.Min(r2, rows));
                int span = r2 - r1 + 1;
                double addV = span > 0 ? b.V / span : 0.0;
                for (int r = r1; r <= r2; r++)
                    profile.VpValues[r] += addV;
            }

            profile.LvnPrices.Clear();
            int size = rows + 1;
            if (size <= LvnStrength * 2 + 1)
                return;

            var lvnIndices = new List<int>();
            for (int i = 0; i < size; i++)
            {
                double val = profile.VpValues[i];
                if (val <= 0) continue;

                bool isLvn = true;
                for (int j = -LvnStrength; j <= LvnStrength; j++)
                {
                    if (j == 0) continue;
                    int k = i + j;
                    if (k < 0 || k >= size) continue;
                    if (profile.VpValues[k] <= 0) continue;
                    if (profile.VpValues[k] < val)
                    {
                        isLvn = false;
                        break;
                    }
                }
                if (isLvn)
                    lvnIndices.Add(i);
            }

            foreach (int i in lvnIndices)
                profile.LvnPrices.Add(RoundToTick(profile.VpYVol[i]));
        }

        private void EnsureProfileArrays(ProfileState profile, int size)
        {
            if (profile.VpValues == null || profile.VpValues.Length != size)
                profile.VpValues = new double[size];
            if (profile.VpYVol == null || profile.VpYVol.Length != size)
                profile.VpYVol = new double[size];
        }

        private void UpdateActiveLvnPrices()
        {
            _activeLvnPrices.Clear();
            var seen = new HashSet<double>();

            AddProfileLvns(_showDailyLvn, _dailyProfile, seen);
            AddProfileLvns(_showWeeklyLvn, _weeklyProfile, seen);
            AddProfileLvns(_showMonthlyLvn, _monthlyProfile, seen);

            _activeLvnPrices.Sort();
        }

        private void AddProfileLvns(bool enabled, ProfileState profile, HashSet<double> seen)
        {
            if (!enabled || profile == null || profile.LvnPrices == null)
                return;

            foreach (double price in profile.LvnPrices)
            {
                double normalized = RoundToTick(price);
                if (seen.Add(normalized))
                    _activeLvnPrices.Add(normalized);
            }
        }

        private void RefreshAllLvnDrawings()
        {
            RefreshProfileDrawings(_dailyProfile, _showDailyLvn);
            RefreshProfileDrawings(_weeklyProfile, _showWeeklyLvn);
            RefreshProfileDrawings(_monthlyProfile, _showMonthlyLvn);
        }

        private void RefreshProfileDrawings(ProfileState profile, bool visible)
        {
            if (profile == null)
                return;

            ClearProfileDrawings(profile);
            if (!visible || profile.LvnPrices == null || profile.LvnPrices.Count == 0)
                return;

            double globalMinVol = double.MaxValue;
            foreach (double val in profile.VpValues)
                if (val > 0 && val < globalMinVol) globalMinVol = val;

            for (int i = 0; i < profile.LvnPrices.Count; i++)
            {
                double price = profile.LvnPrices[i];
                int idx = FindNearestProfileIndex(profile, price);
                double val = idx >= 0 && idx < profile.VpValues.Length ? profile.VpValues[idx] : 0.0;
                Brush color = Close[0] > price
                    ? MakeFrozenBrush(Color.FromRgb(0x25, 0x63, 0xEB))
                    : MakeFrozenBrush(Color.FromRgb(0x1E, 0x3A, 0x8A));
                DashStyleHelper dash = globalMinVol < double.MaxValue && Math.Abs(val - globalMinVol) < Math.Max(0.0001, globalMinVol * 0.001)
                    ? DashStyleHelper.Solid
                    : DashStyleHelper.Dash;
                string tag = string.Format("LVNRADAR_{0}_{1}", profile.Prefix, i);
                profile.DrawTags.Add(tag);
                Draw.HorizontalLine(this, tag, false, price, color, dash, 1);
            }
        }

        private int FindNearestProfileIndex(ProfileState profile, double price)
        {
            int bestIndex = -1;
            double bestDistance = double.MaxValue;
            for (int i = 0; i < profile.VpYVol.Length; i++)
            {
                double distance = Math.Abs(profile.VpYVol[i] - price);
                if (distance < bestDistance)
                {
                    bestDistance = distance;
                    bestIndex = i;
                }
            }
            return bestIndex;
        }

        private void ClearProfileDrawings(ProfileState profile)
        {
            if (profile == null || profile.DrawTags == null)
                return;

            foreach (string tag in profile.DrawTags)
                RemoveDrawObject(tag);
            profile.DrawTags.Clear();
        }

        private void HandleSessionReset()
        {
            if (Time[0].Date == _sessionDate)
                return;

            _sessionDate = Time[0].Date;
            _tradesThisSession = 0;
            _killSwitch = false;
            _sessionStartCumProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit;
            _sessionAtrSum = 0.0;
            _sessionAtrCount = 0;
            Print(string.Format("{0} Session reset {1:yyyy-MM-dd}.", LogPrefix, _sessionDate));
        }

        private void UpdateSessionAtr()
        {
            if (_atr == null)
                return;

            double atrValue = _atr[0];
            if (atrValue <= 0.0)
                return;

            _sessionAtrSum += atrValue;
            _sessionAtrCount++;
        }

        private double GetSessionAverageAtr()
        {
            return _sessionAtrCount > 0 ? _sessionAtrSum / _sessionAtrCount : 0.0;
        }

        private void UpdateSessionRiskLock()
        {
            double sessionCumProfit = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - _sessionStartCumProfit;
            if (sessionCumProfit <= -Math.Abs(DailyLossCapDollars))
                _killSwitch = true;
        }

        private bool IsBlackoutTime(int hhmm)
        {
            if (BlackoutWindowStart == BlackoutWindowEnd)
                return false;
            if (BlackoutWindowStart < BlackoutWindowEnd)
                return hhmm >= BlackoutWindowStart && hhmm <= BlackoutWindowEnd;
            return hhmm >= BlackoutWindowStart || hhmm <= BlackoutWindowEnd;
        }

        private bool TryGetTriggeredLvnCross(out LvnCandidate best)
        {
            best = null;
            if (_activeLvnPrices.Count == 0)
            {
                LogDebug("BLOCKED no active LVN levels");
                return false;
            }

            double previousClose = Close[1];
            double currentClose = Close[0];
            double maxDistanceTicks = Math.Max(1, LvnApproachTicks);

            foreach (double level in _activeLvnPrices)
            {
                bool crossedUp = previousClose <= level && currentClose > level;
                bool crossedDown = previousClose >= level && currentClose < level;
                if (!crossedUp && !crossedDown)
                    continue;

                double distanceTicks = Math.Min(Math.Abs(currentClose - level), Math.Abs(previousClose - level)) / TickSize;
                if (distanceTicks > maxDistanceTicks)
                    continue;

                int direction = crossedUp ? 1 : -1;
                string source = GetProfileSourceForLevel(level);
                if (best == null || distanceTicks < best.DistanceTicks)
                {
                    best = new LvnCandidate
                    {
                        Price = level,
                        Direction = direction,
                        DistanceTicks = distanceTicks,
                        Source = source,
                    };
                }
            }

            if (best == null)
                LogDebug(string.Format("BLOCKED no LVN cross prev={0:F2} close={1:F2} active={2}", previousClose, currentClose, _activeLvnPrices.Count));

            return best != null;
        }

        private string GetProfileSourceForLevel(double level)
        {
            var sources = new List<string>();
            if (_showDailyLvn && ContainsLevel(_dailyProfile, level)) sources.Add("D");
            if (_showWeeklyLvn && ContainsLevel(_weeklyProfile, level)) sources.Add("W");
            if (_showMonthlyLvn && ContainsLevel(_monthlyProfile, level)) sources.Add("M");
            return sources.Count > 0 ? string.Join("/", sources) : "LVN";
        }

        private bool ContainsLevel(ProfileState profile, double level)
        {
            if (profile == null || profile.LvnPrices == null)
                return false;
            for (int i = 0; i < profile.LvnPrices.Count; i++)
                if (Math.Abs(profile.LvnPrices[i] - level) <= TickSize * 0.5)
                    return true;
            return false;
        }

        private bool PassesVolumeFilter(out double avgVolume)
        {
            avgVolume = GetAverageVolume20();
            if (!VolumeFilterEnabled)
                return true;
            if (avgVolume <= 0.0)
                return false;
            return Volume[0] >= avgVolume * VolumeFilterRatio;
        }

        private double GetAverageVolume20()
        {
            if (CurrentBar < 20)
                return 0.0;

            double sum = 0.0;
            for (int i = 1; i <= 20; i++)
                sum += Volume[i];
            return sum / 20.0;
        }

        private void ConfigureTradePlan(int direction, double entryPrice)
        {
            _activeDirection = direction;
            _entryPrice = entryPrice;
            _entryBar = CurrentBar;
            _breakevenMoved = false;

            _stopPrice = direction > 0
                ? entryPrice - StopLossTicks * TickSize
                : entryPrice + StopLossTicks * TickSize;

            _target1Price = direction > 0
                ? entryPrice + ScaleOutTargetTicks * TickSize
                : entryPrice - ScaleOutTargetTicks * TickSize;

            _target2Price = direction > 0
                ? entryPrice + TargetTicks * TickSize
                : entryPrice - TargetTicks * TickSize;
        }

        private void MaybeApplyRadarTarget(int direction, double entryPrice)
        {
            if (!_radarTargetsEnabled || !UseRadarTargets || _depthRadar == null)
                return;

            double? wallTarget = direction > 0
                ? FindNearestWallAbove(entryPrice, _depthRadar.GenuineAskWallPrices)
                : FindNearestWallBelow(entryPrice, _depthRadar.GenuineBidWallPrices);
            if (!wallTarget.HasValue)
                return;

            double wallTicks = Math.Abs(wallTarget.Value - entryPrice) / TickSize;
            if (wallTicks < 8.0)
                return;

            _target2Price = wallTarget.Value;
            Print(string.Format("{0} Radar-adjusted T2 to genuine wall {1:F2} ({2:F1} ticks from entry).", LogPrefix, _target2Price, wallTicks));
        }

        private double? FindNearestWallAbove(double entryPrice, List<double> prices)
        {
            if (prices == null || prices.Count == 0)
                return null;

            double? best = null;
            foreach (double price in prices)
            {
                if (price <= entryPrice)
                    continue;
                if (!best.HasValue || price < best.Value)
                    best = price;
            }
            return best;
        }

        private double? FindNearestWallBelow(double entryPrice, List<double> prices)
        {
            if (prices == null || prices.Count == 0)
                return null;

            double? best = null;
            foreach (double price in prices)
            {
                if (price >= entryPrice)
                    continue;
                if (!best.HasValue || price > best.Value)
                    best = price;
            }
            return best;
        }

        private void TryEnterTrade(int direction)
        {
            bool isLive = Account != null && Account.Connection != null
                && Account.Connection.Status == ConnectionStatus.Connected
                && !(Account.Name ?? string.Empty).Contains("Playback")
                && !(Account.Name ?? string.Empty).Contains("Sim");
            bool executionBlocked = isLive
                ? (!_autoExecutionEnabled || !EnableAutoExecution || DryRunMode)
                : !_autoExecutionEnabled;

            if (executionBlocked)
            {
                Print(string.Format("{0} DRY-RUN candidate {1} entry={2:F2} stop={3:F2} t1={4:F2} t2={5:F2} auto={6} enableAuto={7} isLive={8}.",
                    LogPrefix,
                    direction > 0 ? "LONG" : "SHORT",
                    _entryPrice,
                    _stopPrice,
                    _target1Price,
                    _target2Price,
                    _autoExecutionEnabled,
                    EnableAutoExecution,
                    isLive));
                return;
            }

            if (ScaleOutEnabled && MaxContractsPerTrade < 2)
            {
                Print(string.Format("{0} BLOCKED scale-out requires at least 2 contracts. MaxContractsPerTrade={1}.", LogPrefix, MaxContractsPerTrade));
                return;
            }

            _activeEntrySignal = "";
            _activeT1Signal = "";
            _activeT2Signal = "";

            SetStopLoss(CalculationMode.Ticks, StopLossTicks);
            SetProfitTarget(CalculationMode.Ticks, TargetTicks);

            _lastEntryBar = CurrentBar;
            _tradesThisSession++;

            if (direction > 0)
                EnterLong(MaxContractsPerTrade, "LVNRadarEntry");
            else
                EnterShort(MaxContractsPerTrade, "LVNRadarEntry");

            Print(string.Format("{0} LIVE entry submitted {1} qty={2} signal={3} stop={4:F2} t1={5:F2} t2={6:F2}.",
                LogPrefix,
                direction > 0 ? "LONG" : "SHORT",
                MaxContractsPerTrade,
                _activeEntrySignal,
                _stopPrice,
                _target1Price,
                _target2Price));
        }

        private void ExitLongOrShortLimit(int direction, int quantity, double limitPrice, string signalName, string fromEntrySignal)
        {
            if (quantity <= 0)
                return;

            if (direction > 0)
                ExitLongLimit(0, true, quantity, limitPrice, signalName, fromEntrySignal);
            else
                ExitShortLimit(0, true, quantity, limitPrice, signalName, fromEntrySignal);
        }

        private void ManageOpenTrade()
        {
            if (Position.MarketPosition == MarketPosition.Flat)
                return;

            if (MaxBarsInTrade > 0 && _entryBar >= 0 && CurrentBar - _entryBar >= MaxBarsInTrade)
            {
                Print(string.Format("{0} EXIT max-bars rule hit after {1} bars.", LogPrefix, CurrentBar - _entryBar));
                ExitPosition("LVNRADAR_MAXBARS");
                return;
            }

            if (BreakevenEnabled && !_breakevenMoved)
            {
                double mfeTicks = _activeDirection > 0
                    ? (Close[0] - _entryPrice) / TickSize
                    : (_entryPrice - Close[0]) / TickSize;

                if (mfeTicks >= BreakevenActivationTicks)
                {
                    _stopPrice = _activeDirection > 0
                        ? _entryPrice + BreakevenOffsetTicks * TickSize
                        : _entryPrice - BreakevenOffsetTicks * TickSize;

                    SetStopLoss("LVNRadarEntry", CalculationMode.Price, _stopPrice, false);
                    _breakevenMoved = true;
                    Print(string.Format("{0} MOVE stop to breakeven {1:F2} after {2:F1} ticks MFE.", LogPrefix, _stopPrice, mfeTicks));
                }
            }
        }

        private void ExitPosition(string signalName)
        {
            if (Position.MarketPosition == MarketPosition.Long)
                ExitLong(signalName);
            else if (Position.MarketPosition == MarketPosition.Short)
                ExitShort(signalName);
        }

        protected override void OnPositionUpdate(Position position, double averagePrice, int quantity, MarketPosition marketPosition)
        {
            if (marketPosition == MarketPosition.Flat && quantity == 0)
            {
                Print(string.Format("{0} Position flat. Session trades={1}/{2} sessionPnL={3:F2}.",
                    LogPrefix,
                    _tradesThisSession,
                    MaxTradesPerSession,
                    SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - _sessionStartCumProfit));
                ResetTradeState();
            }
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
            MarketPosition marketPosition, string orderId, DateTime time)
        {
            string orderName = execution != null && execution.Order != null ? execution.Order.Name : "?";
            Print(string.Format("{0} Execution {1} {2} @ {3:F2} qty={4} orderId={5}.", LogPrefix, marketPosition, orderName, price, quantity, orderId));
        }

        private void ResetTradeState()
        {
            _activeEntrySignal = null;
            _activeT1Signal = null;
            _activeT2Signal = null;
            _activeDirection = 0;
            _entryBar = -1;
            _entryPrice = 0.0;
            _stopPrice = 0.0;
            _target1Price = 0.0;
            _target2Price = 0.0;
            _breakevenMoved = false;
        }

        private void ProcessPendingPanelActions()
        {
            if (_pendingCloseRequest)
            {
                _pendingCloseRequest = false;
                if (Position.MarketPosition != MarketPosition.Flat)
                {
                    Print(string.Format("{0} PANEL close request.", LogPrefix));
                    ExitPosition("LVNRADAR_PANEL_CLOSE");
                }
            }

            if (_pendingBreakevenRequest)
            {
                _pendingBreakevenRequest = false;
                if (Position.MarketPosition != MarketPosition.Flat && _activeDirection != 0 && !string.IsNullOrWhiteSpace(_activeEntrySignal))
                {
                    _stopPrice = _activeDirection > 0
                        ? _entryPrice + BreakevenOffsetTicks * TickSize
                        : _entryPrice - BreakevenOffsetTicks * TickSize;
                    SetStopLoss("LVNRadarEntry", CalculationMode.Price, _stopPrice, false);
                    _breakevenMoved = true;
                    Print(string.Format("{0} PANEL breakeven move stop={1:F2}.", LogPrefix, _stopPrice));
                }
            }
        }

        private void UpdatePanelCaches()
        {
            LvnCandidate lvn;
            _lastNearestLvnDisplay = TryGetNearestLvnCandidate(Close[0], out lvn)
                ? string.Format("{0:F2} ({1}, {2:F1}t)", lvn.Price, lvn.Source, lvn.DistanceTicks)
                : "—";

            _lastLvnStatusDisplay = lvn != null
                ? string.Format("LVNs: {0} | nearest {1:F2} ({2:F1}t)", _activeLvnPrices.Count, lvn.Price, lvn.DistanceTicks)
                : string.Format("LVNs: {0} | nearest —", _activeLvnPrices.Count);

            double? nearestWall = FindNearestWallAnySide(Close[0]);
            _lastNearestWallDisplay = nearestWall.HasValue
                ? string.Format("{0:F2} (G)", nearestWall.Value)
                : "—";
        }

        private bool TryGetNearestLvnCandidate(double price, out LvnCandidate best)
        {
            best = null;
            foreach (double level in _activeLvnPrices)
            {
                double distanceTicks = Math.Abs(price - level) / TickSize;
                if (best == null || distanceTicks < best.DistanceTicks)
                {
                    best = new LvnCandidate
                    {
                        Price = level,
                        Direction = price >= level ? 1 : -1,
                        DistanceTicks = distanceTicks,
                        Source = GetProfileSourceForLevel(level),
                    };
                }
            }
            return best != null;
        }

        private void SchedulePanelUpdate()
        {
            DispatchToUi(UpdateWpfPanel);
        }

        private void DispatchToUi(Action action)
        {
            if (action == null)
                return;

            try
            {
                if (ChartControl != null && ChartControl.Dispatcher != null)
                    ChartControl.Dispatcher.InvokeAsync(action);
                else if (_chartWindow != null && _chartWindow.Dispatcher != null)
                    _chartWindow.Dispatcher.InvokeAsync(action);
            }
            catch { }
        }

        private void CreateOrAttachWpfPanel()
        {
            try
            {
                if (ChartControl == null)
                    return;

                _chartWindow = Window.GetWindow(ChartControl) as NinjaTrader.Gui.Chart.Chart;
                if (_chartWindow == null)
                    return;

                _chartTab = _chartWindow.MainTabControl != null
                    ? (_chartWindow.MainTabControl.SelectedContent as ChartTab ?? FindVisualParent<ChartTab>(ChartControl))
                    : FindVisualParent<ChartTab>(ChartControl);
                _chartGrid = _chartWindow.MainTabControl != null
                    ? _chartWindow.MainTabControl.Parent as Grid
                    : _chartWindow.Content as Grid;
                _chartTraderControl = _chartWindow.FindFirst("ChartWindowChartTraderControl") as ChartTrader;
                _chartTraderGrid = _chartTraderControl != null
                    ? (_chartTraderControl.FindName("grdMain") as Grid ?? _chartTraderControl.Content as Grid)
                    : null;

                if (_chartTraderGrid == null)
                    return;

                if (!_tabSelectionWired && _chartWindow.MainTabControl != null)
                {
                    _chartWindow.MainTabControl.SelectionChanged += OnChartTabSelectionChanged;
                    _tabSelectionWired = true;
                }

                if (_chartTraderPanelBorder == null)
                    BuildWpfPanel();

                SyncPanelVisibility();
                UpdateWpfPanel();
            }
            catch (Exception ex)
            {
                Print(string.Format("{0} PANEL create error: {1}", LogPrefix, ex.Message));
            }
        }

        private void BuildWpfPanel()
        {
            var panelBackground = MakeFrozenBrush(Color.FromRgb(0x1A, 0x1F, 0x29));

            _chartTraderPanelBorder = new Border
            {
                Background = panelBackground,
                BorderBrush = MakeFrozenBrush(Color.FromRgb(0x2C, 0x3E, 0x50)),
                BorderThickness = new Thickness(1),
                Margin = new Thickness(6, 8, 6, 6),
                Padding = new Thickness(0),
                HorizontalAlignment = HorizontalAlignment.Stretch,
                VerticalAlignment = VerticalAlignment.Stretch,
                MinWidth = 260,
            };

            _chartTraderPanelScrollViewer = new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                Background = panelBackground,
            };

            var stack = new StackPanel
            {
                Orientation = Orientation.Vertical,
                Margin = new Thickness(8),
            };

            stack.Children.Add(BuildHeaderSection());
            stack.Children.Add(BuildMarketSection());
            stack.Children.Add(BuildLvnFilterSection());
            stack.Children.Add(BuildVolumeFilterSection());
            stack.Children.Add(BuildStatusSection());
            stack.Children.Add(BuildExecutionSection());

            _chartTraderPanelScrollViewer.Content = stack;
            _chartTraderPanelBorder.Child = _chartTraderPanelScrollViewer;
        }

        private FrameworkElement BuildHeaderSection()
        {
            var section = CreateSectionContainer();
            section.Children.Add(CreateTitleBar("DEEP6 LVN × RADAR", MakeFrozenBrush(Color.FromRgb(0x1A, 0x1F, 0x29)), 12));
            _connectionStatusText = CreateValueText("● DISCONNECTED", 11, MakeFrozenBrush(Color.FromRgb(0xE7, 0x4C, 0x3C)));
            _connectionStatusText.Margin = new Thickness(0, 8, 0, 0);
            section.Children.Add(_connectionStatusText);
            return section;
        }

        private FrameworkElement BuildMarketSection()
        {
            var section = CreateSectionContainer();
            _marketStateText = CreateBannerText("Paused", MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));
            section.Children.Add(_marketStateText);

            _lvnStatusText = CreateBannerText("LVNs: 0 | nearest —", MakeFrozenBrush(Color.FromRgb(0x34, 0x98, 0xDB)));
            section.Children.Add(_lvnStatusText);

            var dirGrid = CreateTwoColumnGrid();
            _longToggleButton = CreateActionButton("Long enabled", OnLongToggleClick);
            _shortToggleButton = CreateActionButton("Short enabled", OnShortToggleClick);
            dirGrid.Children.Add(_longToggleButton);
            dirGrid.Children.Add(_shortToggleButton);
            Grid.SetColumn(_shortToggleButton, 1);
            section.Children.Add(dirGrid);

            var actionGrid = CreateTwoColumnGrid();
            _breakevenButton = CreateBlueButton("Break even", OnBreakEvenClick);
            _closeButton = CreateBlueButton("Close", OnCloseClick);
            actionGrid.Children.Add(_breakevenButton);
            actionGrid.Children.Add(_closeButton);
            Grid.SetColumn(_closeButton, 1);
            section.Children.Add(actionGrid);

            _atmSelectorText = CreateLabelText("ATM Strategy: Managed strategy");
            _atmSelectorText.Margin = new Thickness(0, 4, 0, 0);
            section.Children.Add(_atmSelectorText);
            return section;
        }

        private FrameworkElement BuildLvnFilterSection()
        {
            var section = CreateSectionContainer();
            section.Children.Add(CreateSectionHeader("LVN FILTER"));
            section.Children.Add(CreateLabeledTextBoxRow("Approach ticks", out _approachTicksTextBox, LvnApproachTicks.ToString(), OnApproachTicksChanged));

            var toggleGrid = new Grid { Margin = new Thickness(0, 4, 0, 0) };
            toggleGrid.ColumnDefinitions.Add(new ColumnDefinition());
            toggleGrid.ColumnDefinitions.Add(new ColumnDefinition());
            toggleGrid.ColumnDefinitions.Add(new ColumnDefinition());
            _lvnDailyButton = CreateToggleButton("LVN-D", OnLvnDailyToggleClick);
            _lvnWeeklyButton = CreateToggleButton("LVN-W", OnLvnWeeklyToggleClick);
            _lvnMonthlyButton = CreateToggleButton("LVN-M", OnLvnMonthlyToggleClick);
            toggleGrid.Children.Add(_lvnDailyButton);
            toggleGrid.Children.Add(_lvnWeeklyButton);
            toggleGrid.Children.Add(_lvnMonthlyButton);
            Grid.SetColumn(_lvnWeeklyButton, 1);
            Grid.SetColumn(_lvnMonthlyButton, 2);
            section.Children.Add(toggleGrid);
            return section;
        }

        private FrameworkElement BuildVolumeFilterSection()
        {
            var section = CreateSectionContainer();
            section.Children.Add(CreateSectionHeader("VOLUME FILTER"));
            section.Children.Add(CreateLabeledTextBoxRow("Volume ratio", out _volumeFilterRatioTextBox, VolumeFilterRatio.ToString("0.00"), OnVolumeFilterRatioChanged));

            var grid = CreateTwoColumnGrid();
            _volumeFilterButton = CreateSignalToggleButton("Volume Filter", OnVolumeFilterToggleClick);
            _radarTargetsButton = CreateSignalToggleButton("RADAR Targets", OnRadarTargetsToggleClick);
            grid.Children.Add(_volumeFilterButton);
            grid.Children.Add(_radarTargetsButton);
            Grid.SetColumn(_radarTargetsButton, 1);
            section.Children.Add(grid);
            return section;
        }

        private FrameworkElement BuildStatusSection()
        {
            var section = CreateSectionContainer();
            section.Children.Add(CreateSectionHeader("STATUS"));
            section.Children.Add(CreateStatusRow("Session P&L", out _sessionPnLValueText));
            section.Children.Add(CreateStatusRow("Trades today", out _tradesTodayValueText));
            section.Children.Add(CreateStatusRow("Nearest LVN", out _nearestLvnValueText));
            section.Children.Add(CreateStatusRow("Nearest Wall", out _nearestWallValueText));
            return section;
        }

        private FrameworkElement BuildExecutionSection()
        {
            var section = CreateSectionContainer();
            section.Children.Add(CreateSectionHeader("EXECUTION"));
            _autoExecuteButton = CreateLargeToggleButton(OnAutoExecuteToggleClick);
            _autoExecuteText = CreateCenteredButtonText("● AUTO EXECUTE (DISABLED)");
            _autoExecuteButton.Content = _autoExecuteText;
            section.Children.Add(_autoExecuteButton);

            _dryRunButton = CreateToggleButton(string.Empty, OnDryRunToggleClick, true);
            _dryRunText = CreateCenteredButtonText("DRY RUN MODE (ACTIVE)");
            _dryRunButton.Content = _dryRunText;
            section.Children.Add(_dryRunButton);
            return section;
        }

        private StackPanel CreateSectionContainer()
        {
            return new StackPanel
            {
                Orientation = Orientation.Vertical,
                Margin = new Thickness(0, 0, 0, 8),
            };
        }

        private Border CreateTitleBar(string text, Brush background, double fontSize)
        {
            return new Border
            {
                Background = background,
                Padding = new Thickness(8),
                Child = new TextBlock
                {
                    Text = text,
                    Foreground = Brushes.White,
                    FontFamily = new FontFamily("Segoe UI"),
                    FontSize = fontSize,
                    FontWeight = FontWeights.Bold,
                }
            };
        }

        private Border CreateSectionHeader(string text)
        {
            return CreateTitleBar(text, MakeFrozenBrush(Color.FromRgb(0x2C, 0x3E, 0x50)), 10);
        }

        private TextBlock CreateLabelText(string text)
        {
            return new TextBlock
            {
                Text = text,
                Foreground = Brushes.White,
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 11,
                Margin = new Thickness(0, 4, 0, 2),
                TextWrapping = TextWrapping.Wrap,
            };
        }

        private TextBlock CreateValueText(string text, double fontSize, Brush brush)
        {
            return new TextBlock
            {
                Text = text,
                Foreground = brush,
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = fontSize,
                FontWeight = FontWeights.SemiBold,
                TextWrapping = TextWrapping.Wrap,
            };
        }

        private TextBlock CreateBannerText(string text, Brush background)
        {
            return new TextBlock
            {
                Text = text,
                Foreground = Brushes.White,
                Background = background,
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Padding = new Thickness(8, 6, 8, 6),
                Margin = new Thickness(0, 4, 0, 4),
                TextAlignment = TextAlignment.Center,
            };
        }

        private Grid CreateTwoColumnGrid()
        {
            var grid = new Grid { Margin = new Thickness(0, 4, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition());
            grid.ColumnDefinitions.Add(new ColumnDefinition());
            return grid;
        }

        private Grid CreateLabeledTextBoxRow(string label, out TextBox textBox, string value, TextChangedEventHandler handler)
        {
            var grid = new Grid { Margin = new Thickness(0, 4, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            grid.Children.Add(CreateLabelText(label));

            textBox = new TextBox
            {
                Text = value,
                MinWidth = 56,
                Height = 28,
                Margin = new Thickness(8, 0, 0, 0),
                Padding = new Thickness(6, 4, 6, 4),
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 11,
                VerticalContentAlignment = VerticalAlignment.Center,
                Background = MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)),
                Foreground = Brushes.White,
                BorderBrush = MakeFrozenBrush(Color.FromRgb(0x52, 0x66, 0x7A)),
            };
            textBox.TextChanged += handler;

            grid.Children.Add(textBox);
            Grid.SetColumn(textBox, 1);
            return grid;
        }

        private Grid CreateStatusRow(string label, out TextBlock valueText)
        {
            var grid = new Grid { Margin = new Thickness(0, 4, 0, 0) };
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Auto) });
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
            grid.Children.Add(CreateLabelText(label + ":"));
            valueText = CreateValueText("—", 13, Brushes.White);
            valueText.Margin = new Thickness(8, 4, 0, 2);
            grid.Children.Add(valueText);
            Grid.SetColumn(valueText, 1);
            return grid;
        }

        private Button CreateActionButton(string text, RoutedEventHandler handler)
        {
            var button = CreateStyledButton(text, MakeFrozenBrush(Color.FromRgb(0x34, 0x98, 0xDB)), 36);
            button.Click += handler;
            return button;
        }

        private Button CreateBlueButton(string text, RoutedEventHandler handler)
        {
            return CreateActionButton(text, handler);
        }

        private Button CreateToggleButton(string text, RoutedEventHandler handler, bool fullWidth = false)
        {
            var button = CreateStyledButton(text, MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)), 36);
            if (fullWidth)
                button.HorizontalAlignment = HorizontalAlignment.Stretch;
            button.Click += handler;
            return button;
        }

        private Button CreateSignalToggleButton(string text, RoutedEventHandler handler)
        {
            return CreateToggleButton(text, handler, true);
        }

        private Button CreateLargeToggleButton(RoutedEventHandler handler)
        {
            var button = CreateStyledButton(string.Empty, MakeFrozenBrush(Color.FromRgb(0xE7, 0x4C, 0x3C)), 48);
            button.Click += handler;
            button.Margin = new Thickness(0, 4, 0, 4);
            return button;
        }

        private TextBlock CreateCenteredButtonText(string text)
        {
            return new TextBlock
            {
                Text = text,
                Foreground = Brushes.White,
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 12,
                FontWeight = FontWeights.Bold,
                HorizontalAlignment = HorizontalAlignment.Center,
                VerticalAlignment = VerticalAlignment.Center,
                TextAlignment = TextAlignment.Center,
            };
        }

        private Button CreateStyledButton(string text, Brush background, double height)
        {
            return new Button
            {
                Content = text,
                Height = height,
                Margin = new Thickness(0, 4, 4, 0),
                Padding = new Thickness(8, 6, 8, 6),
                Background = background,
                Foreground = Brushes.White,
                BorderBrush = MakeFrozenBrush(Color.FromRgb(0x1A, 0x1F, 0x29)),
                BorderThickness = new Thickness(1),
                HorizontalAlignment = HorizontalAlignment.Stretch,
                FontFamily = new FontFamily("Segoe UI"),
                FontSize = 11,
                FontWeight = FontWeights.SemiBold,
                Template = CreateRoundedButtonTemplate(),
            };
        }

        private ControlTemplate CreateRoundedButtonTemplate()
        {
            var template = new ControlTemplate(typeof(Button));
            var border = new FrameworkElementFactory(typeof(Border));
            border.SetBinding(Border.BackgroundProperty, new System.Windows.Data.Binding("Background") { RelativeSource = new System.Windows.Data.RelativeSource(System.Windows.Data.RelativeSourceMode.TemplatedParent) });
            border.SetBinding(Border.BorderBrushProperty, new System.Windows.Data.Binding("BorderBrush") { RelativeSource = new System.Windows.Data.RelativeSource(System.Windows.Data.RelativeSourceMode.TemplatedParent) });
            border.SetBinding(Border.BorderThicknessProperty, new System.Windows.Data.Binding("BorderThickness") { RelativeSource = new System.Windows.Data.RelativeSource(System.Windows.Data.RelativeSourceMode.TemplatedParent) });
            border.SetValue(Border.CornerRadiusProperty, new CornerRadius(4));

            var content = new FrameworkElementFactory(typeof(ContentPresenter));
            content.SetValue(FrameworkElement.HorizontalAlignmentProperty, HorizontalAlignment.Center);
            content.SetValue(FrameworkElement.VerticalAlignmentProperty, VerticalAlignment.Center);
            content.SetBinding(ContentPresenter.MarginProperty, new System.Windows.Data.Binding("Padding") { RelativeSource = new System.Windows.Data.RelativeSource(System.Windows.Data.RelativeSourceMode.TemplatedParent) });
            border.AppendChild(content);
            template.VisualTree = border;
            return template;
        }

        private void SyncPanelVisibility()
        {
            if (_chartTraderGrid == null || _chartTraderPanelBorder == null)
                return;

            bool shouldShow = TabSelected();
            if (shouldShow && !_panelAttached)
            {
                if (_chartTraderPanelRow == null || !_chartTraderGrid.RowDefinitions.Contains(_chartTraderPanelRow))
                {
                    _chartTraderPanelRow = new RowDefinition { Height = GridLength.Auto };
                    _chartTraderGrid.RowDefinitions.Add(_chartTraderPanelRow);
                }

                if (!_chartTraderGrid.Children.Contains(_chartTraderPanelBorder))
                {
                    Grid.SetRow(_chartTraderPanelBorder, _chartTraderGrid.RowDefinitions.Count - 1);
                    Grid.SetColumnSpan(_chartTraderPanelBorder, Math.Max(1, _chartTraderGrid.ColumnDefinitions.Count));
                    _chartTraderGrid.Children.Add(_chartTraderPanelBorder);
                }

                _panelAttached = true;
            }
            else if (!shouldShow && _panelAttached)
            {
                if (_chartTraderGrid.Children.Contains(_chartTraderPanelBorder))
                    _chartTraderGrid.Children.Remove(_chartTraderPanelBorder);
                if (_chartTraderPanelRow != null && _chartTraderGrid.RowDefinitions.Contains(_chartTraderPanelRow))
                    _chartTraderGrid.RowDefinitions.Remove(_chartTraderPanelRow);

                _chartTraderPanelRow = null;
                _panelAttached = false;
            }
        }

        private bool TabSelected()
        {
            return _chartWindow != null
                && _chartWindow.MainTabControl != null
                && _chartTab != null
                && ReferenceEquals(_chartWindow.MainTabControl.SelectedContent, _chartTab);
        }

        private void UpdateWpfPanel()
        {
            try
            {
                if (_chartTraderPanelBorder == null)
                    return;

                SyncPanelVisibility();
                if (!_panelAttached)
                    return;

                bool isConnected = Account != null && Account.Connection != null && Account.Connection.Status == ConnectionStatus.Connected;
                _connectionStatusText.Text = isConnected ? "● CONNECTED" : "● DISCONNECTED";
                _connectionStatusText.Foreground = isConnected
                    ? MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71))
                    : MakeFrozenBrush(Color.FromRgb(0xE7, 0x4C, 0x3C));

                string marketState;
                Brush marketBrush;
                GetMarketStateVisual(out marketState, out marketBrush);
                _marketStateText.Text = marketState;
                _marketStateText.Background = marketBrush;

                _lvnStatusText.Text = _lastLvnStatusDisplay;
                _sessionPnLValueText.Text = GetSessionPnlText();
                _sessionPnLValueText.Foreground = GetSessionPnlBrush();
                _tradesTodayValueText.Text = string.Format("{0}/{1}", _tradesThisSession, MaxTradesPerSession);
                _nearestLvnValueText.Text = _lastNearestLvnDisplay;
                _nearestWallValueText.Text = _lastNearestWallDisplay;
                _atmSelectorText.Text = "ATM Strategy: Managed strategy";

                ApplyToggleButtonStyle(_longToggleButton, _allowLongEntries, MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71)), MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));
                ApplyToggleButtonStyle(_shortToggleButton, _allowShortEntries, MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71)), MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));
                ApplyToggleButtonStyle(_lvnDailyButton, _showDailyLvn, MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71)), MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));
                ApplyToggleButtonStyle(_lvnWeeklyButton, _showWeeklyLvn, MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71)), MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));
                ApplyToggleButtonStyle(_lvnMonthlyButton, _showMonthlyLvn, MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71)), MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));
                ApplyToggleButtonStyle(_volumeFilterButton, VolumeFilterEnabled, MakeFrozenBrush(Color.FromRgb(0x34, 0x98, 0xDB)), MakeFrozenBrush(Color.FromRgb(0x2C, 0x3E, 0x50)));
                ApplyToggleButtonStyle(_radarTargetsButton, _radarTargetsEnabled, MakeFrozenBrush(Color.FromRgb(0x34, 0x98, 0xDB)), MakeFrozenBrush(Color.FromRgb(0x2C, 0x3E, 0x50)));
                ApplyToggleButtonStyle(_autoExecuteButton, _autoExecutionEnabled, MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71)), MakeFrozenBrush(Color.FromRgb(0xE7, 0x4C, 0x3C)));
                ApplyToggleButtonStyle(_dryRunButton, DryRunMode, MakeFrozenBrush(Color.FromRgb(0xF3, 0x9C, 0x12)), MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E)));

                _autoExecuteText.Text = _autoExecutionEnabled ? "● AUTO EXECUTE (ENABLED)" : "● AUTO EXECUTE (DISABLED)";
                _dryRunText.Text = DryRunMode ? "DRY RUN MODE (ACTIVE)" : "DRY RUN MODE (OFF)";

                if (_approachTicksTextBox != null && _approachTicksTextBox.Text != LvnApproachTicks.ToString())
                    _approachTicksTextBox.Text = LvnApproachTicks.ToString();
                if (_volumeFilterRatioTextBox != null && _volumeFilterRatioTextBox.Text != VolumeFilterRatio.ToString("0.00"))
                    _volumeFilterRatioTextBox.Text = VolumeFilterRatio.ToString("0.00");
            }
            catch (Exception ex)
            {
                Print(string.Format("{0} PANEL update error: {1}", LogPrefix, ex.Message));
            }
        }

        private void ApplyToggleButtonStyle(Button button, bool isOn, Brush onBrush, Brush offBrush)
        {
            if (button == null)
                return;
            button.Background = isOn ? onBrush : offBrush;
            button.Foreground = Brushes.White;
        }

        private string GetSessionPnlText()
        {
            double pnl = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - _sessionStartCumProfit;
            return string.Format("{0}{1:F2}", pnl >= 0 ? "+$" : "-$", Math.Abs(pnl));
        }

        private Brush GetSessionPnlBrush()
        {
            double pnl = SystemPerformance.AllTrades.TradesPerformance.Currency.CumProfit - _sessionStartCumProfit;
            return pnl >= 0
                ? MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71))
                : MakeFrozenBrush(Color.FromRgb(0xE7, 0x4C, 0x3C));
        }

        private void GetMarketStateVisual(out string text, out Brush brush)
        {
            if (_killSwitch)
            {
                text = "Kill Switch";
                brush = MakeFrozenBrush(Color.FromRgb(0xE7, 0x4C, 0x3C));
            }
            else if (!_autoExecutionEnabled)
            {
                text = "Paused";
                brush = MakeFrozenBrush(Color.FromRgb(0x34, 0x49, 0x5E));
            }
            else
            {
                text = "Active";
                brush = MakeFrozenBrush(Color.FromRgb(0x2E, 0xCC, 0x71));
            }
        }

        private double? FindNearestWallAnySide(double referencePrice)
        {
            double? best = null;
            Action<List<double>> evaluate = prices =>
            {
                if (prices == null)
                    return;
                foreach (double price in prices)
                {
                    if (!best.HasValue || Math.Abs(price - referencePrice) < Math.Abs(best.Value - referencePrice))
                        best = price;
                }
            };

            if (_depthRadar != null)
            {
                evaluate(_depthRadar.GenuineBidWallPrices);
                evaluate(_depthRadar.GenuineAskWallPrices);
            }

            return best;
        }

        private void OnChartTabSelectionChanged(object sender, SelectionChangedEventArgs e)
        {
            SyncPanelVisibility();
            UpdateWpfPanel();
        }

        private void RemoveWpfPanel()
        {
            try
            {
                if (_chartWindow != null && _chartWindow.MainTabControl != null && _tabSelectionWired)
                    _chartWindow.MainTabControl.SelectionChanged -= OnChartTabSelectionChanged;
            }
            catch { }

            _tabSelectionWired = false;

            UnwireButton(_longToggleButton, OnLongToggleClick);
            UnwireButton(_shortToggleButton, OnShortToggleClick);
            UnwireButton(_breakevenButton, OnBreakEvenClick);
            UnwireButton(_closeButton, OnCloseClick);
            UnwireButton(_lvnDailyButton, OnLvnDailyToggleClick);
            UnwireButton(_lvnWeeklyButton, OnLvnWeeklyToggleClick);
            UnwireButton(_lvnMonthlyButton, OnLvnMonthlyToggleClick);
            UnwireButton(_volumeFilterButton, OnVolumeFilterToggleClick);
            UnwireButton(_radarTargetsButton, OnRadarTargetsToggleClick);
            UnwireButton(_autoExecuteButton, OnAutoExecuteToggleClick);
            UnwireButton(_dryRunButton, OnDryRunToggleClick);

            if (_approachTicksTextBox != null) _approachTicksTextBox.TextChanged -= OnApproachTicksChanged;
            if (_volumeFilterRatioTextBox != null) _volumeFilterRatioTextBox.TextChanged -= OnVolumeFilterRatioChanged;

            if (_chartTraderGrid != null && _chartTraderPanelBorder != null && _chartTraderGrid.Children.Contains(_chartTraderPanelBorder))
                _chartTraderGrid.Children.Remove(_chartTraderPanelBorder);
            if (_chartTraderGrid != null && _chartTraderPanelRow != null && _chartTraderGrid.RowDefinitions.Contains(_chartTraderPanelRow))
                _chartTraderGrid.RowDefinitions.Remove(_chartTraderPanelRow);

            _chartTraderPanelRow = null;
            _panelAttached = false;
            _chartTraderPanelScrollViewer = null;
            _chartTraderPanelBorder = null;
            _chartTraderGrid = null;
            _chartTraderControl = null;
            _chartGrid = null;
            _chartTab = null;
            _chartWindow = null;

            _connectionStatusText = null;
            _marketStateText = null;
            _lvnStatusText = null;
            _atmSelectorText = null;
            _sessionPnLValueText = null;
            _tradesTodayValueText = null;
            _nearestLvnValueText = null;
            _nearestWallValueText = null;
            _autoExecuteText = null;
            _dryRunText = null;
            _longToggleButton = null;
            _shortToggleButton = null;
            _breakevenButton = null;
            _closeButton = null;
            _lvnDailyButton = null;
            _lvnWeeklyButton = null;
            _lvnMonthlyButton = null;
            _volumeFilterButton = null;
            _radarTargetsButton = null;
            _autoExecuteButton = null;
            _dryRunButton = null;
            _approachTicksTextBox = null;
            _volumeFilterRatioTextBox = null;
        }

        private void UnwireButton(Button button, RoutedEventHandler handler)
        {
            if (button != null)
                button.Click -= handler;
        }

        private void OnLongToggleClick(object sender, RoutedEventArgs e) { _allowLongEntries = !_allowLongEntries; UpdateWpfPanel(); }
        private void OnShortToggleClick(object sender, RoutedEventArgs e) { _allowShortEntries = !_allowShortEntries; UpdateWpfPanel(); }
        private void OnBreakEvenClick(object sender, RoutedEventArgs e) { _pendingBreakevenRequest = true; UpdateWpfPanel(); }
        private void OnCloseClick(object sender, RoutedEventArgs e) { _pendingCloseRequest = true; UpdateWpfPanel(); }
        private void OnLvnDailyToggleClick(object sender, RoutedEventArgs e) { _showDailyLvn = !_showDailyLvn; RefreshAllLvnDrawings(); UpdatePanelCaches(); UpdateWpfPanel(); }
        private void OnLvnWeeklyToggleClick(object sender, RoutedEventArgs e) { _showWeeklyLvn = !_showWeeklyLvn; RefreshAllLvnDrawings(); UpdatePanelCaches(); UpdateWpfPanel(); }
        private void OnLvnMonthlyToggleClick(object sender, RoutedEventArgs e) { _showMonthlyLvn = !_showMonthlyLvn; RefreshAllLvnDrawings(); UpdatePanelCaches(); UpdateWpfPanel(); }
        private void OnVolumeFilterToggleClick(object sender, RoutedEventArgs e) { VolumeFilterEnabled = !VolumeFilterEnabled; UpdateWpfPanel(); }
        private void OnRadarTargetsToggleClick(object sender, RoutedEventArgs e) { _radarTargetsEnabled = !_radarTargetsEnabled; UpdateWpfPanel(); }
        private void OnAutoExecuteToggleClick(object sender, RoutedEventArgs e) { _autoExecutionEnabled = !_autoExecutionEnabled; UpdateWpfPanel(); }
        private void OnDryRunToggleClick(object sender, RoutedEventArgs e) { DryRunMode = !DryRunMode; UpdateWpfPanel(); }

        private void OnApproachTicksChanged(object sender, TextChangedEventArgs e)
        {
            int value;
            if (int.TryParse(_approachTicksTextBox.Text, out value) && value >= 1 && value <= 30)
                LvnApproachTicks = value;
        }

        private void OnVolumeFilterRatioChanged(object sender, TextChangedEventArgs e)
        {
            double value;
            if (double.TryParse(_volumeFilterRatioTextBox.Text, out value) && value > 0 && value <= 5.0)
                VolumeFilterRatio = value;
        }

        private static T FindVisualParent<T>(DependencyObject child) where T : DependencyObject
        {
            while (child != null)
            {
                if (child is T)
                    return child as T;
                child = VisualTreeHelper.GetParent(child);
            }
            return null;
        }

        private double RoundToTick(double price)
        {
            if (TickSize <= 0)
                return price;
            return Math.Round(price / TickSize, MidpointRounding.AwayFromZero) * TickSize;
        }

        private static SolidColorBrush MakeFrozenBrush(Color color)
        {
            var brush = new SolidColorBrush(color);
            if (brush.CanFreeze && !brush.IsFrozen)
                brush.Freeze();
            return brush;
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1, 30)]
        [Display(Name = "LvnApproachTicks", Order = 0, GroupName = "Entry")]
        public int LvnApproachTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "VolumeFilterEnabled", Order = 1, GroupName = "Entry")]
        public bool VolumeFilterEnabled { get; set; }

        [NinjaScriptProperty]
        [Range(0.1, 5.0)]
        [Display(Name = "VolumeFilterRatio", Order = 2, GroupName = "Entry")]
        public double VolumeFilterRatio { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "DefaultLvnPeriod", Order = 0, GroupName = "LVN Config")]
        public VPProfilePeriod DefaultLvnPeriod { get; set; }

        [NinjaScriptProperty]
        [Range(10, 1000)]
        [Display(Name = "LvnRows", Order = 1, GroupName = "LVN Config")]
        public int LvnRows { get; set; }

        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name = "LvnStrength", Order = 2, GroupName = "LVN Config")]
        public int LvnStrength { get; set; }

        [NinjaScriptProperty]
        [Range(1, 60)]
        [Display(Name = "LvnResolutionMinutes", Order = 3, GroupName = "LVN Config")]
        public int LvnResolutionMinutes { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "StopLossTicks", Order = 0, GroupName = "Exit")]
        public int StopLossTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ScaleOutEnabled", Order = 1, GroupName = "Exit")]
        public bool ScaleOutEnabled { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "ScaleOutTargetTicks", Order = 2, GroupName = "Exit")]
        public int ScaleOutTargetTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "TargetTicks", Order = 3, GroupName = "Exit")]
        public int TargetTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BreakevenEnabled", Order = 4, GroupName = "Exit")]
        public bool BreakevenEnabled { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BreakevenActivationTicks", Order = 5, GroupName = "Exit")]
        public int BreakevenActivationTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BreakevenOffsetTicks", Order = 6, GroupName = "Exit")]
        public int BreakevenOffsetTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "MaxBarsInTrade", Order = 7, GroupName = "Exit")]
        public int MaxBarsInTrade { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "UseRadarTargets", Order = 8, GroupName = "Exit")]
        public bool UseRadarTargets { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "MaxContractsPerTrade", Order = 0, GroupName = "Risk")]
        public int MaxContractsPerTrade { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "MaxTradesPerSession", Order = 1, GroupName = "Risk")]
        public int MaxTradesPerSession { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "DailyLossCapDollars", Order = 2, GroupName = "Risk")]
        public double DailyLossCapDollars { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "MinBarsBetweenEntries", Order = 3, GroupName = "Risk")]
        public int MinBarsBetweenEntries { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BlackoutWindowStart", Order = 4, GroupName = "Risk")]
        public int BlackoutWindowStart { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "BlackoutWindowEnd", Order = 5, GroupName = "Risk")]
        public int BlackoutWindowEnd { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "EnableAutoExecution", Order = 0, GroupName = "Safety")]
        public bool EnableAutoExecution { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "DryRunMode", Order = 1, GroupName = "Safety")]
        public bool DryRunMode { get; set; }

        #endregion
    }
}

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using SharpDX;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using Color = System.Windows.Media.Color;
using SolidColorBrush = System.Windows.Media.SolidColorBrush;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6LiquidityLevels : Indicator
    {
        private const int DepthSlots = 4000;
        private const int ArrayMidpoint = 2000;
        private const int InvalidateIntervalMs = 50;
        private const string PerfLogFileName = "DEEP6LiquidityLevels-perf.log";

        private long[] bidVolumes;
        private long[] askVolumes;
        private double _basePrice;
        private double _tickSize = 0.25;
        private long _currentBidTicks;
        private long _currentAskTicks;
        private long _lastDepthTicks;
        private int _dirtyFlag;
        private int _recentering;
        private long _depthCallbackCount;
        private long _lastRateLogTick;
        private Timer _throttleTimer;
        private Timer _invalidateTimer;

        private volatile LevelSnapshot _renderSnapshot;
        private readonly Dictionary<int, DateTime> _persistence = new Dictionary<int, DateTime>();
        private readonly int[] _persistenceRemovals = new int[DepthSlots];

        private readonly Stopwatch _renderSw = new Stopwatch();
        private readonly double[] _renderTimes = new double[100];
        private int _renderTimeIdx;
        private long _diagCallbacksShown; // cumulative count for diag display
        private int  _firstLevelsLogged; // 0 = not logged yet

        private SharpDX.Direct2D1.SolidColorBrush _dxBidZone;
        private SharpDX.Direct2D1.SolidColorBrush _dxBidLine;
        private SharpDX.Direct2D1.SolidColorBrush _dxAskZone;
        private SharpDX.Direct2D1.SolidColorBrush _dxAskLine;
        private SharpDX.Direct2D1.SolidColorBrush _dxLabelBg;
        private SharpDX.Direct2D1.SolidColorBrush _dxLabelText;
        private SharpDX.Direct2D1.SolidColorBrush _dxStatusText;
        private SharpDX.DirectWrite.TextFormat _fmtLabel;
        private SharpDX.DirectWrite.TextFormat _fmtStatus;

        private sealed class LevelSnapshot
        {
            public bool HasData;
            public bool IsStale;
            public LevelEntry[] BidLevels;
            public LevelEntry[] AskLevels;
            public string StatusText;
        }

        private struct LevelEntry
        {
            public double Price;
            public long Volume;
            public string Label;
        }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 DOM-based liquidity wall detector for real-time support and resistance levels.";
                Name = "DEEP6 Liquidity Levels";
                Calculate = Calculate.OnEachTick;
                IsOverlay = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                IsSuspendedWhileInactive = false;
                DisplayInDataBox = false;
                ScaleJustification = ScaleJustification.Right;

                MaxLevels = 5;
                MinVolumeFloor = 1;   // diagnostic: 1 lot minimum — show anything
                MinPersistenceMs = 0; // diagnostic: no spoof filter — show immediately
                ThrottleIntervalMs = 250;
                ZoneBandTicks = 2;
                BidLevelColor = MakeFrozenBrush(Color.FromRgb(0x00, 0xE0, 0xFF));
                AskLevelColor = MakeFrozenBrush(Color.FromRgb(0xFF, 0x17, 0x44));
            }
            else if (State == State.Configure)
            {
                bidVolumes = new long[DepthSlots];
                askVolumes = new long[DepthSlots];
            }
            else if (State == State.Realtime)
            {
                _tickSize = Instrument != null && Instrument.MasterInstrument != null && Instrument.MasterInstrument.TickSize > 0
                    ? Instrument.MasterInstrument.TickSize
                    : 0.25;

                _lastRateLogTick = unchecked((uint)Environment.TickCount);
                _renderSnapshot = CreateWaitingSnapshot();
                Print("[DEEP6LiquidityLevels] Realtime reached. TickSize=" + _tickSize + " — waiting for Level 2 DOM data from Rithmic");
                _throttleTimer = new Timer(OnThrottleTimer, null, ThrottleIntervalMs, ThrottleIntervalMs);
                _invalidateTimer = new Timer(OnInvalidateTimer, null, InvalidateIntervalMs, InvalidateIntervalMs);
                Interlocked.Exchange(ref _dirtyFlag, 1);
            }
            else if (State == State.Terminated)
            {
                if (_throttleTimer != null)
                {
                    _throttleTimer.Dispose();
                    _throttleTimer = null;
                }

                if (_invalidateTimer != null)
                {
                    _invalidateTimer.Dispose();
                    _invalidateTimer = null;
                }

                DisposeDx();
            }
        }

        protected override void OnBarUpdate()
        {
            if (BarsInProgress != 0)
                return;

            if (CurrentBar < 0)
                return;

            if (Bars != null && Bars.IsFirstBarOfSession && IsFirstTickOfBar)
                ResetSessionState();
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (State != State.Realtime || e == null)
                return;

            if (bidVolumes == null || askVolumes == null)
                return;

            if (e.MarketDataType != MarketDataType.Bid && e.MarketDataType != MarketDataType.Ask)
                return;

            if (_basePrice == 0)
                _basePrice = e.Price;

            int index = (int)((e.Price - _basePrice) / _tickSize) + ArrayMidpoint;
            if (index < 0 || index >= DepthSlots)
            {
                Interlocked.Exchange(ref _recentering, 1);
                return;
            }

            long size = e.Operation == Operation.Remove ? 0L : (long)e.Volume;
            if (e.MarketDataType == MarketDataType.Bid)
                bidVolumes[index] = size;
            else
                askVolumes[index] = size;

            if (e.Position == 0)
            {
                long priceTicks = (long)(e.Price * 10000.0);
                if (e.MarketDataType == MarketDataType.Bid)
                    Interlocked.Exchange(ref _currentBidTicks, priceTicks);
                else
                    Interlocked.Exchange(ref _currentAskTicks, priceTicks);
            }

            Interlocked.Exchange(ref _lastDepthTicks, DateTime.UtcNow.Ticks);
            Interlocked.Exchange(ref _dirtyFlag, 1);
            long cb = Interlocked.Increment(ref _depthCallbackCount);
            if (cb == 1) Print("[DEEP6LiquidityLevels] First DOM event received: price=" + e.Price + " vol=" + e.Volume + " side=" + e.MarketDataType);
        }

        private void OnThrottleTimer(object state)
        {
            try
            {
                if (Interlocked.CompareExchange(ref _recentering, 1, 1) == 1)
                {
                    RecenterArrays();
                    return;
                }

                long lastDepthTicks = Interlocked.Read(ref _lastDepthTicks);

                // If OnMarketDepth has never fired, stay in "waiting" state — do not publish HasData=true
                if (lastDepthTicks == 0)
                {
                    Interlocked.Exchange(ref _dirtyFlag, 1);
                    return;
                }

                bool isStale = DateTime.UtcNow.Ticks - lastDepthTicks > 5L * TimeSpan.TicksPerSecond;

                // Timer reads arrays while OnMarketDepth writes without locking. Individual long reads on x64 are atomic.
                // Transient inconsistency is acceptable for a visual indicator refreshing every 250ms.
                DateTime now = DateTime.UtcNow;
                int maxLevels = MaxLevels;
                long[] topBidVolumes = new long[maxLevels];
                int[] topBidIndexes = new int[maxLevels];
                long[] topAskVolumes = new long[maxLevels];
                int[] topAskIndexes = new int[maxLevels];
                int bidCount = 0;
                int askCount = 0;
                int removalCount = 0;

                for (int index = 0; index < DepthSlots; index++)
                {
                    long bidVolume = bidVolumes[index];
                    long askVolume = askVolumes[index];

                    if (bidVolume == 0 && askVolume == 0)
                    {
                        if (_persistence.ContainsKey(index))
                            _persistenceRemovals[removalCount++] = index;
                        continue;
                    }

                    if (MinPersistenceMs > 0)
                    {
                        DateTime firstSeen;
                        if (!_persistence.TryGetValue(index, out firstSeen))
                        {
                            _persistence[index] = now;
                            continue;
                        }
                        if ((now - firstSeen).TotalMilliseconds < MinPersistenceMs)
                            continue;
                    }

                    if (bidVolume >= MinVolumeFloor)
                        InsertTopLevel(topBidVolumes, topBidIndexes, ref bidCount, bidVolume, index);

                    if (askVolume >= MinVolumeFloor)
                        InsertTopLevel(topAskVolumes, topAskIndexes, ref askCount, askVolume, index);
                }

                for (int i = 0; i < removalCount; i++)
                    _persistence.Remove(_persistenceRemovals[i]);

                LevelSnapshot newSnapshot = new LevelSnapshot
                {
                    HasData = true,
                    IsStale = isStale,
                    BidLevels = BuildEntries(topBidVolumes, topBidIndexes, bidCount),
                    AskLevels = BuildEntries(topAskVolumes, topAskIndexes, askCount),
                    StatusText = isStale ? "NO DATA — Rithmic DOM feed lost" : string.Empty
                };

                _renderSnapshot = newSnapshot;
                Interlocked.Exchange(ref _dirtyFlag, 1);

                // Print first time we find levels
                if (bidCount + askCount > 0 && _firstLevelsLogged == 0)
                {
                    _firstLevelsLogged = 1;
                    Print("[DEEP6LiquidityLevels] First levels found: bid=" + bidCount + " ask=" + askCount + " floor=" + MinVolumeFloor + " persist=" + MinPersistenceMs + "ms");
                }

                LogDomRate();
            }
            catch { }
        }

        private void OnInvalidateTimer(object state)
        {
            if (Interlocked.Exchange(ref _dirtyFlag, 0) != 1) return;
            try
            {
                if (ChartControl != null)
                    ChartControl.Dispatcher.BeginInvoke(new Action(delegate
                    {
                        if (ChartControl != null) ChartControl.InvalidateVisual();
                    }));
            }
            catch { }
        }

        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;
            var rt = RenderTarget;
            var factory = NinjaTrader.Core.Globals.DirectWriteFactory;

            var bidRgb = ((SolidColorBrush)BidLevelColor).Color;
            _dxBidZone = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(bidRgb.R / 255f, bidRgb.G / 255f, bidRgb.B / 255f, 0.25f));
            _dxBidLine = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(bidRgb.R / 255f, bidRgb.G / 255f, bidRgb.B / 255f, 0.85f));

            var askRgb = ((SolidColorBrush)AskLevelColor).Color;
            _dxAskZone = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(askRgb.R / 255f, askRgb.G / 255f, askRgb.B / 255f, 0.25f));
            _dxAskLine = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(askRgb.R / 255f, askRgb.G / 255f, askRgb.B / 255f, 0.85f));

            _dxLabelBg = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(0.08f, 0.09f, 0.10f, 0.75f));
            _dxLabelText = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1f, 1f, 1f, 0.90f));
            _dxStatusText = new SharpDX.Direct2D1.SolidColorBrush(rt, new SharpDX.Color4(1f, 0.75f, 0f, 0.90f));

            _fmtLabel = new SharpDX.DirectWrite.TextFormat(factory, "Consolas", SharpDX.DirectWrite.FontWeight.Normal, SharpDX.DirectWrite.FontStyle.Normal, SharpDX.DirectWrite.FontStretch.Normal, 9f);
            _fmtStatus = new SharpDX.DirectWrite.TextFormat(factory, "Consolas", SharpDX.DirectWrite.FontWeight.Bold, SharpDX.DirectWrite.FontStyle.Normal, SharpDX.DirectWrite.FontStretch.Normal, 10f);
        }

        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (IsInHitTest) return;
            if (RenderTarget == null || chartControl == null) return;
            if (_dxBidLine == null) return;
            // Historical scroll guard removed — status text must always show

            _renderSw.Restart();

            var snap = _renderSnapshot;
            var priorAntialias = RenderTarget.AntialiasMode;
            RenderTarget.AntialiasMode = SharpDX.Direct2D1.AntialiasMode.Aliased;

            float panelX = (float)ChartPanel.X;
            float panelW = (float)ChartPanel.W;
            double minValue = chartScale.MinValue;
            double maxValue = chartScale.MaxValue;

            // Always draw diagnostic HUD regardless of data state
            long totalCb = Interlocked.Read(ref _depthCallbackCount) + _diagCallbacksShown;
            int bidLvls  = (snap != null && snap.BidLevels != null) ? snap.BidLevels.Length : 0;
            int askLvls  = (snap != null && snap.AskLevels != null) ? snap.AskLevels.Length : 0;
            string diagState = (snap == null || !snap.HasData) ? "WAITING" : snap.IsStale ? "STALE" : "LIVE";
            DrawDiag($"DOM:{diagState} cb={totalCb} B:{bidLvls} A:{askLvls} floor={MinVolumeFloor}");

            if (snap == null || !snap.HasData)
            {
                DrawStatus("DEEP6 Levels: waiting for Rithmic Level 2...");
                goto done;
            }

            if (snap.IsStale)
            {
                DrawStatus("DEEP6 Levels: Rithmic DOM feed lost");
                goto done;
            }

            float lastBidLabelY = float.MinValue;
            for (int i = 0; i < snap.BidLevels.Length; i++)
            {
                LevelEntry lvl = snap.BidLevels[i];
                if (lvl.Volume <= 0 || lvl.Price < minValue || lvl.Price > maxValue)
                    continue;

                float y = chartScale.GetYByValue(lvl.Price);
                float bandH = Math.Abs(chartScale.GetYByValue(lvl.Price - ZoneBandTicks * _tickSize) - y);
                if (bandH < 2f) bandH = 2f;

                RenderTarget.FillRectangle(new RectangleF(panelX, y - bandH / 2f, panelW, bandH), _dxBidZone);
                RenderTarget.DrawLine(new Vector2(panelX, y), new Vector2(panelX + panelW, y), _dxBidLine, 1.5f);

                float labelY = y - 10f;
                if (lastBidLabelY != float.MinValue && labelY - lastBidLabelY < 12f)
                    labelY = lastBidLabelY + 12f;
                lastBidLabelY = labelY;

                var labelRect = new RectangleF(panelX + panelW - 52f, labelY, 50f, 12f);
                RenderTarget.FillRectangle(labelRect, _dxLabelBg);
                RenderTarget.DrawText(lvl.Label, _fmtLabel, labelRect, _dxLabelText);
            }

            float lastAskLabelY = float.MinValue;
            for (int i = 0; i < snap.AskLevels.Length; i++)
            {
                LevelEntry lvl = snap.AskLevels[i];
                if (lvl.Volume <= 0 || lvl.Price < minValue || lvl.Price > maxValue)
                    continue;

                float y = chartScale.GetYByValue(lvl.Price);
                float bandH = Math.Abs(chartScale.GetYByValue(lvl.Price - ZoneBandTicks * _tickSize) - y);
                if (bandH < 2f) bandH = 2f;

                RenderTarget.FillRectangle(new RectangleF(panelX, y - bandH / 2f, panelW, bandH), _dxAskZone);
                RenderTarget.DrawLine(new Vector2(panelX, y), new Vector2(panelX + panelW, y), _dxAskLine, 1.5f);

                float labelY = y - 10f;
                if (lastAskLabelY != float.MinValue && labelY - lastAskLabelY < 12f)
                    labelY = lastAskLabelY + 12f;
                lastAskLabelY = labelY;

                var labelRect = new RectangleF(panelX + 2f, labelY, 50f, 12f);
                RenderTarget.FillRectangle(labelRect, _dxLabelBg);
                RenderTarget.DrawText(lvl.Label, _fmtLabel, labelRect, _dxLabelText);
            }

        done:
            RenderTarget.AntialiasMode = priorAntialias;

            _renderSw.Stop();
            _renderTimes[_renderTimeIdx++ % 100] = _renderSw.Elapsed.TotalMilliseconds;
            if (_renderTimeIdx % 100 == 0)
            {
                double avg = 0;
                for (int i = 0; i < 100; i++)
                    avg += _renderTimes[i];
                avg /= 100;

                string msg = $"[DEEP6LiquidityLevels] Avg render: {avg:F2}ms";
                Print(msg);
                TryAppendPerfLog(msg);
                if (avg > 12.0)
                    Print("[DEEP6LiquidityLevels] WARNING: render time > 12ms — possible performance issue");
            }
        }

        private void DrawStatus(string text)
        {
            if (_fmtStatus == null || _dxStatusText == null || _dxLabelBg == null)
                return;

            float y = (float)ChartPanel.Y + (float)ChartPanel.H - 30f;
            var rect = new RectangleF((float)ChartPanel.X + 8f, y, 500f, 18f);
            RenderTarget.FillRectangle(rect, _dxLabelBg);
            RenderTarget.DrawText(text, _fmtStatus, rect, _dxStatusText);
        }

        private void DrawDiag(string text)
        {
            if (_fmtStatus == null || _dxStatusText == null || _dxLabelBg == null)
                return;

            float y = (float)ChartPanel.Y + (float)ChartPanel.H - 52f; // above the status line
            var rect = new RectangleF((float)ChartPanel.X + 8f, y, 500f, 18f);
            RenderTarget.FillRectangle(rect, _dxLabelBg);
            RenderTarget.DrawText(text, _fmtStatus, rect, _dxStatusText);
        }

        private void ResetSessionState()
        {
            _basePrice = 0;
            if (bidVolumes != null)
                Array.Clear(bidVolumes, 0, bidVolumes.Length);
            if (askVolumes != null)
                Array.Clear(askVolumes, 0, askVolumes.Length);
            _persistence.Clear();
            _renderSnapshot = CreateWaitingSnapshot();
            Interlocked.Exchange(ref _dirtyFlag, 1);
        }

        private LevelSnapshot CreateWaitingSnapshot()
        {
            return new LevelSnapshot
            {
                HasData = false,
                IsStale = false,
                BidLevels = Array.Empty<LevelEntry>(),
                AskLevels = Array.Empty<LevelEntry>(),
                StatusText = "Waiting for Rithmic DOM data..."
            };
        }

        private void RecenterArrays()
        {
            double currentPrice = GetCurrentReferencePrice();
            if (currentPrice > 0)
                _basePrice = currentPrice;

            Array.Clear(bidVolumes, 0, DepthSlots);
            Array.Clear(askVolumes, 0, DepthSlots);
            _persistence.Clear();
            Interlocked.Exchange(ref _recentering, 0);
            Interlocked.Exchange(ref _dirtyFlag, 1);
        }

        private double GetCurrentReferencePrice()
        {
            long bidTicks = Interlocked.Read(ref _currentBidTicks);
            long askTicks = Interlocked.Read(ref _currentAskTicks);

            if (bidTicks > 0 && askTicks > 0)
                return ((bidTicks + askTicks) * 0.5) / 10000.0;
            if (askTicks > 0)
                return askTicks / 10000.0;
            if (bidTicks > 0)
                return bidTicks / 10000.0;

            return _basePrice;
        }

        private void InsertTopLevel(long[] topVolumes, int[] topIndexes, ref int count, long volume, int index)
        {
            int limit = topVolumes.Length;
            int insertAt = count;

            while (insertAt > 0 && volume > topVolumes[insertAt - 1])
                insertAt--;

            if (insertAt >= limit)
                return;

            int moveCount = Math.Min(count, limit - 1);
            for (int i = moveCount; i > insertAt; i--)
            {
                topVolumes[i] = topVolumes[i - 1];
                topIndexes[i] = topIndexes[i - 1];
            }

            topVolumes[insertAt] = volume;
            topIndexes[insertAt] = index;
            if (count < limit)
                count++;
        }

        private LevelEntry[] BuildEntries(long[] topVolumes, int[] topIndexes, int count)
        {
            LevelEntry[] entries = new LevelEntry[count];
            for (int i = 0; i < count; i++)
            {
                entries[i] = new LevelEntry
                {
                    Price = _basePrice + (topIndexes[i] - ArrayMidpoint) * _tickSize,
                    Volume = topVolumes[i],
                    Label = FormatVolumeLabel(topVolumes[i])
                };
            }
            return entries;
        }

        private string FormatVolumeLabel(long volume)
        {
            if (volume < 1000)
                return volume.ToString();

            return (volume / 1000.0).ToString("F1") + "K";
        }

        private void LogDomRate()
        {
            long nowTick = unchecked((uint)Environment.TickCount);
            long elapsed10s = nowTick - _lastRateLogTick;
            if (elapsed10s < 10000)
                return;

            long count = Interlocked.Exchange(ref _depthCallbackCount, 0);
            long rate = count * 1000 / Math.Max(elapsed10s, 1);
            string msg = $"[DEEP6LiquidityLevels] DOM callbacks/sec: {rate}";
            Print(msg);
            TryAppendPerfLog(msg);
            _lastRateLogTick = nowTick;
        }

        private void TryAppendPerfLog(string msg)
        {
            try
            {
                File.AppendAllText(Path.Combine(Path.GetTempPath(), PerfLogFileName), msg + Environment.NewLine);
            }
            catch { }
        }

        private void DisposeDx()
        {
            SafeDispose(ref _dxBidZone); SafeDispose(ref _dxBidLine);
            SafeDispose(ref _dxAskZone); SafeDispose(ref _dxAskLine);
            SafeDispose(ref _dxLabelBg); SafeDispose(ref _dxLabelText); SafeDispose(ref _dxStatusText);
            if (_fmtLabel != null) { _fmtLabel.Dispose(); _fmtLabel = null; }
            if (_fmtStatus != null) { _fmtStatus.Dispose(); _fmtStatus = null; }
        }

        private static void SafeDispose<T>(ref T resource) where T : SharpDX.DisposeBase
        {
            if (resource != null && !resource.IsDisposed) resource.Dispose();
            resource = null;
        }

        private static SolidColorBrush MakeFrozenBrush(Color color)
        {
            var brush = new SolidColorBrush(color);
            if (brush.CanFreeze)
                brush.Freeze();
            return brush;
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1, 10)]
        [Display(Name = "MaxLevels", GroupName = "DEEP6 Liquidity Levels", Order = 1)]
        public int MaxLevels { get; set; }

        [NinjaScriptProperty]
        [Range(0, 5000)]
        [Display(Name = "MinVolumeFloor", GroupName = "DEEP6 Liquidity Levels", Order = 2)]
        public int MinVolumeFloor { get; set; }

        [NinjaScriptProperty]
        [Range(0, 5000)]
        [Display(Name = "MinPersistenceMs", GroupName = "DEEP6 Liquidity Levels", Order = 3)]
        public int MinPersistenceMs { get; set; }

        [NinjaScriptProperty]
        [Range(50, 2000)]
        [Display(Name = "ThrottleIntervalMs", GroupName = "DEEP6 Liquidity Levels", Order = 4)]
        public int ThrottleIntervalMs { get; set; }

        [NinjaScriptProperty]
        [Range(0, 10)]
        [Display(Name = "ZoneBandTicks", GroupName = "DEEP6 Liquidity Levels", Order = 5)]
        public int ZoneBandTicks { get; set; }

        [XmlIgnore]
        [NinjaScriptProperty]
        [Display(Name = "BidLevelColor", GroupName = "DEEP6 Liquidity Levels", Order = 6)]
        public Brush BidLevelColor { get; set; }

        [Browsable(false)]
        public string BidLevelColorSerializable
        {
            get { return Serialize.BrushToString(BidLevelColor); }
            set { BidLevelColor = Serialize.StringToBrush(value); }
        }

        [XmlIgnore]
        [NinjaScriptProperty]
        [Display(Name = "AskLevelColor", GroupName = "DEEP6 Liquidity Levels", Order = 7)]
        public Brush AskLevelColor { get; set; }

        [Browsable(false)]
        public string AskLevelColorSerializable
        {
            get { return Serialize.BrushToString(AskLevelColor); }
            set { AskLevelColor = Serialize.StringToBrush(value); }
        }

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DEEP6LiquidityLevels[] cacheDEEP6LiquidityLevels;
        public DEEP6.DEEP6LiquidityLevels DEEP6LiquidityLevels(int maxLevels, int minVolumeFloor, int minPersistenceMs, int throttleIntervalMs, int zoneBandTicks)
        {
            return DEEP6LiquidityLevels(Input, maxLevels, minVolumeFloor, minPersistenceMs, throttleIntervalMs, zoneBandTicks);
        }
        public DEEP6.DEEP6LiquidityLevels DEEP6LiquidityLevels(ISeries<double> input, int maxLevels, int minVolumeFloor, int minPersistenceMs, int throttleIntervalMs, int zoneBandTicks)
        {
            if (cacheDEEP6LiquidityLevels != null)
                foreach (var i in cacheDEEP6LiquidityLevels)
                    if (i.MaxLevels == maxLevels && i.MinVolumeFloor == minVolumeFloor && i.MinPersistenceMs == minPersistenceMs && i.ThrottleIntervalMs == throttleIntervalMs && i.ZoneBandTicks == zoneBandTicks && i.EqualsInput(input))
                        return i;
            return CacheIndicator<DEEP6.DEEP6LiquidityLevels>(new DEEP6.DEEP6LiquidityLevels(){ MaxLevels = maxLevels, MinVolumeFloor = minVolumeFloor, MinPersistenceMs = minPersistenceMs, ThrottleIntervalMs = throttleIntervalMs, ZoneBandTicks = zoneBandTicks }, input, ref cacheDEEP6LiquidityLevels);
        }
    }
}
#endregion

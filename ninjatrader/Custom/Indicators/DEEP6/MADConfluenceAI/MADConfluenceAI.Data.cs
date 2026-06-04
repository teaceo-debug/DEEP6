// MADConfluenceAI.Data.cs — Data pipeline: OnMarketData tick handler, OnMarketDepth DOM handler
// Core data types (MADCell, MADFootprintBar, MADSignalResult, MADSignalDirection)
// are defined at namespace level below, BEFORE the partial class.
using System;
using System.Collections.Generic;
using NinjaTrader.Cbi;
using NinjaTrader.Data;

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    // ── Signal direction enum ───────────────────────────────────────────
    public enum MADSignalDirection { Long, Short, Neutral }

    // ── Signal result DTO ───────────────────────────────────────────────
    public sealed class MADSignalResult
    {
        public string SignalId;
        public MADSignalDirection Direction;
        public double Strength;   // 0.0 - 1.0
        public string Detail;
        public double Price;      // price level where signal fired
    }

    // ── Per-price-level footprint cell ──────────────────────────────────
    public sealed class MADCell
    {
        public long BidVol;       // sell-aggressor volume (trade price <= best bid)
        public long AskVol;       // buy-aggressor volume (trade price >= best ask)
        public long NeutralVol;   // between-spread prints

        public long Delta => AskVol - BidVol;
        public long TotalVol => AskVol + BidVol + NeutralVol;
        public double ImbalanceRatio
        {
            get
            {
                if (BidVol == 0 && AskVol == 0) return 1.0;
                if (BidVol == 0) return double.MaxValue;
                if (AskVol == 0) return double.MaxValue;
                return AskVol > BidVol ? (double)AskVol / BidVol : (double)BidVol / AskVol;
            }
        }
    }

    // ── Footprint bar (tick-by-tick accumulation) ───────────────────────
    public sealed class MADFootprintBar
    {
        public int BarIndex;
        public double Open, High, Low, Close;
        public DateTime BarTime;
        public SortedDictionary<double, MADCell> Levels = new SortedDictionary<double, MADCell>();
        public long TotalVol;
        public long BarDelta;
        public long Cvd;
        public double PocPrice;
        public double VahPrice;
        public double ValPrice;
        public long MaxDelta;
        public long MinDelta;
        public long RunningDelta;
        public int TradeCount;
        public double BarRange;

        /// <summary>
        /// Add a single trade to this bar.
        /// aggressor: 1=buy (at ask), 2=sell (at bid), 0=neutral
        /// </summary>
        public void AddTrade(double price, long size, int aggressor)
        {
            MADCell cell;
            if (!Levels.TryGetValue(price, out cell)) { cell = new MADCell(); Levels[price] = cell; }
            if (aggressor == 1) { cell.AskVol += size; RunningDelta += size; }
            else if (aggressor == 2) { cell.BidVol += size; RunningDelta -= size; }
            else { cell.NeutralVol += size; }
            if (RunningDelta > MaxDelta) MaxDelta = RunningDelta;
            if (RunningDelta < MinDelta) MinDelta = RunningDelta;
            if (Open == 0) Open = price;
            if (price > High) High = price;
            if (Low == 0 || price < Low) Low = price;
            Close = price;
            TotalVol += size;
            TradeCount++;
        }

        /// <summary>
        /// Finalize bar after last trade: compute BarDelta, POC, CVD, BarRange.
        /// </summary>
        public void Finalize(long priorCvd = 0)
        {
            if (TotalVol == 0 && Levels.Count > 0)
            {
                TotalVol = 0;
                foreach (var lv in Levels.Values) TotalVol += lv.TotalVol;
            }
            BarDelta = 0;
            foreach (var lv in Levels.Values) BarDelta += lv.Delta;
            double bestPx = 0; long bestVol = -1;
            foreach (var kv in Levels)
            {
                long v = kv.Value.TotalVol;
                if (v > bestVol) { bestVol = v; bestPx = kv.Key; }
            }
            PocPrice = bestPx;
            BarRange = High - Low;
            Cvd = priorCvd + BarDelta;
        }

        /// <summary>
        /// Quality scalar: how much of the intrabar delta extreme survived to bar close.
        /// 1.0 = all delta preserved (clean trend); 0.0 = fully reversed.
        /// </summary>
        public double DeltaQualityScalar()
        {
            long extreme = Math.Abs(MaxDelta) > Math.Abs(MinDelta) ? Math.Abs(MaxDelta) : Math.Abs(MinDelta);
            if (extreme == 0) return 0.0;
            double q = (double)Math.Abs(BarDelta) / extreme;
            return Math.Min(1.15, Math.Max(0.0, q));
        }
    }

    // ── Delta pipeline: ring-buffer CVD/close tracker for divergence & acceleration ──
    public sealed class MADDeltaPipeline
    {
        private const int BufferSize = 500;
        private readonly long[] _cvdBuffer = new long[BufferSize];
        private readonly double[] _closeBuffer = new double[BufferSize];
        private int _head;
        private int _count;

        public int Count => _count;

        public void OnBarFinalized(MADFootprintBar bar)
        {
            _cvdBuffer[_head] = bar.Cvd;
            _closeBuffer[_head] = bar.Close;
            _head = (_head + 1) % BufferSize;
            if (_count < BufferSize) _count++;
        }

        public long GetCvd(int barsAgo)
        {
            if (barsAgo < 0 || barsAgo >= _count) return 0;
            int idx = ((_head - 1 - barsAgo) % BufferSize + BufferSize) % BufferSize;
            return _cvdBuffer[idx];
        }

        public double GetClose(int barsAgo)
        {
            if (barsAgo < 0 || barsAgo >= _count) return 0;
            int idx = ((_head - 1 - barsAgo) % BufferSize + BufferSize) % BufferSize;
            return _closeBuffer[idx];
        }

        public double CheckDivergence(int lookback)
        {
            if (_count < lookback || lookback < 2) return 0;
            double priceNow = GetClose(0);
            double priceThen = GetClose(lookback - 1);
            long cvdNow = GetCvd(0);
            long cvdThen = GetCvd(lookback - 1);

            bool priceDown = priceNow < priceThen;
            bool priceUp = priceNow > priceThen;
            bool cvdUp = cvdNow > cvdThen;
            bool cvdDown = cvdNow < cvdThen;

            if (priceDown && cvdUp) return 1.0;
            if (priceUp && cvdDown) return -1.0;
            return 0;
        }

        public double DeltaRoC
        {
            get
            {
                if (_count < 2) return 0;
                int n = Math.Min(10, _count);
                return (double)(GetCvd(0) - GetCvd(n - 1)) / n;
            }
        }

        public double DeltaAccel
        {
            get
            {
                int half = _count / 2;
                int n = Math.Min(10, half);
                if (n < 2) return 0;
                double rocNow = (double)(GetCvd(0) - GetCvd(n - 1)) / n;
                double rocPrev = (double)(GetCvd(n) - GetCvd(n + n - 1)) / n;
                return rocNow - rocPrev;
            }
        }

        public void Reset()
        {
            _head = 0;
            _count = 0;
            Array.Clear(_cvdBuffer, 0, BufferSize);
            Array.Clear(_closeBuffer, 0, BufferSize);
        }
    }

    public partial class MADConfluenceAI : Indicator
    {
        // Thread-safe locks (data thread vs chart thread)
        private readonly object _dataLock = new object();
        private readonly object _domLock = new object();

        // BBO tracking (updated on data thread)
        private double _bestBid = 0;
        private double _bestAsk = 0;

        // DOM availability flag (false until first OnMarketDepth call)
        private bool _isDomAvailable = false;

        // DOM state arrays (pre-allocated, 50 levels per side)
        private double[] _domBidPrices = new double[50];
        private long[] _domBidVolumes = new long[50];
        private double[] _domAskPrices = new double[50];
        private long[] _domAskVolumes = new long[50];
        private int _domBidCount = 0;
        private int _domAskCount = 0;
        // Refill tracking for iceberg detection
        private Dictionary<double, int> _refillCounts = new Dictionary<double, int>();
        private Dictionary<double, DateTime> _refillTimestamps = new Dictionary<double, DateTime>();

        // ── Data pipeline state ─────────────────────────────────────────
        private List<MADFootprintBar> _bars = new List<MADFootprintBar>();
        private int _processedBars = 0;
        private bool _isWarmedUp = false;
        private MADFootprintBar _currentBar;
        private MADDeltaPipeline _deltaPipeline = new MADDeltaPipeline();

        /// <summary>
        /// Initialize data pipeline structures. Called from State.DataLoaded.
        /// </summary>
        private void InitDataPipeline()
        {
            _bars = new List<MADFootprintBar>();
            _processedBars = 0;
            _isWarmedUp = false;
            _currentBar = null;
            _deltaPipeline = new MADDeltaPipeline();
            _refillCounts = new Dictionary<double, int>();
            _refillTimestamps = new Dictionary<double, DateTime>();
            _domBidCount = 0;
            _domAskCount = 0;
            Array.Clear(_domBidPrices, 0, 50);
            Array.Clear(_domBidVolumes, 0, 50);
            Array.Clear(_domAskPrices, 0, 50);
            Array.Clear(_domAskVolumes, 0, 50);
        }

        /// <summary>
        /// Finalize the current bar's footprint data (delta, POC, CVD) and add to bar list.
        /// Called at the start of each new bar in OnBarUpdate.
        /// </summary>
        private void FinalizeCurrentBar()
        {
            if (_currentBar != null)
            {
                long priorCvd = _bars.Count > 0 ? _bars[_bars.Count - 1].Cvd : 0;
                _currentBar.Finalize(priorCvd);
                _bars.Add(_currentBar);
                _deltaPipeline.OnBarFinalized(_currentBar);
            }
            _currentBar = new MADFootprintBar { BarIndex = CurrentBar, BarTime = Time[0] };
        }

        internal List<double> GetLiquidityWalls(double threshold)
        {
            if (!_isDomAvailable) return new List<double>();
            long totalVol = 0; int count = 0;
            for (int i = 0; i < _domBidCount; i++) { if (_domBidVolumes[i] > 0) { totalVol += _domBidVolumes[i]; count++; } }
            for (int i = 0; i < _domAskCount; i++) { if (_domAskVolumes[i] > 0) { totalVol += _domAskVolumes[i]; count++; } }
            if (count == 0) return new List<double>();
            double avg = (double)totalVol / count;
            var walls = new List<double>();
            for (int i = 0; i < _domBidCount; i++) if (_domBidVolumes[i] > threshold * avg) walls.Add(_domBidPrices[i]);
            for (int i = 0; i < _domAskCount; i++) if (_domAskVolumes[i] > threshold * avg) walls.Add(_domAskPrices[i]);
            return walls;
        }

        internal double GetDomImbalance()
        {
            if (!_isDomAvailable) return 1.0;
            long bidSum = 0, askSum = 0;
            int top = Math.Min(10, Math.Min(_domBidCount, _domAskCount));
            for (int i = 0; i < top; i++) { bidSum += _domBidVolumes[i]; askSum += _domAskVolumes[i]; }
            if (askSum == 0) return 1.0;
            return (double)bidSum / askSum;
        }

        internal int GetRefillCount(double price)
        {
            if (!_isDomAvailable) return 0;
            int c; return _refillCounts.TryGetValue(price, out c) ? c : 0;
        }

        protected override void OnMarketData(MarketDataEventArgs marketDataUpdate)
        {
            lock (_dataLock)
            {
                if (marketDataUpdate.MarketDataType == MarketDataType.Bid)
                { _bestBid = marketDataUpdate.Price; return; }
                if (marketDataUpdate.MarketDataType == MarketDataType.Ask)
                { _bestAsk = marketDataUpdate.Price; return; }
                if (marketDataUpdate.MarketDataType != MarketDataType.Last) return;
                if (_currentBar == null) return;
                double price = marketDataUpdate.Price;
                long volume = marketDataUpdate.Volume;
                int aggressor = 0;
                if (_bestAsk > 0 && price >= _bestAsk) aggressor = 1;
                else if (_bestBid > 0 && price <= _bestBid) aggressor = 2;
                _currentBar.AddTrade(price, volume, aggressor);
            }
        }

        protected override void OnMarketDepth(MarketDepthEventArgs marketDepthUpdate)
        {
            lock (_domLock)
            {
                _isDomAvailable = true;
                int pos = marketDepthUpdate.Position;
                if (pos < 0 || pos >= 50) return;
                if (marketDepthUpdate.MarketDataType == MarketDataType.Bid)
                {
                    long priorVol = _domBidVolumes[pos];
                    _domBidPrices[pos] = marketDepthUpdate.Price;
                    if (marketDepthUpdate.Operation == Operation.Remove)
                    {
                        _domBidVolumes[pos] = 0;
                        _refillTimestamps[marketDepthUpdate.Price] = DateTime.UtcNow;
                    }
                    else
                    {
                        _domBidVolumes[pos] = marketDepthUpdate.Volume;
                        if (priorVol == 0 && marketDepthUpdate.Volume > 0)
                        {
                            DateTime ts;
                            if (_refillTimestamps.TryGetValue(marketDepthUpdate.Price, out ts) && (DateTime.UtcNow - ts).TotalSeconds <= 30)
                            {
                                if (!_refillCounts.ContainsKey(marketDepthUpdate.Price)) _refillCounts[marketDepthUpdate.Price] = 0;
                                _refillCounts[marketDepthUpdate.Price]++;
                            }
                        }
                    }
                    if (pos >= _domBidCount) _domBidCount = pos + 1;
                }
                else if (marketDepthUpdate.MarketDataType == MarketDataType.Ask)
                {
                    long priorVol = _domAskVolumes[pos];
                    _domAskPrices[pos] = marketDepthUpdate.Price;
                    if (marketDepthUpdate.Operation == Operation.Remove)
                    {
                        _domAskVolumes[pos] = 0;
                        _refillTimestamps[marketDepthUpdate.Price] = DateTime.UtcNow;
                    }
                    else
                    {
                        _domAskVolumes[pos] = marketDepthUpdate.Volume;
                        if (priorVol == 0 && marketDepthUpdate.Volume > 0)
                        {
                            DateTime ts;
                            if (_refillTimestamps.TryGetValue(marketDepthUpdate.Price, out ts) && (DateTime.UtcNow - ts).TotalSeconds <= 30)
                            {
                                if (!_refillCounts.ContainsKey(marketDepthUpdate.Price)) _refillCounts[marketDepthUpdate.Price] = 0;
                                _refillCounts[marketDepthUpdate.Price]++;
                            }
                        }
                    }
                    if (pos >= _domAskCount) _domAskCount = pos + 1;
                }
            }
        }
    }
}

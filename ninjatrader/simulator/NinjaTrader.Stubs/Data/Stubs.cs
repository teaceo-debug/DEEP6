// NinjaTrader.Data stubs — Bars, ISeries, MarketDataEventArgs, MarketDepthEventArgs.

namespace NinjaTrader.Data
{
    public enum MarketDataType { Last, Bid, Ask, DailyHigh, DailyLow, DailyVolume, Opening, SettlementPrice }
    public enum BarsPeriodType { Minute, Day, Tick, Volume, Range, Second, Week, Month, Year }
    public enum Operation { Add, Update, Remove }

    public interface ISeries<T>
    {
        T this[int barsAgo] { get; }
        int Count { get; }
    }

    /// <summary>Simple list-backed data series (price, volume, time).</summary>
    public class DataSeries<T> : ISeries<T>
    {
        private readonly System.Collections.Generic.List<T> _data = new();
        private int _currentBar = -1;

        internal void SetCurrentBar(int idx) { _currentBar = idx; }
        internal void Add(T value) { _data.Add(value); }
        internal void Set(int idx, T value) { _data[idx] = value; }

        public T this[int barsAgo]
        {
            get
            {
                int idx = _currentBar - barsAgo;
                if (idx < 0 || idx >= _data.Count) return default;
                return _data[idx];
            }
        }

        public int Count => _data.Count;

        internal T GetDirect(int idx) => (idx >= 0 && idx < _data.Count) ? _data[idx] : default;
    }

    public class Bars
    {
        private readonly DataSeries<double> _open = new();
        private readonly DataSeries<double> _high = new();
        private readonly DataSeries<double> _low = new();
        private readonly DataSeries<double> _close = new();
        private readonly DataSeries<long> _volume = new();
        private readonly DataSeries<System.DateTime> _time = new();

        public int Count => _close.Count;

        public double GetOpen(int idx) => _open.GetDirect(idx);
        public double GetHigh(int idx) => _high.GetDirect(idx);
        public double GetLow(int idx) => _low.GetDirect(idx);
        public double GetClose(int idx) => _close.GetDirect(idx);
        public long GetVolume(int idx) => _volume.GetDirect(idx);
        public System.DateTime GetTime(int idx) => _time.GetDirect(idx);

        /// <summary>Add a bar to the series (used by the lifecycle simulator).</summary>
        public void AddBar(double open, double high, double low, double close, long volume, System.DateTime time)
        {
            _open.Add(open);
            _high.Add(high);
            _low.Add(low);
            _close.Add(close);
            _volume.Add(volume);
            _time.Add(time);
        }

        internal void SetCurrentBar(int idx)
        {
            _open.SetCurrentBar(idx);
            _high.SetCurrentBar(idx);
            _low.SetCurrentBar(idx);
            _close.SetCurrentBar(idx);
            _volume.SetCurrentBar(idx);
            _time.SetCurrentBar(idx);
        }

        public BarsPeriod BarsPeriod { get; set; } = new BarsPeriod();
    }

    public class BarsPeriod
    {
        public BarsPeriodType BarsPeriodType { get; set; } = BarsPeriodType.Minute;
        public int Value { get; set; } = 1;
    }

    public class MarketDataEventArgs : System.EventArgs
    {
        public MarketDataType MarketDataType { get; set; }
        public double Price { get; set; }
        public long Volume { get; set; }
        public System.DateTime Time { get; set; }
    }

    public class MarketDepthEventArgs : System.EventArgs
    {
        public MarketDataType MarketDataType { get; set; }
        public Operation Operation { get; set; }
        public int Position { get; set; }
        public double Price { get; set; }
        public long Volume { get; set; }
        public System.DateTime Time { get; set; }
    }
}

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Delta
{
    public enum DeltaDivergenceBias
    {
        Neutral = 0,
        Bullish = 1,
        Bearish = -1,
    }

    public readonly struct DeltaDivergenceBar
    {
        public DeltaDivergenceBar(double high, double low, double close, long delta)
        {
            High = high;
            Low = low;
            Close = close;
            Delta = delta;
        }

        public double High { get; }
        public double Low { get; }
        public double Close { get; }
        public long Delta { get; }
        public double Range => High - Low;
    }

    public sealed class MtfDeltaDivergenceConfig
    {
        public int PivotLookback = 20;
        public int MinBars = 20;
        public double TickSize = 0.25;
        public int MinPriceBreakTicks = 4;
        public long MinDeltaImprovement = 250;
        public double CloseConfirmationRatio = 0.50;
    }

    public sealed class MtfDeltaDivergenceEngine
    {
        private readonly MtfDeltaDivergenceConfig _config;
        private readonly List<DeltaDivergenceBar> _bars = new List<DeltaDivergenceBar>();

        public MtfDeltaDivergenceEngine() : this(new MtfDeltaDivergenceConfig())
        {
        }

        public MtfDeltaDivergenceEngine(MtfDeltaDivergenceConfig config)
        {
            _config = config ?? new MtfDeltaDivergenceConfig();
        }

        public DeltaDivergenceBias CurrentBias { get; private set; }

        public int Count => _bars.Count;

        public void Reset()
        {
            _bars.Clear();
            CurrentBias = DeltaDivergenceBias.Neutral;
        }

        public DeltaDivergenceBias AddBar(DeltaDivergenceBar bar)
        {
            _bars.Add(bar);
            CurrentBias = EvaluateLatest();
            return CurrentBias;
        }

        public DeltaDivergenceBias EvaluateLatest()
        {
            if (_bars.Count < System.Math.Max(2, _config.MinBars))
                return DeltaDivergenceBias.Neutral;

            DeltaDivergenceBar current = _bars[_bars.Count - 1];
            int lookback = System.Math.Min(_config.PivotLookback, _bars.Count - 1);
            int start = (_bars.Count - 1) - lookback;
            double priceBreakDistance = _config.MinPriceBreakTicks * _config.TickSize;

            int priorLowIndex = start;
            int priorHighIndex = start;

            for (int i = start + 1; i < _bars.Count - 1; i++)
            {
                if (_bars[i].Low < _bars[priorLowIndex].Low)
                    priorLowIndex = i;
                if (_bars[i].High > _bars[priorHighIndex].High)
                    priorHighIndex = i;
            }

            DeltaDivergenceBar priorLow = _bars[priorLowIndex];
            DeltaDivergenceBar priorHigh = _bars[priorHighIndex];

            bool bullish = current.Low <= priorLow.Low - priceBreakDistance
                && current.Delta >= priorLow.Delta + _config.MinDeltaImprovement
                && HasBullishCloseConfirmation(current);

            bool bearish = current.High >= priorHigh.High + priceBreakDistance
                && current.Delta <= priorHigh.Delta - _config.MinDeltaImprovement
                && HasBearishCloseConfirmation(current);

            if (bullish == bearish)
                return DeltaDivergenceBias.Neutral;

            return bullish ? DeltaDivergenceBias.Bullish : DeltaDivergenceBias.Bearish;
        }

        public static DeltaDivergenceBias ToCompositeBias(IReadOnlyList<DeltaDivergenceBias> biases, int minAgreement)
        {
            if (biases == null || biases.Count == 0)
                return DeltaDivergenceBias.Neutral;

            int bulls = 0;
            int bears = 0;
            for (int i = 0; i < biases.Count; i++)
            {
                if (biases[i] == DeltaDivergenceBias.Bullish)
                    bulls++;
                else if (biases[i] == DeltaDivergenceBias.Bearish)
                    bears++;
            }

            if (bulls >= minAgreement && bulls > bears)
                return DeltaDivergenceBias.Bullish;
            if (bears >= minAgreement && bears > bulls)
                return DeltaDivergenceBias.Bearish;
            return DeltaDivergenceBias.Neutral;
        }

        private bool HasBullishCloseConfirmation(DeltaDivergenceBar bar)
        {
            double range = System.Math.Max(bar.Range, _config.TickSize);
            double threshold = bar.Low + (range * _config.CloseConfirmationRatio);
            return bar.Close >= threshold;
        }

        private bool HasBearishCloseConfirmation(DeltaDivergenceBar bar)
        {
            double range = System.Math.Max(bar.Range, _config.TickSize);
            double threshold = bar.High - (range * _config.CloseConfirmationRatio);
            return bar.Close <= threshold;
        }
    }
}

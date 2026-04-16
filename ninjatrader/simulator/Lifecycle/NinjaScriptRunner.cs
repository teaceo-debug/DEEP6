// NinjaScriptRunner — drives a NinjaScript indicator or strategy through the
// NT8 lifecycle state machine with historical bar replay.
//
// State machine: SetDefaults → Configure → DataLoaded → Historical (replay bars) → Realtime → Terminated
//
// Usage:
//   var runner = new NinjaScriptRunner();
//   runner.LoadBars(bars);                 // OHLCV + time
//   runner.Run<DEEP6Footprint>();          // instantiate + lifecycle
//   var log = runner.Script.PrintLog;      // inspect Print() output

using System;
using System.Collections.Generic;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;

namespace NinjaScriptSim.Lifecycle
{
    /// <summary>
    /// Represents one historical bar for replay.
    /// </summary>
    public class BarData
    {
        public double Open, High, Low, Close;
        public long Volume;
        public DateTime Time;

        /// <summary>Optional: trades within this bar for tick-level replay.</summary>
        public List<TickData> Ticks { get; set; }
    }

    /// <summary>
    /// Represents one tick (trade) for tick-level replay within a bar.
    /// </summary>
    public class TickData
    {
        public double Price;
        public long Size;
        public int Aggressor; // 1=buy (hit ask), 2=sell (hit bid), 0=neutral
        public DateTime Time;
    }

    /// <summary>
    /// Represents one DOM depth update for L2 replay.
    /// </summary>
    public class DepthUpdate
    {
        public MarketDataType Side; // Bid or Ask
        public Operation Operation;
        public int Position;
        public double Price;
        public long Volume;
        public DateTime Time;
    }

    /// <summary>
    /// Drives a NinjaScript through the full NT8 lifecycle with bar replay.
    /// </summary>
    public class NinjaScriptRunner
    {
        private readonly List<BarData> _bars = new();
        private readonly List<DepthUpdate> _depthUpdates = new();

        public NinjaScriptBase Script { get; private set; }
        public FillSimulatorResult FillResult { get; private set; }
        public List<string> Errors { get; } = new();
        public List<string> Warnings { get; } = new();
        public bool Succeeded { get; private set; }

        /// <summary>Simulated instrument settings.</summary>
        public string InstrumentName { get; set; } = "NQ 06-26";
        public double TickSize { get; set; } = 0.25;
        public double PointValue { get; set; } = 20.0;

        /// <summary>Account settings (for strategy simulation).</summary>
        public string AccountName { get; set; } = "Sim101";
        public double AccountBalance { get; set; } = 50000.0;

        /// <summary>Load bars for replay.</summary>
        public void LoadBars(IEnumerable<BarData> bars)
        {
            _bars.Clear();
            _bars.AddRange(bars);
        }

        /// <summary>Load DOM depth updates for L2 replay (optional).</summary>
        public void LoadDepthUpdates(IEnumerable<DepthUpdate> updates)
        {
            _depthUpdates.Clear();
            _depthUpdates.AddRange(updates);
        }

        /// <summary>
        /// Instantiate and run a NinjaScript through the full lifecycle.
        /// </summary>
        public T Run<T>() where T : NinjaScriptBase, new()
        {
            Errors.Clear();
            Warnings.Clear();
            Succeeded = false;

            var script = new T();
            Script = script;

            // Set up instrument
            script.Instrument = new Instrument
            {
                FullName = InstrumentName,
                MasterInstrument = new MasterInstrument
                {
                    Name = InstrumentName.Split(' ')[0],
                    TickSize = TickSize,
                    PointValue = PointValue,
                }
            };

            // Set up account + fill engine (strategies only)
            FillSimulator fillEngine = null;
            if (script is StrategyBase strategy)
            {
                strategy.Account = new Account { Name = AccountName };
                strategy.Position = new Position();
                fillEngine = new FillSimulator(new FillConfig { TickSize = TickSize, TickValue = PointValue * TickSize });
                strategy.FillEngine = fillEngine;
            }

            // Build Bars data structure
            var bars = new Bars();
            foreach (var b in _bars)
                bars.AddBar(b.Open, b.High, b.Low, b.Close, b.Volume, b.Time);

            script.Bars = bars;

            // Create barsAgo-indexed data series
            var closeSeries = new DataSeries<double>();
            var openSeries = new DataSeries<double>();
            var highSeries = new DataSeries<double>();
            var lowSeries = new DataSeries<double>();
            var volumeSeries = new DataSeries<long>();
            var timeSeries = new DataSeries<DateTime>();

            foreach (var b in _bars)
            {
                closeSeries.Add(b.Close);
                openSeries.Add(b.Open);
                highSeries.Add(b.High);
                lowSeries.Add(b.Low);
                volumeSeries.Add(b.Volume);
                timeSeries.Add(b.Time);
            }

            script.Close = closeSeries;
            script.Open = openSeries;
            script.High = highSeries;
            script.Low = lowSeries;
            script.Volume = volumeSeries;
            script.Time = timeSeries;
            script.Input = closeSeries;

            // ── State Machine ──

            // 1. SetDefaults
            try
            {
                script.InvokeStateChange(State.SetDefaults);
            }
            catch (Exception ex)
            {
                Errors.Add($"[SetDefaults] {ex.GetType().Name}: {ex.Message}");
                return script;
            }

            // 2. Configure
            try
            {
                script.InvokeStateChange(State.Configure);
            }
            catch (Exception ex)
            {
                Errors.Add($"[Configure] {ex.GetType().Name}: {ex.Message}");
                return script;
            }

            // 3. DataLoaded
            try
            {
                script.InvokeStateChange(State.DataLoaded);
            }
            catch (Exception ex)
            {
                Errors.Add($"[DataLoaded] {ex.GetType().Name}: {ex.Message}");
                return script;
            }

            // 4. Historical — replay all bars
            script.InvokeStateChange(State.Historical);

            int depthIdx = 0;
            for (int i = 0; i < _bars.Count; i++)
            {
                script.CurrentBar = i;
                script.BarsInProgress = 0;
                script.IsFirstTickOfBar = true;
                bars.SetCurrentBar(i);
                closeSeries.SetCurrentBar(i);
                openSeries.SetCurrentBar(i);
                highSeries.SetCurrentBar(i);
                lowSeries.SetCurrentBar(i);
                volumeSeries.SetCurrentBar(i);
                timeSeries.SetCurrentBar(i);

                // Feed ticks if available (for OnMarketData)
                if (_bars[i].Ticks != null)
                {
                    // Send bid/ask updates to establish BBO
                    if (i > 0)
                    {
                        script.InvokeMarketData(new MarketDataEventArgs
                        {
                            MarketDataType = MarketDataType.Bid,
                            Price = _bars[i].Low + TickSize,
                            Volume = 10,
                            Time = _bars[i].Time,
                        });
                        script.InvokeMarketData(new MarketDataEventArgs
                        {
                            MarketDataType = MarketDataType.Ask,
                            Price = _bars[i].High - TickSize,
                            Volume = 10,
                            Time = _bars[i].Time,
                        });
                    }

                    foreach (var tick in _bars[i].Ticks)
                    {
                        script.InvokeMarketData(new MarketDataEventArgs
                        {
                            MarketDataType = MarketDataType.Last,
                            Price = tick.Price,
                            Volume = tick.Size,
                            Time = tick.Time,
                        });
                    }
                }

                // Feed depth updates that fall within this bar's time window
                DateTime barEnd = _bars[i].Time;
                DateTime barStart = i > 0 ? _bars[i - 1].Time : barEnd.AddMinutes(-1);
                while (depthIdx < _depthUpdates.Count && _depthUpdates[depthIdx].Time <= barEnd)
                {
                    var du = _depthUpdates[depthIdx];
                    script.InvokeMarketDepth(new MarketDepthEventArgs
                    {
                        MarketDataType = du.Side,
                        Operation = du.Operation,
                        Position = du.Position,
                        Price = du.Price,
                        Volume = du.Volume,
                        Time = du.Time,
                    });
                    depthIdx++;
                }

                // Process fill engine BEFORE OnBarUpdate (fills from prior bar's entry)
                if (fillEngine != null)
                {
                    fillEngine.ProcessBar(i, _bars[i].Open, _bars[i].High, _bars[i].Low, _bars[i].Close, _bars[i].Time);
                    // Sync position state back to strategy
                    if (script is StrategyBase strat)
                    {
                        if (!fillEngine.InTrade)
                        {
                            strat.Position.MarketPosition = MarketPosition.Flat;
                            strat.Position.Quantity = 0;
                        }
                    }
                }

                // Fire OnBarUpdate
                try
                {
                    script.InvokeBarUpdate();
                }
                catch (Exception ex)
                {
                    Errors.Add($"[OnBarUpdate bar={i}] {ex.GetType().Name}: {ex.Message}");
                    // Continue processing remaining bars
                }
            }

            // Session end — close any open position
            if (fillEngine != null && _bars.Count > 0)
            {
                var lastBar = _bars[_bars.Count - 1];
                fillEngine.SessionEnd(_bars.Count - 1, lastBar.Close, lastBar.Time);
                fillEngine.Finalize();
                FillResult = fillEngine.Result;
            }

            // 5. Terminated
            try
            {
                script.InvokeStateChange(State.Terminated);
            }
            catch (Exception ex)
            {
                Warnings.Add($"[Terminated] {ex.GetType().Name}: {ex.Message}");
            }

            Succeeded = Errors.Count == 0;
            return script;
        }

        /// <summary>
        /// Run lifecycle without bar replay — just validates the state machine (SetDefaults → Configure → DataLoaded → Terminated).
        /// Useful for compile-check: if this doesn't throw, the NinjaScript code is structurally valid.
        /// </summary>
        public T ValidateOnly<T>() where T : NinjaScriptBase, new()
        {
            // Same as Run but with minimal bars
            LoadBars(new[]
            {
                new BarData { Open = 19000, High = 19010, Low = 18990, Close = 19005, Volume = 1000, Time = DateTime.Now.AddMinutes(-3) },
                new BarData { Open = 19005, High = 19015, Low = 18995, Close = 19010, Volume = 1200, Time = DateTime.Now.AddMinutes(-2) },
                new BarData { Open = 19010, High = 19020, Low = 19000, Close = 19015, Volume = 800, Time = DateTime.Now.AddMinutes(-1) },
            });
            return Run<T>();
        }
    }
}

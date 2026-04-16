// FillSimulator: Realistic order fill engine for the NinjaScript simulator.
//
// Tracks entries, exits, stops, targets, and computes P&L per trade.
// Wired into StrategyBase so that EnterLong/ExitLong/AtmStrategyCreate
// route through the fill engine instead of being no-ops.
//
// Fill logic mirrors NT8's backtest behavior:
//   - Market orders fill at next bar's open + slippage
//   - Stop orders trigger when price crosses stop level
//   - Target orders trigger when price crosses target level
//   - ATM brackets create stop + target simultaneously
//   - Scale-out partial exits supported

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace NinjaScriptSim.Lifecycle
{
    public enum TradeDirection { Long = 1, Short = -1 }
    public enum TradeExitReason { Target, StopLoss, Breakeven, Trail, OpposingSignal, MaxBars, SessionEnd, ManualExit, ScaleOut }

    public class SimTrade
    {
        public int EntryBar { get; set; }
        public int ExitBar { get; set; }
        public DateTime EntryTime { get; set; }
        public DateTime ExitTime { get; set; }
        public double EntryPrice { get; set; }
        public double ExitPrice { get; set; }
        public TradeDirection Direction { get; set; }
        public int Quantity { get; set; }
        public double PnlTicks { get; set; }
        public double PnlDollars { get; set; }
        public TradeExitReason ExitReason { get; set; }
        public string SignalName { get; set; }
        public string AtmTemplate { get; set; }
        public double Mfe { get; set; }  // max favorable excursion (ticks)
        public double Mae { get; set; }  // max adverse excursion (ticks)
        public int DurationBars => ExitBar - EntryBar;
    }

    public class FillConfig
    {
        public double SlippageTicks { get; set; } = 1.0;
        public double CommissionPerSide { get; set; } = 2.09;  // NQ round-trip ~$4.18
        public double TickSize { get; set; } = 0.25;
        public double TickValue { get; set; } = 5.0;   // NQ: $5 per tick

        // ATM template defaults (used when actual template isn't configured)
        public int DefaultStopTicks { get; set; } = 20;
        public int DefaultTargetTicks { get; set; } = 32;
        public int DefaultScaleOutTicks { get; set; } = 16;
        public double DefaultScaleOutPercent { get; set; } = 0.5;
        public bool ScaleOutEnabled { get; set; } = true;

        // Breakeven
        public bool BreakevenEnabled { get; set; } = true;
        public int BreakevenActivationTicks { get; set; } = 10;
        public int BreakevenOffsetTicks { get; set; } = 2;

        // Max bars in trade
        public int MaxBarsInTrade { get; set; } = 60;
    }

    public class FillSimulatorResult
    {
        public List<SimTrade> Trades { get; } = new();
        public double NetPnl => Trades.Sum(t => t.PnlDollars);
        public double GrossProfit => Trades.Where(t => t.PnlDollars > 0).Sum(t => t.PnlDollars);
        public double GrossLoss => Trades.Where(t => t.PnlDollars < 0).Sum(t => t.PnlDollars);
        public int Winners => Trades.Count(t => t.PnlDollars > 0);
        public int Losers => Trades.Count(t => t.PnlDollars < 0);
        public int Scratches => Trades.Count(t => t.PnlDollars == 0);
        public double WinRate => Trades.Count > 0 ? (double)Winners / Trades.Count * 100 : 0;
        public double ProfitFactor => GrossLoss != 0 ? System.Math.Abs(GrossProfit / GrossLoss) : GrossProfit > 0 ? 999 : 0;
        public double AvgWin => Winners > 0 ? GrossProfit / Winners : 0;
        public double AvgLoss => Losers > 0 ? GrossLoss / Losers : 0;
        public double MaxDrawdown { get; set; }
        public double SharpeRatio { get; set; }
        public double TotalCommissions { get; set; }

        // Equity curve (cumulative P&L after each trade)
        public List<double> EquityCurve { get; } = new();
        public List<double> DrawdownCurve { get; } = new();
    }

    /// <summary>
    /// Processes pending orders against bar data, computes fills, tracks positions.
    /// Called by the NinjaScriptRunner after each OnBarUpdate.
    /// </summary>
    public class FillSimulator
    {
        private readonly FillConfig _config;

        // Active position state
        private bool _inTrade;
        private TradeDirection _direction;
        private double _entryPrice;
        private int _entryBar;
        private DateTime _entryTime;
        private int _quantity;
        private string _signalName;
        private string _atmTemplate;
        private double _stopPrice;
        private double _targetPrice;
        private double _scaleOutPrice;
        private bool _scaleOutDone;
        private double _mfe, _mae;
        private bool _breakevenArmed;

        // Pending entry (fills at next bar open)
        private bool _pendingEntry;
        private NinjaTrader.Cbi.OrderAction _pendingAction;
        private string _pendingSignal;
        private string _pendingAtm;
        private int _pendingQty;

        public FillSimulatorResult Result { get; } = new();
        public bool InTrade => _inTrade;
        public FillConfig Config => _config;

        public FillSimulator(FillConfig config = null)
        {
            _config = config ?? new FillConfig();
        }

        /// <summary>
        /// Called by StrategyBase.AtmStrategyCreate — queues a market entry
        /// that fills at the next bar's open.
        /// </summary>
        public void QueueEntry(NinjaTrader.Cbi.OrderAction action, string signalName, string atmTemplate, int quantity = 2)
        {
            _pendingEntry = true;
            _pendingAction = action;
            _pendingSignal = signalName;
            _pendingAtm = atmTemplate;
            _pendingQty = quantity;
        }

        /// <summary>
        /// Called by StrategyBase.AtmStrategyClose — immediate market exit.
        /// </summary>
        public void ForceExit(int currentBar, double currentPrice, DateTime time)
        {
            if (!_inTrade) return;
            CloseTrade(currentBar, currentPrice, time, TradeExitReason.ManualExit);
        }

        /// <summary>
        /// Process fills for the current bar. Called by NinjaScriptRunner
        /// BEFORE OnBarUpdate so that position state is correct.
        /// </summary>
        public void ProcessBar(int barIndex, double open, double high, double low, double close, DateTime time)
        {
            // 1. Fill pending entry at this bar's open
            if (_pendingEntry)
            {
                _pendingEntry = false;
                bool isLong = _pendingAction == NinjaTrader.Cbi.OrderAction.Buy;
                double slippage = _config.SlippageTicks * _config.TickSize;
                double fillPrice = isLong ? open + slippage : open - slippage;

                _inTrade = true;
                _direction = isLong ? TradeDirection.Long : TradeDirection.Short;
                _entryPrice = fillPrice;
                _entryBar = barIndex;
                _entryTime = time;
                _quantity = _pendingQty;
                _signalName = _pendingSignal;
                _atmTemplate = _pendingAtm;
                _mfe = 0;
                _mae = 0;
                _breakevenArmed = false;
                _scaleOutDone = false;

                // Set stop and target from config
                int dir = (int)_direction;
                _stopPrice = _entryPrice - dir * _config.DefaultStopTicks * _config.TickSize;
                _targetPrice = _entryPrice + dir * _config.DefaultTargetTicks * _config.TickSize;
                _scaleOutPrice = _config.ScaleOutEnabled
                    ? _entryPrice + dir * _config.DefaultScaleOutTicks * _config.TickSize
                    : 0;
            }

            if (!_inTrade) return;

            // 2. Update MFE/MAE
            int d = (int)_direction;
            double mfeTicks = d == 1
                ? (high - _entryPrice) / _config.TickSize
                : (_entryPrice - low) / _config.TickSize;
            double maeTicks = d == 1
                ? (_entryPrice - low) / _config.TickSize
                : (high - _entryPrice) / _config.TickSize;
            if (mfeTicks > _mfe) _mfe = mfeTicks;
            if (maeTicks > _mae) _mae = maeTicks;

            // 3. Breakeven stop
            if (_config.BreakevenEnabled && !_breakevenArmed && _mfe >= _config.BreakevenActivationTicks)
            {
                _breakevenArmed = true;
                double beStop = _entryPrice + d * _config.BreakevenOffsetTicks * _config.TickSize;
                // Only tighten, never loosen
                if (d == 1 && beStop > _stopPrice) _stopPrice = beStop;
                else if (d == -1 && beStop < _stopPrice) _stopPrice = beStop;
            }

            // 4. Check exits in priority order

            // 4a. Stop loss
            bool stopHit = d == 1 ? low <= _stopPrice : high >= _stopPrice;
            if (stopHit)
            {
                double fillPrice = _stopPrice + (d == 1 ? -1 : 1) * _config.SlippageTicks * _config.TickSize;
                CloseTrade(barIndex, fillPrice, time,
                    _breakevenArmed ? TradeExitReason.Breakeven : TradeExitReason.StopLoss);
                return;
            }

            // 4b. Scale-out partial
            if (_config.ScaleOutEnabled && !_scaleOutDone && _scaleOutPrice != 0)
            {
                bool scaleHit = d == 1 ? high >= _scaleOutPrice : low <= _scaleOutPrice;
                if (scaleHit)
                {
                    // Partial exit
                    int scaleQty = (int)System.Math.Max(1, _quantity * _config.DefaultScaleOutPercent);
                    double scalePnlTicks = (_scaleOutPrice - _entryPrice) / _config.TickSize * d;
                    double scalePnlDollars = scalePnlTicks * _config.TickValue * scaleQty;
                    double commission = _config.CommissionPerSide * 2 * scaleQty;

                    Result.Trades.Add(new SimTrade
                    {
                        EntryBar = _entryBar, ExitBar = barIndex,
                        EntryTime = _entryTime, ExitTime = time,
                        EntryPrice = _entryPrice, ExitPrice = _scaleOutPrice,
                        Direction = _direction, Quantity = scaleQty,
                        PnlTicks = scalePnlTicks,
                        PnlDollars = scalePnlDollars - commission,
                        ExitReason = TradeExitReason.ScaleOut,
                        SignalName = _signalName, AtmTemplate = _atmTemplate,
                        Mfe = _mfe, Mae = _mae,
                    });
                    Result.TotalCommissions += commission;

                    _quantity -= scaleQty;
                    _scaleOutDone = true;
                }
            }

            // 4c. Full target
            bool targetHit = d == 1 ? high >= _targetPrice : low <= _targetPrice;
            if (targetHit)
            {
                CloseTrade(barIndex, _targetPrice, time, TradeExitReason.Target);
                return;
            }

            // 4d. Max bars
            if (barIndex - _entryBar >= _config.MaxBarsInTrade)
            {
                CloseTrade(barIndex, close, time, TradeExitReason.MaxBars);
                return;
            }
        }

        /// <summary>Force-close at session end.</summary>
        public void SessionEnd(int barIndex, double closePrice, DateTime time)
        {
            if (_inTrade)
                CloseTrade(barIndex, closePrice, time, TradeExitReason.SessionEnd);
        }

        private void CloseTrade(int barIndex, double exitPrice, DateTime time, TradeExitReason reason)
        {
            int d = (int)_direction;
            double slippage = reason == TradeExitReason.Target || reason == TradeExitReason.ScaleOut
                ? 0 // Target fills at exact price
                : _config.SlippageTicks * _config.TickSize;
            double fillPrice = exitPrice - d * slippage;

            double pnlTicks = (fillPrice - _entryPrice) / _config.TickSize * d;
            double pnlDollars = pnlTicks * _config.TickValue * _quantity;
            double commission = _config.CommissionPerSide * 2 * _quantity;

            Result.Trades.Add(new SimTrade
            {
                EntryBar = _entryBar, ExitBar = barIndex,
                EntryTime = _entryTime, ExitTime = time,
                EntryPrice = _entryPrice, ExitPrice = fillPrice,
                Direction = _direction, Quantity = _quantity,
                PnlTicks = pnlTicks,
                PnlDollars = pnlDollars - commission,
                ExitReason = reason,
                SignalName = _signalName, AtmTemplate = _atmTemplate,
                Mfe = _mfe, Mae = _mae,
            });
            Result.TotalCommissions += commission;

            _inTrade = false;
            _quantity = 0;
        }

        /// <summary>Finalize results — compute equity curve, drawdown, Sharpe.</summary>
        public void Finalize()
        {
            double equity = 0, peak = 0, maxDd = 0;
            Result.EquityCurve.Clear();
            Result.DrawdownCurve.Clear();

            foreach (var t in Result.Trades)
            {
                equity += t.PnlDollars;
                Result.EquityCurve.Add(equity);
                if (equity > peak) peak = equity;
                double dd = peak - equity;
                Result.DrawdownCurve.Add(dd);
                if (dd > maxDd) maxDd = dd;
            }

            Result.MaxDrawdown = maxDd;

            // Sharpe
            if (Result.Trades.Count >= 2)
            {
                var pnls = Result.Trades.Select(t => t.PnlDollars).ToArray();
                double mean = pnls.Average();
                double variance = pnls.Sum(p => (p - mean) * (p - mean)) / (pnls.Length - 1);
                double stdDev = System.Math.Sqrt(variance);
                Result.SharpeRatio = stdDev > 0 ? mean / stdDev * System.Math.Sqrt(252) : 0;
            }
        }

        // ── Reporting ──

        public static void PrintReport(FillSimulatorResult result)
        {
            Console.WriteLine($"  ── Trade Summary ──");
            Console.WriteLine($"  Total trades:    {result.Trades.Count}");
            Console.WriteLine($"  Winners:         {result.Winners} ({result.WinRate:F1}%)");
            Console.WriteLine($"  Losers:          {result.Losers}");
            Console.WriteLine($"  Scratches:       {result.Scratches}");
            Console.WriteLine($"  Net P&L:         ${result.NetPnl:F2}");
            Console.WriteLine($"  Gross profit:    ${result.GrossProfit:F2}");
            Console.WriteLine($"  Gross loss:      ${result.GrossLoss:F2}");
            Console.WriteLine($"  Profit factor:   {result.ProfitFactor:F2}");
            Console.WriteLine($"  Avg win:         ${result.AvgWin:F2}");
            Console.WriteLine($"  Avg loss:        ${result.AvgLoss:F2}");
            Console.WriteLine($"  Max drawdown:    ${result.MaxDrawdown:F2}");
            Console.WriteLine($"  Sharpe ratio:    {result.SharpeRatio:F3}");
            Console.WriteLine($"  Commissions:     ${result.TotalCommissions:F2}");

            if (result.Trades.Count > 0)
            {
                Console.WriteLine();
                Console.WriteLine("  ── Exit Breakdown ──");
                var byExit = result.Trades.GroupBy(t => t.ExitReason)
                    .OrderByDescending(g => g.Count());
                foreach (var g in byExit)
                {
                    double pnl = g.Sum(t => t.PnlDollars);
                    Console.WriteLine($"    {g.Key,-16} {g.Count(),4} trades  ${pnl:F2}");
                }

                Console.WriteLine();
                Console.WriteLine("  ── Last 10 Trades ──");
                Console.WriteLine("  {0,4} {1,10} {2,10} {3,8} {4,10} {5,8} {6,14}",
                    "Bar", "Entry", "Exit", "Dir", "PnL", "Ticks", "Reason");
                foreach (var t in result.Trades.TakeLast(10))
                {
                    Console.WriteLine("  {0,4} {1,10:F2} {2,10:F2} {3,8} {4,10:F2} {5,8:F1} {6,14}",
                        t.EntryBar, t.EntryPrice, t.ExitPrice,
                        t.Direction == TradeDirection.Long ? "LONG" : "SHORT",
                        t.PnlDollars, t.PnlTicks, t.ExitReason);
                }
            }
        }

        public static void ExportCsv(FillSimulatorResult result, string outputPath)
        {
            using var writer = new StreamWriter(outputPath);
            writer.WriteLine("EntryBar,ExitBar,EntryTime,ExitTime,EntryPrice,ExitPrice,Direction,Qty,PnlTicks,PnlDollars,ExitReason,Signal,MFE,MAE,Duration");
            foreach (var t in result.Trades)
            {
                writer.WriteLine(string.Format(CultureInfo.InvariantCulture,
                    "{0},{1},{2},{3},{4:F2},{5:F2},{6},{7},{8:F1},{9:F2},{10},{11},{12:F1},{13:F1},{14}",
                    t.EntryBar, t.ExitBar,
                    t.EntryTime.ToString("yyyy-MM-dd HH:mm:ss"),
                    t.ExitTime.ToString("yyyy-MM-dd HH:mm:ss"),
                    t.EntryPrice, t.ExitPrice,
                    t.Direction == TradeDirection.Long ? "LONG" : "SHORT",
                    t.Quantity, t.PnlTicks, t.PnlDollars, t.ExitReason,
                    t.SignalName, t.Mfe, t.Mae, t.DurationBars));
            }
        }

        /// <summary>Export equity curve as HTML chart.</summary>
        public static void ExportEquityChart(FillSimulatorResult result, string outputPath)
        {
            var sb = new System.Text.StringBuilder();
            sb.AppendLine("<!DOCTYPE html><html><head><meta charset='UTF-8'>");
            sb.AppendLine("<title>DEEP6 Equity Curve</title>");
            sb.AppendLine("<script src='https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js'></script>");
            sb.AppendLine("<style>* { margin:0; padding:0; box-sizing:border-box; } body { background:#0a0a0a; color:#f5f5f5; font-family:'Inter',sans-serif; }");
            sb.AppendLine("#header { padding:16px 24px; border-bottom:1px solid #1f1f1f; } h1 { font-size:16px; color:#e0e0e0; }");
            sb.AppendLine(".stat { display:inline-block; margin-right:24px; font-size:12px; } .stat b { color:#00ff88; }");
            sb.AppendLine(".stat.loss b { color:#ff2e63; } #chart { width:100%; height:400px; } #dd { width:100%; height:200px; }</style>");
            sb.AppendLine("</head><body>");
            sb.AppendLine("<div id='header'><h1>DEEP6 Equity Curve</h1>");
            sb.AppendLine($"<span class='stat'>Trades: <b>{result.Trades.Count}</b></span>");
            sb.AppendLine($"<span class='stat'>Net P&L: <b>${result.NetPnl:F2}</b></span>");
            sb.AppendLine($"<span class='stat'>Win Rate: <b>{result.WinRate:F1}%</b></span>");
            sb.AppendLine($"<span class='stat'>PF: <b>{result.ProfitFactor:F2}</b></span>");
            sb.AppendLine($"<span class='stat loss'>Max DD: <b>${result.MaxDrawdown:F2}</b></span>");
            sb.AppendLine($"<span class='stat'>Sharpe: <b>{result.SharpeRatio:F3}</b></span>");
            sb.AppendLine("</div><div id='chart'></div><div id='dd'></div><script>");

            // Equity data
            sb.AppendLine("const eq = [");
            for (int i = 0; i < result.EquityCurve.Count; i++)
            {
                int bar = result.Trades[i].ExitBar;
                sb.AppendLine(string.Format(CultureInfo.InvariantCulture,
                    "  {{time:{0},value:{1:F2}}},", bar, result.EquityCurve[i]));
            }
            sb.AppendLine("];");

            // Drawdown data
            sb.AppendLine("const dd = [");
            for (int i = 0; i < result.DrawdownCurve.Count; i++)
            {
                int bar = result.Trades[i].ExitBar;
                sb.AppendLine(string.Format(CultureInfo.InvariantCulture,
                    "  {{time:{0},value:{1:F2}}},", bar, -result.DrawdownCurve[i]));
            }
            sb.AppendLine("];");

            sb.AppendLine(@"
const c1 = LightweightCharts.createChart(document.getElementById('chart'), {
  width: window.innerWidth, height: 400,
  layout: { background:{color:'#0a0a0a'}, textColor:'#8a8a8a' },
  grid: { vertLines:{color:'#111'}, horzLines:{color:'#111'} },
  rightPriceScale: { borderColor:'#1f1f1f' }, timeScale: { borderColor:'#1f1f1f' },
});
const eqLine = c1.addLineSeries({ color:'#00ff88', lineWidth:2 });
eqLine.setData(eq);
const c2 = LightweightCharts.createChart(document.getElementById('dd'), {
  width: window.innerWidth, height: 200,
  layout: { background:{color:'#0a0a0a'}, textColor:'#8a8a8a' },
  grid: { vertLines:{color:'#111'}, horzLines:{color:'#111'} },
  rightPriceScale: { borderColor:'#1f1f1f' }, timeScale: { borderColor:'#1f1f1f' },
});
const ddArea = c2.addAreaSeries({ topColor:'rgba(255,46,99,0.4)', bottomColor:'rgba(255,46,99,0.0)',
  lineColor:'#ff2e63', lineWidth:1 });
ddArea.setData(dd);
window.addEventListener('resize', () => { c1.applyOptions({width:window.innerWidth}); c2.applyOptions({width:window.innerWidth}); });
");
            sb.AppendLine("</script></body></html>");
            File.WriteAllText(outputPath, sb.ToString());
        }
    }
}

// NinjaScriptBase — the root base class all NinjaScript types inherit from.
// Provides State, CurrentBar, BarsInProgress, Print, etc.

using System;
using System.Collections.Generic;
using NinjaTrader.Cbi;
using NinjaTrader.Data;

namespace NinjaTrader.NinjaScript
{
    public enum State
    {
        SetDefaults,
        Configure,
        Active,
        DataLoaded,
        Historical,
        Transition,
        Realtime,
        Terminated,
        Finalized
    }

    public enum Calculate { OnBarClose, OnEachTick, OnPriceChange }
    public enum MaximumBarsLookBack { TwoHundredFiftySix, Infinite }
    public enum ScaleJustification { Right, Left, Overlay }

    // Attribute used by NT8's property grid to identify NinjaScript properties
    [AttributeUsage(AttributeTargets.Property)]
    public class NinjaScriptPropertyAttribute : Attribute { }

    public abstract class NinjaScriptBase
    {
        // ── State machine ──
        public State State { get; set; }

        // ── Bar context ──
        public int CurrentBar { get; set; } = -1;
        public int BarsInProgress { get; set; }
        public bool IsFirstTickOfBar { get; set; } = true;

        // ── Instrument / tick ──
        public Instrument Instrument { get; set; } = new Instrument();
        public double TickSize => Instrument?.MasterInstrument?.TickSize ?? 0.25;

        // ── Data series (populated by simulator) ──
        public Bars Bars { get; set; } = new Bars();
        public ISeries<double> Input { get; set; }

        // barsAgo-indexed price series (set by simulator before each OnBarUpdate)
        public ISeries<double> Close { get; set; }
        public ISeries<double> Open { get; set; }
        public ISeries<double> High { get; set; }
        public ISeries<double> Low { get; set; }
        public ISeries<long> Volume { get; set; }
        public ISeries<DateTime> Time { get; set; }

        // ── Rendering (indicators) ──
        public SharpDX.Direct2D1.RenderTarget RenderTarget { get; set; }
        public NinjaTrader.Gui.Chart.ChartControl ChartControl { get; set; }
        public NinjaTrader.Gui.Chart.ChartScale ChartScale { get; set; }
        public NinjaTrader.Gui.Chart.ChartPanel ChartPanel { get; set; }

        // ── Output ──
        private readonly List<string> _printLog = new();
        public IReadOnlyList<string> PrintLog => _printLog;

        public void Print(string message)
        {
            _printLog.Add(message);
        }

        public void Print(object obj)
        {
            _printLog.Add(obj?.ToString() ?? "null");
        }

        public void ClearOutputWindow() { _printLog.Clear(); }

        // ── Lifecycle hooks (virtual — overridden by indicators/strategies) ──
        protected virtual void OnStateChange() { }
        protected virtual void OnBarUpdate() { }
        protected virtual void OnMarketData(MarketDataEventArgs e) { }
        protected virtual void OnMarketDepth(MarketDepthEventArgs e) { }
        public virtual void OnRenderTargetChanged() { }
        public virtual void OnRender(SharpDX.Direct2D1.RenderTarget target, NinjaTrader.Gui.Chart.ChartScale scale) { }

        // ── Internal lifecycle driver (called by simulator) ──
        internal void InvokeStateChange(State newState)
        {
            State = newState;
            OnStateChange();
        }

        internal void InvokeBarUpdate()
        {
            OnBarUpdate();
        }

        internal void InvokeMarketData(MarketDataEventArgs e)
        {
            OnMarketData(e);
        }

        internal void InvokeMarketDepth(MarketDepthEventArgs e)
        {
            OnMarketDepth(e);
        }

        // ── Helpers used by NinjaScript code ──
        public bool EqualsInput(ISeries<double> input) => input == Input;
    }
}

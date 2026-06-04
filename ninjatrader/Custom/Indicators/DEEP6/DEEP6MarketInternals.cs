// DEEP6MarketInternals: NT8 indicator that subscribes to NYSE market internals
// (^TICK, ^ADD, ^VOLD) and forwards them to connected clients via DataBridge.
//
// Install: copy to %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\
// Usage: add this indicator to any NQ chart. It streams internals data as NDJSON
// on port 9200 (configurable) for consumption by the Python copilot adapter.
//
// This indicator is invisible (no plots, no chart rendering). It only bridges data.
//
// NDJSON format:
//   {"type":"internals","tick":234,"add":1456,"vold":2.1,"ts_ms":1715000000000}
//
// Note: if DataBridgeIndicator is also on the chart, set different BridgePort
// values to avoid port conflicts (e.g. 9200 for DataBridge, 9201 for Internals).

#region Using
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DEEP6MarketInternals : Indicator
    {
        private DataBridgeServer _bridge;
        private double _tick = double.NaN;
        private double _add  = double.NaN;
        private double _vold = double.NaN;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Market Internals — forwards ^TICK, ^ADD, ^VOLD via DataBridge";
                Name        = "DEEP6 MarketInternals";
                Calculate   = Calculate.OnBarClose;
                IsOverlay   = true;
                DisplayInDataBox        = false;
                DrawOnPricePanel        = false;
                IsSuspendedWhileInactive = false; // keep streaming even when chart is in background
            }
            else if (State == State.Configure)
            {
                // BarsInProgress 1 = ^TICK (NYSE Tick Index)
                AddDataSeries(TickSymbol, BarsPeriodType.Tick, 1);
                // BarsInProgress 2 = ^ADD  (NYSE Advance/Decline)
                AddDataSeries(AddSymbol,  BarsPeriodType.Tick, 1);
                // BarsInProgress 3 = ^VOLD (NYSE Up/Down Volume)
                AddDataSeries(VoldSymbol, BarsPeriodType.Tick, 1);
            }
            else if (State == State.DataLoaded)
            {
                _bridge = new DataBridgeServer(BridgePort);
                _bridge.Start();
                Print($"[DEEP6 Internals] Server started on port {BridgePort}. Streaming ^TICK, ^ADD, ^VOLD.");
            }
            else if (State == State.Terminated)
            {
                if (_bridge != null)
                {
                    _bridge.Dispose();
                    _bridge = null;
                }
            }
        }

        protected override void OnBarUpdate()
        {
            if (_bridge == null || _bridge.ClientCount == 0) return;

            // Route by data series index
            if (BarsInProgress == 1)       // ^TICK
                _tick = Closes[1][0];
            else if (BarsInProgress == 2)  // ^ADD
                _add = Closes[2][0];
            else if (BarsInProgress == 3)  // ^VOLD
                _vold = Closes[3][0];
            else
                return; // primary series — ignore

            // Broadcast whenever any internals series updates
            _bridge.WriteInternals(
                double.IsNaN(_tick) ? 0 : _tick,
                double.IsNaN(_add)  ? 0 : _add,
                double.IsNaN(_vold) ? 0 : _vold
            );
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1024, 65535)]
        [Display(Name = "Bridge Port", Order = 1, GroupName = "DEEP6 Internals",
                 Description = "TCP port for the data bridge server. Default 9200.")]
        public int BridgePort { get; set; } = 9200;

        [NinjaScriptProperty]
        [Display(Name = "TICK Symbol", Order = 2, GroupName = "DEEP6 Internals",
                 Description = "NYSE TICK index symbol. Default ^TICK.")]
        public string TickSymbol { get; set; } = "^TICK";

        [NinjaScriptProperty]
        [Display(Name = "ADD Symbol", Order = 3, GroupName = "DEEP6 Internals",
                 Description = "NYSE Advance/Decline symbol. Default ^ADD.")]
        public string AddSymbol { get; set; } = "^ADD";

        [NinjaScriptProperty]
        [Display(Name = "VOLD Symbol", Order = 4, GroupName = "DEEP6 Internals",
                 Description = "NYSE Up/Down Volume symbol. Default ^VOLD.")]
        public string VoldSymbol { get; set; } = "^VOLD";

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.

namespace NinjaTrader.NinjaScript.Indicators
{
	public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
	{
		private DEEP6.DEEP6MarketInternals[] cacheDEEP6MarketInternals;
		public DEEP6.DEEP6MarketInternals DEEP6MarketInternals(int bridgePort, string tickSymbol, string addSymbol, string voldSymbol)
		{
			return DEEP6MarketInternals(Input, bridgePort, tickSymbol, addSymbol, voldSymbol);
		}

		public DEEP6.DEEP6MarketInternals DEEP6MarketInternals(ISeries<double> input, int bridgePort, string tickSymbol, string addSymbol, string voldSymbol)
		{
			if (cacheDEEP6MarketInternals != null)
				for (int idx = 0; idx < cacheDEEP6MarketInternals.Length; idx++)
					if (cacheDEEP6MarketInternals[idx] != null && cacheDEEP6MarketInternals[idx].BridgePort == bridgePort && cacheDEEP6MarketInternals[idx].TickSymbol == tickSymbol && cacheDEEP6MarketInternals[idx].AddSymbol == addSymbol && cacheDEEP6MarketInternals[idx].VoldSymbol == voldSymbol && cacheDEEP6MarketInternals[idx].EqualsInput(input))
						return cacheDEEP6MarketInternals[idx];
			return CacheIndicator<DEEP6.DEEP6MarketInternals>(new DEEP6.DEEP6MarketInternals(){ BridgePort = bridgePort, TickSymbol = tickSymbol, AddSymbol = addSymbol, VoldSymbol = voldSymbol }, input, ref cacheDEEP6MarketInternals);
		}
	}
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
	public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
	{
		public Indicators.DEEP6.DEEP6MarketInternals DEEP6MarketInternals(int bridgePort, string tickSymbol, string addSymbol, string voldSymbol)
		{
			return indicator.DEEP6MarketInternals(Input, bridgePort, tickSymbol, addSymbol, voldSymbol);
		}

		public Indicators.DEEP6.DEEP6MarketInternals DEEP6MarketInternals(ISeries<double> input, int bridgePort, string tickSymbol, string addSymbol, string voldSymbol)
		{
			return indicator.DEEP6MarketInternals(input, bridgePort, tickSymbol, addSymbol, voldSymbol);
		}
	}
}

namespace NinjaTrader.NinjaScript.Strategies
{
	public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
	{
		public Indicators.DEEP6.DEEP6MarketInternals DEEP6MarketInternals(int bridgePort, string tickSymbol, string addSymbol, string voldSymbol)
		{
			return indicator.DEEP6MarketInternals(Input, bridgePort, tickSymbol, addSymbol, voldSymbol);
		}

		public Indicators.DEEP6.DEEP6MarketInternals DEEP6MarketInternals(ISeries<double> input, int bridgePort, string tickSymbol, string addSymbol, string voldSymbol)
		{
			return indicator.DEEP6MarketInternals(input, bridgePort, tickSymbol, addSymbol, voldSymbol);
		}
	}
}

#endregion

// DataBridgeIndicator: NT8 indicator that forwards all market events to the
// NinjaScript Simulator via the DataBridgeServer TCP connection.
//
// Install: copy to %USERPROFILE%\Documents\NinjaTrader 8\bin\Custom\Indicators\DEEP6\
// Usage: add this indicator to any NQ chart. It starts the bridge server
// on port 9200 and forwards every OnMarketData, OnMarketDepth, and OnBarUpdate
// event to connected simulator clients.
//
// This indicator is invisible (no plots, no chart rendering). It only bridges data.
//
// On the simulator side, run:
//   dotnet run --project ninjatrader/simulator -- bridge 9200
// to connect and receive live data.

#region Using
using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.DEEP6
{
    public class DataBridgeIndicator : Indicator
    {
        private DataBridgeServer _bridge;
        private double _bestBid = double.NaN, _bestAsk = double.NaN;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 Data Bridge — forwards market data to the NinjaScript Simulator on macOS";
                Name = "DEEP6 DataBridge";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = false;
                DrawOnPricePanel = false;
                IsSuspendedWhileInactive = false; // keep streaming even when chart is in background
            }
            else if (State == State.DataLoaded)
            {
                _bridge = new DataBridgeServer(BridgePort);
                _bridge.Start();
                Print($"[DEEP6 Bridge] Server started on port {BridgePort}. Waiting for simulator connection...");
            }
            else if (State == State.Terminated)
            {
                if (_bridge != null)
                {
                    Print($"[DEEP6 Bridge] Stopping server. Served {_bridge.ClientCount} client(s).");
                    _bridge.Dispose();
                    _bridge = null;
                }
            }
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (_bridge == null || _bridge.ClientCount == 0) return;

            if (e.MarketDataType == MarketDataType.Bid)
            {
                _bestBid = e.Price;
                return;
            }
            if (e.MarketDataType == MarketDataType.Ask)
            {
                _bestAsk = e.Price;
                return;
            }
            if (e.MarketDataType != MarketDataType.Last) return;

            // Classify aggressor from BBO
            int aggressor;
            if (!double.IsNaN(_bestAsk) && e.Price >= _bestAsk) aggressor = 1;
            else if (!double.IsNaN(_bestBid) && e.Price <= _bestBid) aggressor = 2;
            else aggressor = 0;

            _bridge.WriteTrade(e.Price, (long)e.Volume, aggressor);
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (_bridge == null || _bridge.ClientCount == 0) return;
            if (e.Position >= 10) return; // same filter as DEEP6Footprint

            int side = e.MarketDataType == MarketDataType.Bid ? 0 : 1;
            long size = e.Operation == Operation.Remove ? 0 : (long)e.Volume;

            _bridge.WriteDepth(side, e.Position, e.Price, size);
        }

        protected override void OnBarUpdate()
        {
            if (_bridge == null || _bridge.ClientCount == 0) return;
            if (BarsInProgress != 0) return;
            if (CurrentBar < 2) return;

            // Send the prior bar (just closed)
            int prevIdx = CurrentBar - 1;
            double open = Bars.GetOpen(prevIdx);
            double high = Bars.GetHigh(prevIdx);
            double low = Bars.GetLow(prevIdx);
            double close = Bars.GetClose(prevIdx);

            // We don't have footprint data here — just OHLCV.
            // The simulator builds its own FootprintBar from the ticks it received.
            _bridge.WriteBar(open, high, low, close, 0, (long)Bars.GetVolume(prevIdx), 0);
        }

        #region Properties

        [NinjaScriptProperty]
        [Range(1024, 65535)]
        [Display(Name = "Bridge Port", Order = 1, GroupName = "DEEP6 Bridge",
                 Description = "TCP port for the data bridge server. Default 9200.")]
        public int BridgePort { get; set; } = 9200;

        #endregion
    }
}

#region NinjaScript generated code. Neither change nor remove.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase
    {
        private DEEP6.DataBridgeIndicator[] cacheDataBridgeIndicator;
        public DEEP6.DataBridgeIndicator DataBridgeIndicator(int bridgePort)
        {
            return DataBridgeIndicator(Input, bridgePort);
        }

        public DEEP6.DataBridgeIndicator DataBridgeIndicator(ISeries<double> input, int bridgePort)
        {
            if (cacheDataBridgeIndicator != null)
                for (int idx = 0; idx < cacheDataBridgeIndicator.Length; idx++)
                    if (cacheDataBridgeIndicator[idx] != null && cacheDataBridgeIndicator[idx].BridgePort == bridgePort && cacheDataBridgeIndicator[idx].EqualsInput(input))
                        return cacheDataBridgeIndicator[idx];
            return CacheIndicator<DEEP6.DataBridgeIndicator>(new DEEP6.DataBridgeIndicator() { BridgePort = bridgePort }, input, ref cacheDataBridgeIndicator);
        }
    }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : MarketAnalyzerColumnBase
    {
        public Indicators.DEEP6.DataBridgeIndicator DataBridgeIndicator(int bridgePort)
        {
            return indicator.DataBridgeIndicator(Input, bridgePort);
        }

        public Indicators.DEEP6.DataBridgeIndicator DataBridgeIndicator(ISeries<double> input, int bridgePort)
        {
            return indicator.DataBridgeIndicator(input, bridgePort);
        }
    }
}
#endregion

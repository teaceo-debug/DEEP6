// StrategyBase — base class for NinjaScript strategies.
// Provides entry/exit methods, Position, Account, ATM strategy methods, strategy properties.

using System;
using NinjaTrader.Cbi;
using NinjaTrader.Data;

namespace NinjaTrader.NinjaScript
{
    public enum EntryHandling { AllEntries, UniqueEntries }
    public enum StartBehavior { AdoptAccountPosition, ImmediatelySubmit, WaitUntilFlat, WaitUntilFlatSynchronizeAccount }
    public enum OrderFillResolution { Standard, High }
    public enum RealtimeErrorHandling { IgnoreAllErrors, StopCancelClose, StopCancelCloseIgnoreRejects }
    public enum StopTargetHandling { PerEntryExecution, ByStrategyPosition }

    public abstract class StrategyBase : NinjaScriptBase
    {
        // ── Strategy properties ──
        public string Name { get; set; } = "";
        public string Description { get; set; } = "";
        public Calculate Calculate { get; set; } = Calculate.OnBarClose;
        public int EntriesPerDirection { get; set; } = 1;
        public EntryHandling EntryHandling { get; set; } = EntryHandling.AllEntries;
        public bool IsExitOnSessionCloseStrategy { get; set; }
        public int ExitOnSessionCloseSeconds { get; set; } = 30;
        public bool IsFillLimitOnTouch { get; set; }
        public MaximumBarsLookBack MaximumBarsLookBack { get; set; } = MaximumBarsLookBack.TwoHundredFiftySix;
        public OrderFillResolution OrderFillResolution { get; set; } = OrderFillResolution.Standard;
        public double Slippage { get; set; }
        public StartBehavior StartBehavior { get; set; } = StartBehavior.WaitUntilFlat;
        public TimeInForce TimeInForce { get; set; } = TimeInForce.Day;
        public bool TraceOrders { get; set; }
        public RealtimeErrorHandling RealtimeErrorHandling { get; set; } = RealtimeErrorHandling.StopCancelClose;
        public StopTargetHandling StopTargetHandling { get; set; } = StopTargetHandling.PerEntryExecution;
        public int BarsRequiredToTrade { get; set; } = 20;
        public bool IsInstantiatedOnEachOptimizationIteration { get; set; }

        // ── Account + Position ──
        public Account Account { get; set; } = new Account();
        public Position Position { get; set; } = new Position();

        // ── Entry methods ──
        public Order EnterLong(string signalName = "")
        {
            Print($"[SIM] EnterLong: {signalName}");
            Position.MarketPosition = MarketPosition.Long;
            Position.Quantity = 1;
            return new Order { Name = signalName, OrderAction = OrderAction.Buy };
        }

        public Order EnterLong(int quantity, string signalName = "")
        {
            Print($"[SIM] EnterLong qty={quantity}: {signalName}");
            Position.MarketPosition = MarketPosition.Long;
            Position.Quantity = quantity;
            return new Order { Name = signalName, OrderAction = OrderAction.Buy, Quantity = quantity };
        }

        public Order EnterShort(string signalName = "")
        {
            Print($"[SIM] EnterShort: {signalName}");
            Position.MarketPosition = MarketPosition.Short;
            Position.Quantity = 1;
            return new Order { Name = signalName, OrderAction = OrderAction.SellShort };
        }

        public Order EnterShort(int quantity, string signalName = "")
        {
            Print($"[SIM] EnterShort qty={quantity}: {signalName}");
            Position.MarketPosition = MarketPosition.Short;
            Position.Quantity = quantity;
            return new Order { Name = signalName, OrderAction = OrderAction.SellShort, Quantity = quantity };
        }

        // ── Exit methods ──
        public Order ExitLong(string signalName = "")
        {
            Print($"[SIM] ExitLong: {signalName}");
            Position.MarketPosition = MarketPosition.Flat;
            Position.Quantity = 0;
            return new Order { Name = signalName, OrderAction = OrderAction.Sell };
        }

        public Order ExitShort(string signalName = "")
        {
            Print($"[SIM] ExitShort: {signalName}");
            Position.MarketPosition = MarketPosition.Flat;
            Position.Quantity = 0;
            return new Order { Name = signalName, OrderAction = OrderAction.BuyToCover };
        }

        // ── Stop/Target ──
        public void SetStopLoss(CalculationMode mode, double value) { }
        public void SetStopLoss(string fromEntrySignal, CalculationMode mode, double value, bool isSimulatedStop) { }
        public void SetProfitTarget(CalculationMode mode, double value) { }
        public void SetProfitTarget(string fromEntrySignal, CalculationMode mode, double value) { }

        // ── ATM Strategy stubs ──
        public delegate void AtmStrategyCallback(ErrorCode errorCode, string id);

        public void AtmStrategyCreate(OrderAction action, OrderType orderType, double limitPrice, double stopPrice,
            TimeInForce tif, string orderId, string templateName, string atmGuid, AtmStrategyCallback callback)
        {
            Print($"[SIM] AtmStrategyCreate: action={action} template={templateName} guid={atmGuid}");
            callback?.Invoke(ErrorCode.NoError, orderId);
        }

        public void AtmStrategyClose(string atmGuid)
        {
            Print($"[SIM] AtmStrategyClose: {atmGuid}");
            Position.MarketPosition = MarketPosition.Flat;
            Position.Quantity = 0;
        }

        // ── Position lifecycle hooks ──
        protected virtual void OnPositionUpdate(Position position, double averagePrice, int quantity, MarketPosition marketPosition) { }
        protected virtual void OnExecutionUpdate(Execution execution, string executionId, double price, int quantity,
            MarketPosition marketPosition, string orderId, DateTime time) { }

        internal void InvokePositionUpdate(Position pos, double avgPrice, int qty, MarketPosition mp)
        {
            OnPositionUpdate(pos, avgPrice, qty, mp);
        }

        internal void InvokeExecutionUpdate(Execution exec, string execId, double price, int qty, MarketPosition mp, string orderId, DateTime time)
        {
            OnExecutionUpdate(exec, execId, price, qty, mp, orderId, time);
        }
    }

    public enum CalculationMode { Currency, Percent, Price, Pips, Ticks }
}

// Partial class stub for NT8's generated Strategy code region.
namespace NinjaTrader.NinjaScript.Strategies
{
    public partial class Strategy : NinjaTrader.Gui.NinjaScript.StrategyRenderBase
    {
        // NT8 generates factory methods on partial Strategy that call through to indicator.
        protected NinjaTrader.NinjaScript.Indicators.Indicator indicator = new();
    }
}

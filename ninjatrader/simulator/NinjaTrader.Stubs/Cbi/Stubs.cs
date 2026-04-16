// NinjaTrader.Cbi stubs — Account, Position, Order, Execution, Currency, enums.

namespace NinjaTrader.Cbi
{
    public enum MarketPosition { Flat, Long, Short }
    public enum OrderAction { Buy, Sell, BuyToCover, SellShort }
    public enum OrderType { Market, Limit, StopMarket, StopLimit, MIT }
    public enum TimeInForce { Day, Gtc, Ioc }
    public enum Currency { UsDollar, Euro, BritishPound, JapaneseYen, SwissFranc, CanadianDollar, AustralianDollar }
    public enum AccountItem { NetLiquidation, CashValue, BuyingPower, RealizedProfitLoss, UnrealizedProfitLoss }
    public enum ErrorCode { NoError, OrderRejected, UserAbort, Panic, LogOnFailed, UnableToCancelOrder, UnableToChangeOrder, UnableToSubmitOrder }
    public enum ConnectionStatus { Connected, Connecting, ConnectionLost, Disconnected }

    public class Account
    {
        public string Name { get; set; } = "Sim101";
        public ConnectionStatus ConnectionStatus { get; set; } = ConnectionStatus.Connected;

        public double Get(AccountItem item, Currency currency)
        {
            // Return simulated values
            return item switch
            {
                AccountItem.NetLiquidation => 50000.0,
                AccountItem.CashValue => 50000.0,
                AccountItem.BuyingPower => 50000.0,
                _ => 0.0
            };
        }
    }

    public class Position
    {
        public MarketPosition MarketPosition { get; set; } = MarketPosition.Flat;
        public int Quantity { get; set; }
        public double AveragePrice { get; set; }
    }

    public class Order
    {
        public string Name { get; set; }
        public OrderType OrderType { get; set; }
        public OrderAction OrderAction { get; set; }
        public double LimitPrice { get; set; }
        public double StopPrice { get; set; }
        public int Quantity { get; set; }
    }

    public class Execution
    {
        public Order Order { get; set; }
        public double Price { get; set; }
        public int Quantity { get; set; }
        public MarketPosition MarketPosition { get; set; }
        public System.DateTime Time { get; set; }
    }

    public class Instrument
    {
        public string FullName { get; set; } = "NQ 06-26";
        public MasterInstrument MasterInstrument { get; set; } = new MasterInstrument();
    }

    public class MasterInstrument
    {
        public string Name { get; set; } = "NQ";
        public double TickSize { get; set; } = 0.25;
        public double PointValue { get; set; } = 20.0;
        public InstrumentType InstrumentType { get; set; } = InstrumentType.Future;
    }

    public enum InstrumentType { Stock, Future, Forex, Option, Index, Cfd, Crypto }
}

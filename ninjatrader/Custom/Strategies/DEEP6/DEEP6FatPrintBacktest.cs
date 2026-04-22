// DEEP6 FatPrint Backtest Strategy
//
// Entry rule: when a FatPrint (gray diamond) appears on bar N, enter on bar N+1 open.
// FatPrint = the single price level that traded more volume than average × FatMult.
// This is the same "acceptance" signal drawn as a gray diamond by DEEP6Footprint.
//
// Direction options:
//   FollowBar  — long if N was an up bar, short if N was a down bar
//   FadeBar    — short if N was an up bar, long if N was a down bar
//   AlwaysLong / AlwaysShort — override direction for one-sided testing
//
// Requires: Volumetric bar type (same as footprint chart — 1min, 5min, etc.)

using System;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Strategies;

namespace NinjaTrader.NinjaScript.Strategies.DEEP6
{
    public enum FatPrintTradeDirection
    {
        FollowBar,    // long on up bar, short on down bar
        FadeBar,      // short on up bar, long on down bar
        AlwaysLong,
        AlwaysShort,
    }

    public class DEEP6FatPrintBacktest : Strategy
    {
        private bool _fatPrintPending;
        private int  _fatPrintBarIndex;
        private int  _fatPrintDirection;   // +1 long, -1 short (resolved at detection)

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description  = "Backtest the FatPrint (gray diamond) entry: enter next bar after detection.";
                Name         = "DEEP6 FatPrint Backtest";
                Calculate    = Calculate.OnBarClose;
                EntriesPerDirection = 1;
                EntryHandling = EntryHandling.AllEntries;
                IsExitOnSessionCloseStrategy = true;
                ExitOnSessionCloseSeconds    = 30;

                FatMult           = 3.0;
                TargetTicks       = 20;
                StopTicks         = 16;
                TradeDirection    = FatPrintTradeDirection.FollowBar;
                MinBarRange       = 4;    // skip inside bars (< N ticks high-low)
            }
            else if (State == State.Configure)
            {
                // Strategy must run on volumetric bars — caller's responsibility.
                // Warn in output if we can't cast but don't crash.
            }
        }

        protected override void OnBarUpdate()
        {
            if (CurrentBar < 2) return;

            // ── Step 1: Execute pending entry on this bar's open ──
            if (_fatPrintPending && CurrentBar > _fatPrintBarIndex)
            {
                _fatPrintPending = false;
                if (_fatPrintDirection > 0)
                    EnterLong(1, "FatPrint");
                else
                    EnterShort(1, "FatPrint");
            }

            // ── Step 2: Detect FatPrint on the bar that just closed ──
            if (DetectFatPrint(CurrentBar, out double fatPx))
            {
                // Resolve direction
                int dir = ResolveDirection();
                if (dir == 0) return;   // neutral bar + FollowBar/FadeBar = skip

                _fatPrintPending   = true;
                _fatPrintBarIndex  = CurrentBar;
                _fatPrintDirection = dir;
            }
        }

        private bool DetectFatPrint(int barIdx, out double fatPx)
        {
            fatPx = 0;

            // Skip tiny bars — they produce noisy fat prints
            if ((High[0] - Low[0]) < MinBarRange * TickSize) return false;

            var barsType = Bars.BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            if (barsType == null) return false;

            var volumes = barsType.Volumes[barIdx];
            if (volumes == null || volumes.TotalVolume == 0) return false;

            // Walk each price level: find highest-volume tick
            double fattestVol = 0;
            double fattestPx  = 0;
            long   levelCount = 0;
            long   totalVol   = 0;

            double lo = Low[0];
            double hi = High[0];

            for (double px = lo; px <= hi + TickSize * 0.5; px += TickSize)
            {
                double ask = volumes.GetAskVolumeForPrice(px);
                double bid = volumes.GetBidVolumeForPrice(px);
                double lv  = ask + bid;
                if (lv <= 0) continue;

                levelCount++;
                totalVol += (long)lv;

                if (lv > fattestVol)
                {
                    fattestVol = lv;
                    fattestPx  = px;
                }
            }

            if (levelCount < 3 || totalVol == 0) return false;

            double avgLevelVol = (double)totalVol / levelCount;
            if (fattestVol < avgLevelVol * FatMult) return false;

            fatPx = fattestPx;
            return true;
        }

        private int ResolveDirection()
        {
            switch (TradeDirection)
            {
                case FatPrintTradeDirection.AlwaysLong:  return +1;
                case FatPrintTradeDirection.AlwaysShort: return -1;
                case FatPrintTradeDirection.FollowBar:
                    if (Close[0] > Open[0]) return +1;
                    if (Close[0] < Open[0]) return -1;
                    return 0;
                case FatPrintTradeDirection.FadeBar:
                    if (Close[0] > Open[0]) return -1;
                    if (Close[0] < Open[0]) return +1;
                    return 0;
                default:
                    return 0;
            }
        }

        protected override void OnExecutionUpdate(Execution execution, string executionId,
            double price, int quantity, MarketPosition marketPosition,
            string orderId, DateTime time)
        {
            if (execution.Order == null) return;

            // Place bracket on fill
            if (execution.Order.Name == "FatPrint" && execution.Order.OrderState == OrderState.Filled)
            {
                if (marketPosition == MarketPosition.Long)
                {
                    SetStopLoss("FatPrint",   CalculationMode.Ticks, StopTicks,  false);
                    SetProfitTarget("FatPrint", CalculationMode.Ticks, TargetTicks, false);
                }
                else if (marketPosition == MarketPosition.Short)
                {
                    SetStopLoss("FatPrint",   CalculationMode.Ticks, StopTicks,  false);
                    SetProfitTarget("FatPrint", CalculationMode.Ticks, TargetTicks, false);
                }
            }
        }

        #region Properties

        [NinjaScriptProperty]
        [Display(Name = "Fat Mult (× avg level vol)", Order = 1, GroupName = "FatPrint Detection")]
        public double FatMult { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Min Bar Range (ticks)", Order = 2, GroupName = "FatPrint Detection")]
        public int MinBarRange { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Trade Direction", Order = 3, GroupName = "Entry")]
        public FatPrintTradeDirection TradeDirection { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Target (ticks)", Order = 4, GroupName = "Exit")]
        public int TargetTicks { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Stop (ticks)", Order = 5, GroupName = "Exit")]
        public int StopTicks { get; set; }

        #endregion
    }
}

using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using NinjaScriptSim.Lifecycle;
using NinjaTrader.Cbi;
using NinjaTrader.NinjaScript.AddOns.DEEP6;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Registry;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;
using NinjaTrader.NinjaScript.Strategies.DEEP6;
using NUnit.Framework;

namespace NinjaTrader.Tests.Strategy
{
    [TestFixture]
    public class DEEP6StrategySimulatorTests
    {
        [SetUp]
        public void SetUp()
        {
            ScorerSharedState.Clear("NQ 06-26");
        }

        [TearDown]
        public void TearDown()
        {
            ScorerSharedState.Clear("NQ 06-26");
        }

        [Test]
        public void ValidateOnly_StrategyLifecycle_CompletesWithoutErrors()
        {
            var runner = new NinjaScriptRunner();
            runner.ValidateOnly<DEEP6Strategy>();

            Assert.That(runner.Errors, Is.Empty, string.Join(" | ", runner.Errors));
            Assert.That(runner.Succeeded, Is.True);
        }

        [Test]
        public void HasFreshScorerResult_RequiresCurrentBarMatch()
        {
            var strategy = CreateInitializedStrategy();
            var scored = MakePassingResult(+1);

            bool fresh = (bool)InvokePrivate(strategy, "HasFreshScorerResult", scored, strategy.CurrentBar, strategy.CurrentBar);
            bool stale = (bool)InvokePrivate(strategy, "HasFreshScorerResult", scored, strategy.CurrentBar - 1, strategy.CurrentBar);

            Assert.That(fresh, Is.True);
            Assert.That(stale, Is.False);
        }

        [Test]
        public void CanEvaluateSharedScorerWithoutLocalFootprint_RequiresRegistryModeAndSharedScore()
        {
            var strategy = CreateInitializedStrategy();
            var scored = MakePassingResult(+1);

            strategy.UseNewRegistry = true;
            bool allowed = (bool)InvokePrivate(strategy, "CanEvaluateSharedScorerWithoutLocalFootprint", null, scored);
            bool blockedWithoutScore = (bool)InvokePrivate(strategy, "CanEvaluateSharedScorerWithoutLocalFootprint", null, null);

            strategy.UseNewRegistry = false;
            bool blockedLegacy = (bool)InvokePrivate(strategy, "CanEvaluateSharedScorerWithoutLocalFootprint", null, scored);

            Assert.That(allowed, Is.True);
            Assert.That(blockedWithoutScore, Is.False);
            Assert.That(blockedLegacy, Is.False);
        }

        [Test]
        public void Run_TwoSessions_LogsSessionBoundaryReset()
        {
            var runner = new NinjaScriptRunner();
            runner.LoadBars(BuildTwoSessionBars());
            var strategy = runner.Run<DEEP6Strategy>();

            Assert.That(runner.Errors, Is.Empty, string.Join(" | ", runner.Errors));
            var sessionLogs = strategy.PrintLog.Where(x => x.Contains("New session")).ToList();
            Assert.That(sessionLogs.Count, Is.GreaterThanOrEqualTo(1), string.Join(" | ", strategy.PrintLog));
            Assert.That(sessionLogs.Any(x => x.Contains("2026-04-24")), Is.True, string.Join(" | ", strategy.PrintLog));
        }

        [Test]
        public void RiskGatesPass_BlocksWithoutSessionStartBalance()
        {
            var strategy = CreateInitializedStrategy();
            strategy.ApprovedAccountName = "Sim101";
            SetPrivateField(strategy, "_sessionStartBalance", double.NaN);
            SetPrivateField(strategy, "_lastEntryBar", -100);
            SetPrivateField(strategy, "_tradesThisSession", 0);

            bool allowed = (bool)InvokePrivate(
                strategy,
                "RiskGatesPass",
                +1,
                19000.0,
                "TEST_TRIGGER",
                strategy.CurrentBar,
                new DateTime(2026, 4, 23, 10, 15, 0, DateTimeKind.Local));

            Assert.That(allowed, Is.False);
            Assert.That(strategy.PrintLog.Any(x => x.Contains("session start balance not yet captured")), Is.True, string.Join(" | ", strategy.PrintLog));
        }

        [Test]
        public void RiskGatesPass_BlocksWithinCooldown()
        {
            var strategy = CreateInitializedStrategy();
            strategy.ApprovedAccountName = "Sim101";
            SetPrivateField(strategy, "_sessionStartBalance", 50000.0);
            SetPrivateField(strategy, "_lastEntryBar", strategy.CurrentBar - 1);
            SetPrivateField(strategy, "_tradesThisSession", 0);

            bool allowed = (bool)InvokePrivate(
                strategy,
                "RiskGatesPass",
                +1,
                19000.0,
                "TEST_TRIGGER",
                strategy.CurrentBar,
                new DateTime(2026, 4, 23, 10, 15, 0, DateTimeKind.Local));

            Assert.That(allowed, Is.False);
            Assert.That(strategy.PrintLog.Any(x => x.Contains("within cooldown")), Is.True, string.Join(" | ", strategy.PrintLog));
        }

        [Test]
        public void RiskGatesPass_BlocksAtMaxTradesPerSession()
        {
            var strategy = CreateInitializedStrategy();
            strategy.ApprovedAccountName = "Sim101";
            SetPrivateField(strategy, "_sessionStartBalance", 50000.0);
            SetPrivateField(strategy, "_lastEntryBar", -100);
            SetPrivateField(strategy, "_tradesThisSession", strategy.MaxTradesPerSession);

            bool allowed = (bool)InvokePrivate(
                strategy,
                "RiskGatesPass",
                +1,
                19000.0,
                "TEST_TRIGGER",
                strategy.CurrentBar,
                new DateTime(2026, 4, 23, 10, 15, 0, DateTimeKind.Local));

            Assert.That(allowed, Is.False);
            Assert.That(strategy.PrintLog.Any(x => x.Contains("max trades reached")), Is.True, string.Join(" | ", strategy.PrintLog));
        }

        [Test]
        public void RiskGatesPass_UsesSignalBarTimestampForTimeChecks()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.RespectNewsBlackouts = true;
            strategy.ApprovedAccountName = "Sim101";
            SetPrivateField(strategy, "_sessionStartBalance", 50000.0);
            SetPrivateField(strategy, "_lastEntryBar", -100);
            SetPrivateField(strategy, "_tradesThisSession", 0);

            bool allowed = (bool)InvokePrivate(
                strategy,
                "RiskGatesPass",
                +1,
                19000.0,
                "TEST_TRIGGER",
                strategy.CurrentBar,
                new DateTime(2026, 4, 23, 9, 59, 0, DateTimeKind.Local));

            Assert.That(allowed, Is.True, string.Join(" | ", strategy.PrintLog));
        }

        [Test]
        public void EvaluateEntry_PassedScoreAndRiskReady_CreatesLiveAtmEntry()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.SlowGrindVetoEnabled = false;
            strategy.RespectNewsBlackouts = false;
            strategy.ApprovedAccountName = "Sim101";
            SetPrivateField(strategy, "_sessionStartBalance", 50000.0);
            SetPrivateField(strategy, "_lastEntryBar", -100);
            SetPrivateField(strategy, "_tradesThisSession", 0);

            var scored = MakePassingResult(+1);
            InvokePrivate(strategy, "EvaluateEntry", strategy.CurrentBar, scored, scored.Signals, 4.0, 1000,
                new DateTime(2026, 4, 23, 10, 0, 0, DateTimeKind.Local));

            Assert.That(strategy.PrintLog.Any(x => x.Contains("ATM created:")), Is.True, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.PrintLog.Any(x => x.Contains("LIVE entry CONFIRMED")), Is.True, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Long));
        }

        [Test]
        public void EvaluateEntry_ApprovedAccountMismatch_BlocksBeforeAtmEntry()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.SlowGrindVetoEnabled = false;
            strategy.RespectNewsBlackouts = false;
            strategy.ApprovedAccountName = "WrongAccount";
            SetPrivateField(strategy, "_sessionStartBalance", 50000.0);
            SetPrivateField(strategy, "_lastEntryBar", -100);
            SetPrivateField(strategy, "_tradesThisSession", 0);

            var scored = MakePassingResult(+1);
            InvokePrivate(strategy, "EvaluateEntry", strategy.CurrentBar, scored, scored.Signals, 4.0, 1000,
                new DateTime(2026, 4, 23, 10, 0, 0, DateTimeKind.Local));

            Assert.That(strategy.PrintLog.Any(x => x.Contains("BLOCKED — account")), Is.True, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.PrintLog.Any(x => x.Contains("LIVE entry CONFIRMED")), Is.False, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Flat));
        }

        [Test]
        public void EvaluateEntry_PlaybackAccount_IsAllowedByDefault()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.SlowGrindVetoEnabled = false;
            strategy.RespectNewsBlackouts = false;
            strategy.ApprovedAccountName = "Sim101";
            strategy.Account.Name = "Playback101";
            SetPrivateField(strategy, "_sessionStartBalance", 50000.0);
            SetPrivateField(strategy, "_lastEntryBar", -100);
            SetPrivateField(strategy, "_tradesThisSession", 0);

            var scored = MakePassingResult(+1);
            InvokePrivate(strategy, "EvaluateEntry", strategy.CurrentBar, scored, scored.Signals, 4.0, 1000,
                new DateTime(2026, 4, 23, 10, 0, 0, DateTimeKind.Local));

            Assert.That(strategy.PrintLog.Any(x => x.Contains("LIVE entry CONFIRMED")), Is.True, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Long));
        }

        [Test]
        public void CheckOpposingExit_UsesConfiguredExitThreshold()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.ExitOnOpposingScore = 0.95;
            strategy.Position.MarketPosition = MarketPosition.Long;
            strategy.Position.Quantity = 2;
            SetPrivateField(strategy, "_activeAtmGuid", "atm-test-guid");

            var abs = new List<AbsorptionSignal>
            {
                new AbsorptionSignal { Direction = -1, Strength = 0.9, Price = 19000.0, Detail = "bearish absorption" }
            };
            var exh = new List<ExhaustionSignal>();

            InvokePrivate(strategy, "CheckOpposingExit", abs, exh);

            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Long));
            Assert.That(GetPrivateField<string>(strategy, "_activeAtmGuid"), Is.EqualTo("atm-test-guid"));
        }

        [Test]
        public void EnterWithAtm_RejectsMissingTemplate()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;

            InvokePrivate(strategy, "EnterWithAtm", +1, "", "TEST_TRIGGER", 19000.0);

            Assert.That(strategy.PrintLog.Any(x => x.Contains("ATM template missing")), Is.True, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Flat));
        }

        [Test]
        public void EnterWithAtm_RejectsScaleOutWhenContractsBelowTwo()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.ScaleOutEnabled = true;
            strategy.MaxContractsPerTrade = 1;

            InvokePrivate(strategy, "EnterWithAtm", +1, "DEEP6_Confluence", "TEST_TRIGGER", 19000.0);

            Assert.That(strategy.PrintLog.Any(x => x.Contains("scale-out requires at least 2 contracts")), Is.True, string.Join(" | ", strategy.PrintLog));
            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Flat));
        }

        [Test]
        public void CheckOpposingExit_WithActiveAtmGuid_ClosesLongPosition()
        {
            var strategy = CreateInitializedStrategy();
            strategy.EnableLiveTrading = true;
            strategy.Position.MarketPosition = MarketPosition.Long;
            strategy.Position.Quantity = 2;
            SetPrivateField(strategy, "_activeAtmGuid", "atm-test-guid");

            var abs = new List<AbsorptionSignal>
            {
                new AbsorptionSignal { Direction = -1, Strength = 0.9, Price = 19000.0, Detail = "bearish absorption" }
            };
            var exh = new List<ExhaustionSignal>();

            InvokePrivate(strategy, "CheckOpposingExit", abs, exh);

            Assert.That(strategy.Position.MarketPosition, Is.EqualTo(MarketPosition.Flat));
            Assert.That(GetPrivateField<string>(strategy, "_activeAtmGuid"), Is.Null);
            Assert.That(strategy.PrintLog.Any(x => x.Contains("EXIT — opposing signal strength")), Is.True, string.Join(" | ", strategy.PrintLog));
        }

        private static DEEP6Strategy CreateInitializedStrategy()
        {
            var runner = new NinjaScriptRunner();
            runner.LoadBars(BuildIntradayBars());
            var strategy = runner.Run<DEEP6Strategy>();
            Assert.That(runner.Errors, Is.Empty, string.Join(" | ", runner.Errors));
            return strategy;
        }

        private static List<BarData> BuildIntradayBars()
        {
            var day = new DateTime(2026, 4, 23, 10, 0, 0, DateTimeKind.Local);
            return new List<BarData>
            {
                MakeBar(day, 19000.0, 19002.0, 18999.0, 19001.0),
                MakeBar(day.AddMinutes(1), 19001.0, 19003.0, 19000.0, 19002.0),
                MakeBar(day.AddMinutes(2), 19002.0, 19004.0, 19001.0, 19003.0),
            };
        }

        private static List<BarData> BuildTwoSessionBars()
        {
            var bars = new List<BarData>();
            var day1 = new DateTime(2026, 4, 23, 10, 0, 0, DateTimeKind.Local);
            var day2 = new DateTime(2026, 4, 24, 10, 0, 0, DateTimeKind.Local);

            for (int i = 0; i < 12; i++)
                bars.Add(MakeBar(day1.AddMinutes(i), 19000.0 + i, 19002.0 + i, 18999.0 + i, 19001.0 + i));

            for (int i = 0; i < 12; i++)
                bars.Add(MakeBar(day2.AddMinutes(i), 19020.0 + i, 19022.0 + i, 19019.0 + i, 19021.0 + i));

            return bars;
        }

        private static BarData MakeBar(DateTime time, double open, double high, double low, double close)
        {
            return new BarData
            {
                Open = open,
                High = high,
                Low = low,
                Close = close,
                Volume = 1000,
                Time = time,
                Ticks = new List<TickData>
                {
                    new TickData { Price = open, Size = 100, Aggressor = 1, Time = time.AddSeconds(5) },
                    new TickData { Price = high, Size = 100, Aggressor = 1, Time = time.AddSeconds(20) },
                    new TickData { Price = low, Size = 100, Aggressor = 2, Time = time.AddSeconds(40) },
                    new TickData { Price = close, Size = 100, Aggressor = 1, Time = time.AddSeconds(55) },
                },
            };
        }

        private static ScorerResult MakePassingResult(int direction)
        {
            return new ScorerResult
            {
                TotalScore = 88.0,
                Tier = SignalTier.TYPE_A,
                Direction = direction,
                Narrative = direction > 0 ? "BULL TEST" : "BEAR TEST",
                EntryPrice = 19000.0,
                EngineAgreement = 1.0,
                CategoryCount = 5,
                ConfluenceMult = 1.25,
                ZoneBonus = 8.0,
                CategoriesFiring = new[] { "absorption", "exhaustion", "delta", "auction", "volume_profile" },
                Signals = new[]
                {
                    new SignalResult("ABS-01", direction, 0.9, 0UL, "abs", 19000.0),
                    new SignalResult("EXH-02", direction, 0.8, 0UL, "exh", 19000.0),
                    new SignalResult("DELT-04", direction, 0.7, 0UL, "delt", 19000.0),
                },
            };
        }

        private static object InvokePrivate(object target, string methodName, params object[] args)
        {
            var method = target.GetType().GetMethod(methodName, BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.That(method, Is.Not.Null, $"Missing private method {methodName}");
            return method.Invoke(target, args);
        }

        private static void SetPrivateField(object target, string fieldName, object value)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.That(field, Is.Not.Null, $"Missing private field {fieldName}");
            field.SetValue(target, value);
        }

        private static T GetPrivateField<T>(object target, string fieldName)
        {
            var field = target.GetType().GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic);
            Assert.That(field, Is.Not.Null, $"Missing private field {fieldName}");
            return (T)field.GetValue(target);
        }
    }
}

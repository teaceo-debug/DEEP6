using System;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Indicators
{
    [TestFixture]
    [Category("Indicators")]
    public class FootprintTradeSetupTests
    {
        [Test]
        public void ScorerResult_ContainsTradeLifecycleFields_ForFootprintExecutionPlan()
        {
            var t = typeof(ScorerResult);
            string[] required =
            {
                "SetupState",
                "ExpireAfterBarIndex",
                "TriggerBarIndex",
                "Confidence",
            };

            var missing = required.Where(name => t.GetField(name, BindingFlags.Public | BindingFlags.Instance) == null).ToArray();
            Assert.That(missing, Is.Empty,
                "Version Two footprint workflow needs explicit setup lifecycle fields on ScorerResult. Missing: " + string.Join(", ", missing));
        }

        [Test]
        public void ScorerSharedState_StillPublishesBaseResult_WithoutThrowing()
        {
            var result = new ScorerResult
            {
                TotalScore = 81.0,
                Tier = SignalTier.TYPE_A,
                Direction = 1,
                Narrative = "baseline",
                EntryPrice = 19000.0,
                CategoryCount = 5,
                EngineAgreement = 1.0,
                ConfluenceMult = 1.25,
                ZoneBonus = 8.0,
                CategoriesFiring = new[] { "absorption", "auction" },
            };

            Assert.DoesNotThrow(() => ScorerSharedState.Publish("NQ 06-26", 123, result, 4.0));
            var latest = ScorerSharedState.Latest("NQ 06-26");
            Assert.That(latest, Is.Not.Null);
            Assert.That(latest.TotalScore, Is.EqualTo(81.0));
            ScorerSharedState.Clear("NQ 06-26");
        }

        [Test]
        public void FutureSetupStateEnumExists_ForSetupArmedTriggeredInvalidExpiredWorkflow()
        {
            var type = Type.GetType("NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring.TradeSetupState");
            Assert.That(type, Is.Not.Null,
                "Version Two requires a TradeSetupState enum so gray-square setups can progress through Setup -> Armed -> Triggered -> Invalid/Expired.");
        }
    }
}

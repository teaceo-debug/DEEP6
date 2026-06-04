using System;
using System.Linq;
using System.Reflection;
using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Scoring;

namespace NinjaTrader.Tests.Indicators
{
    [TestFixture]
    [Category("Indicators")]
    public class GexSharedStateTests
    {
        [Test]
        public void GexSharedState_TypeExists_AsIndependentSharedStateBridge()
        {
            var type = Type.GetType("NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge.GexSharedState");
            Assert.That(type, Is.Not.Null,
                "Version Two requires a dedicated GexSharedState bridge so DEEP6GexLevels can publish machine-readable mapped levels.");
        }

        [Test]
        public void ScorerResult_ContainsLinkedGexMetadata_ForSetupFormation()
        {
            var t = typeof(ScorerResult);
            string[] required =
            {
                "LinkedLevelKind",
                "LinkedLevelPrice",
                "LinkedLevelDistanceTicks",
            };

            var missing = required.Where(name => t.GetField(name, BindingFlags.Public | BindingFlags.Instance) == null).ToArray();
            Assert.That(missing, Is.Empty,
                "Version Two setup formation needs linked GEX metadata and target fields on ScorerResult. Missing: " + string.Join(", ", missing));
        }

        [Test]
        public void FutureBridgeContract_ExposesLatestAndPublishMethods()
        {
            var type = Type.GetType("NinjaTrader.NinjaScript.AddOns.DEEP6.Bridge.GexSharedState");
            Assert.That(type, Is.Not.Null, "GexSharedState type must exist before method contract can be verified.");
            if (type == null) return;

            var methods = type.GetMethods(BindingFlags.Public | BindingFlags.Static).Select(m => m.Name).ToArray();
            Assert.That(methods, Does.Contain("Publish"));
            Assert.That(methods, Does.Contain("Latest"));
        }

        [Test]
        public void Publish_AndNearestQueries_ReturnDeterministicMappedLevels()
        {
            const string instrument = "NQ 06-26";
            GexSharedState.Clear(instrument);

            var snapshot = new GexContextSnapshot
            {
                Instrument = instrument,
                FetchedUtc = new DateTime(2026, 4, 22, 18, 0, 0, DateTimeKind.Utc),
                Levels =
                {
                    new MappedGexLevel { Kind = "PutWall", NqPrice = 18980.0 },
                    new MappedGexLevel { Kind = "GammaFlip", NqPrice = 19000.0 },
                    new MappedGexLevel { Kind = "CallWall", NqPrice = 19020.0 },
                }
            };

            GexSharedState.Publish(instrument, snapshot);

            Assert.That(GexSharedState.Latest(instrument), Is.Not.Null);
            Assert.That(GexSharedState.NearestBelow(instrument, 19005.0)?.Kind, Is.EqualTo("GammaFlip"));
            Assert.That(GexSharedState.NearestAbove(instrument, 19005.0)?.Kind, Is.EqualTo("CallWall"));
            Assert.That(GexSharedState.NearestOfKind(instrument, "PutWall", 19005.0)?.NqPrice, Is.EqualTo(18980.0));
        }
    }
}

using NUnit.Framework;
using NinjaTrader.Tests.MADConfluenceAI;

namespace NinjaTrader.Tests.MADConfluenceAI
{
    [TestFixture]
    public class FixtureTests : MADConfluenceAITestBase
    {
        [Test]
        public void LoadFixture_ExampleAbs01_ParsesCorrectly()
        {
            var fixture = LoadFixture("abs-01-example.json");
            Assert.IsNotNull(fixture, "Fixture should not be null");
            Assert.AreEqual("Classic absorption at prior day low support level", fixture.Description);
            Assert.IsNotNull(fixture.Bar, "Bar should not be null");
            Assert.AreEqual(20002.0, fixture.Bar.Open, 0.001);
            Assert.IsNotNull(fixture.Bar.Levels, "Levels should not be null");
            Assert.IsTrue(fixture.Bar.Levels.ContainsKey("20000.00"));
            Assert.AreEqual(150, fixture.Bar.Levels["20000.00"].Bid);
            Assert.AreEqual(25, fixture.Bar.Levels["20000.00"].Ask);
            Assert.IsNotNull(fixture.Session, "Session should not be null");
            Assert.AreEqual(45.0, fixture.Session.Atr20, 0.001);
            Assert.IsNotNull(fixture.Expected, "Expected array should not be null");
            Assert.AreEqual(1, fixture.Expected.Length);
            Assert.AreEqual("ABS-01", fixture.Expected[0].SignalId);
            Assert.AreEqual("Long", fixture.Expected[0].Direction);
        }

        [Test]
        public void FixturesDirectory_Exists()
        {
            Assert.IsTrue(System.IO.Directory.Exists(FixturesPath), 
                $"Fixtures directory should exist at: {FixturesPath}");
        }
    }
}

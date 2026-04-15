// WassersteinVsScipyParityTests: verifies Wasserstein.Distance matches scipy.stats.wasserstein_distance
// to within 1e-9 tolerance on a set of pre-committed cases.
//
// Cases generated offline via Python (scipy.stats.wasserstein_distance) and committed as static JSON.
// No Python runtime required in CI.
//
// Python reference:
//   scipy.stats.wasserstein_distance(positions, positions, u_weights=u, v_weights=v)
//   where positions = [0, 1, ..., N-1].
//
// C# reference: Wasserstein.Distance(double[] u, double[] v)

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using DeepWasserstein = NinjaTrader.NinjaScript.AddOns.DEEP6.Math.Wasserstein;

namespace NinjaTrader.Tests.Parity
{
    [TestFixture]
    public class WassersteinVsScipyParityTests
    {
        private static string FixturePath() =>
            Path.Combine(TestContext.CurrentContext.TestDirectory,
                "Parity", "fixtures", "wasserstein-cases.json");

        private struct WassersteinCase
        {
            public string   description;
            public double[] u;
            public double[] v;
            public double   expected;
        }

        private static IEnumerable<WassersteinCase> LoadCases()
        {
            string json = File.ReadAllText(FixturePath());
            using var doc = JsonDocument.Parse(json);
            foreach (var elem in doc.RootElement.EnumerateArray())
            {
                var c = new WassersteinCase
                {
                    description = elem.GetProperty("description").GetString(),
                    expected    = elem.GetProperty("expected").GetDouble(),
                };
                var uList = new List<double>();
                foreach (var v in elem.GetProperty("u").EnumerateArray()) uList.Add(v.GetDouble());
                c.u = uList.ToArray();
                var vList = new List<double>();
                foreach (var v in elem.GetProperty("v").EnumerateArray()) vList.Add(v.GetDouble());
                c.v = vList.ToArray();
                yield return c;
            }
        }

        [Test]
        public void WassersteinCases_AllMatchScipyWithin1e9()
        {
            const double tolerance = 1e-9;
            int count = 0;
            var failures = new List<string>();

            foreach (var c in LoadCases())
            {
                count++;
                double actual = DeepWasserstein.Distance(c.u, c.v);
                double diff   = System.Math.Abs(actual - c.expected);

                // Use relative tolerance for large expected values
                double tol = System.Math.Max(tolerance, System.Math.Abs(c.expected) * 1e-9);

                if (diff > tol)
                {
                    failures.Add(string.Format(
                        "Case '{0}': actual={1:G17} expected={2:G17} diff={3:E3} (tol={4:E3})",
                        c.description, actual, c.expected, diff, tol));
                }
            }

            Assert.That(count, Is.GreaterThanOrEqualTo(10),
                "Should have at least 10 Wasserstein parity cases");

            Assert.That(failures, Is.Empty,
                "All Wasserstein cases should match scipy within tolerance:\n" +
                string.Join("\n", failures));
        }

        [Test]
        public void WassersteinCases_AtLeastTenCasesLoaded()
        {
            int count = 0;
            foreach (var _ in LoadCases()) count++;
            Assert.That(count, Is.GreaterThanOrEqualTo(10),
                "wasserstein-cases.json should contain at least 10 cases");
        }

        [Test]
        public void Wasserstein_AllZeroU_ReturnsZero()
        {
            double[] u = new double[10];  // all zeros
            double[] v = { 1, 2, 3, 4, 5, 4, 3, 2, 1, 0 };
            double   result = DeepWasserstein.Distance(u, v);
            Assert.That(result, Is.EqualTo(0.0),
                "Wasserstein.Distance should return 0.0 when u is all-zero (matches Python guard)");
        }

        [Test]
        public void Wasserstein_AllZeroV_ReturnsZero()
        {
            double[] u = { 1, 2, 3, 4, 5, 4, 3, 2, 1, 0 };
            double[] v = new double[10];  // all zeros
            double   result = DeepWasserstein.Distance(u, v);
            Assert.That(result, Is.EqualTo(0.0),
                "Wasserstein.Distance should return 0.0 when v is all-zero (matches Python guard)");
        }

        [Test]
        public void Wasserstein_NullInputs_ReturnZero()
        {
            Assert.That(DeepWasserstein.Distance(null, null), Is.EqualTo(0.0));
            Assert.That(DeepWasserstein.Distance(new double[5], null), Is.EqualTo(0.0));
            Assert.That(DeepWasserstein.Distance(null, new double[5]), Is.EqualTo(0.0));
        }
    }
}

// PolyfitVsNumpyParityTests: verifies DeepMath.Fit1 matches numpy.polyfit(x, y, 1)
// to within 1e-9 tolerance on a set of pre-committed cases.
//
// Cases generated offline via Python (numpy.polyfit) and committed as static JSON.
// No Python runtime required in CI — pure C# assertion against pre-computed expected values.
//
// Python reference: numpy.polyfit(numpy.arange(len(y)), y, 1)
// C# reference: DeepMath.Fit1(IReadOnlyList<double> y) — implicit x = 0..n-1

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using NUnit.Framework;
using DeepMath = NinjaTrader.NinjaScript.AddOns.DEEP6.Math.LeastSquares;

namespace NinjaTrader.Tests.Parity
{
    [TestFixture]
    public class PolyfitVsNumpyParityTests
    {
        private static string FixturePath() =>
            Path.Combine(TestContext.CurrentContext.TestDirectory,
                "Parity", "fixtures", "polyfit-cases.json");

        private struct PolyfitCase
        {
            public string description;
            public double[] y;
            public double expectedSlope;
            public double expectedIntercept;
        }

        private static IEnumerable<PolyfitCase> LoadCases()
        {
            string json = File.ReadAllText(FixturePath());
            using var doc = JsonDocument.Parse(json);
            foreach (var elem in doc.RootElement.EnumerateArray())
            {
                var c = new PolyfitCase
                {
                    description       = elem.GetProperty("description").GetString(),
                    expectedSlope     = elem.GetProperty("expectedSlope").GetDouble(),
                    expectedIntercept = elem.GetProperty("expectedIntercept").GetDouble(),
                };
                var yArr = elem.GetProperty("y");
                var yList = new List<double>();
                foreach (var v in yArr.EnumerateArray()) yList.Add(v.GetDouble());
                c.y = yList.ToArray();
                yield return c;
            }
        }

        [Test]
        public void PolyfitCases_AllMatchNumpyWithin1e9()
        {
            const double tolerance = 1e-9;
            int count = 0;
            var failures = new List<string>();

            foreach (var c in LoadCases())
            {
                count++;
                var fit = DeepMath.Fit1((IReadOnlyList<double>)c.y);

                double slopeDiff     = System.Math.Abs(fit.Slope     - c.expectedSlope);
                double interceptDiff = System.Math.Abs(fit.Intercept - c.expectedIntercept);

                // For very small values (1e-8 scale), use relative tolerance
                double slopeTol = System.Math.Max(tolerance, System.Math.Abs(c.expectedSlope) * 1e-9);
                double intTol   = System.Math.Max(tolerance, System.Math.Abs(c.expectedIntercept) * 1e-9);

                bool slopeOk     = slopeDiff     <= slopeTol;
                bool interceptOk = interceptDiff <= intTol;

                if (!slopeOk || !interceptOk)
                {
                    failures.Add(string.Format(
                        "Case '{0}': slope diff={1:E3} (tol={2:E3}), intercept diff={3:E3} (tol={4:E3})",
                        c.description, slopeDiff, slopeTol, interceptDiff, intTol));
                }
            }

            Assert.That(count, Is.GreaterThanOrEqualTo(10),
                "Should have at least 10 polyfit parity cases");

            Assert.That(failures, Is.Empty,
                "All polyfit cases should match numpy.polyfit within tolerance:\n" +
                string.Join("\n", failures));
        }

        [Test]
        public void Fit1_NullAndEdgeCases_DoNotThrow()
        {
            // n=0: empty list
            var r0 = DeepMath.Fit1(new double[0]);
            Assert.That(r0.Slope,     Is.EqualTo(0.0), "n=0 slope should be 0");
            Assert.That(r0.Intercept, Is.EqualTo(0.0), "n=0 intercept should be 0");

            // n=1: single element
            var r1 = DeepMath.Fit1(new double[] { 42.0 });
            Assert.That(r1.Slope,     Is.EqualTo(0.0),  "n=1 slope should be 0");
            Assert.That(r1.Intercept, Is.EqualTo(42.0), "n=1 intercept should equal y[0]");

            // All-zero y: slope=0, intercept=0
            var r2 = DeepMath.Fit1(new double[] { 0, 0, 0, 0, 0 });
            Assert.That(r2.Slope, Is.EqualTo(0.0), "all-zero y should give slope=0");
        }

        [Test]
        public void PolyfitCases_AtLeastTenCasesLoaded()
        {
            int count = 0;
            foreach (var _ in LoadCases()) count++;
            Assert.That(count, Is.GreaterThanOrEqualTo(10),
                "polyfit-cases.json should contain at least 10 cases");
        }
    }
}

// LeastSquaresTests: validates LeastSquares.Fit1 against hand-computed expected values.
// Verifies numpy.polyfit(arange(n), y, 1) equivalence at double precision.
//
// Python reference: numpy.polyfit([0,1,2,3,4], y, 1) hand-computed results.

using NUnit.Framework;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Math;

namespace NinjaTrader.Tests.Math
{
    [TestFixture]
    public class LeastSquaresTests
    {
        private const double Tol = 1e-9;

        /// <summary>y = [1,2,3,4,5]: slope=1, intercept=1. numpy.polyfit([0..4],[1..5],1) = [1,1].</summary>
        [Test]
        public void Fit1_IncreasingSequence_ReturnsSlope1_Intercept1()
        {
            double[] y = { 1, 2, 3, 4, 5 };
            var fit = LeastSquares.Fit1(y);
            Assert.That(fit.Slope,     Is.EqualTo(1.0).Within(Tol), "Slope should be 1.0");
            Assert.That(fit.Intercept, Is.EqualTo(1.0).Within(Tol), "Intercept should be 1.0");
        }

        /// <summary>y = [5,4,3,2,1]: slope=-1, intercept=5. numpy.polyfit([0..4],[5..1],1) = [-1,5].</summary>
        [Test]
        public void Fit1_DecreasingSequence_ReturnsSlopeMinus1_Intercept5()
        {
            double[] y = { 5, 4, 3, 2, 1 };
            var fit = LeastSquares.Fit1(y);
            Assert.That(fit.Slope,     Is.EqualTo(-1.0).Within(Tol), "Slope should be -1.0");
            Assert.That(fit.Intercept, Is.EqualTo(5.0).Within(Tol),  "Intercept should be 5.0");
        }

        /// <summary>y = [1,1,1,1,1]: slope=0, intercept=1. Flat constant series.</summary>
        [Test]
        public void Fit1_ConstantSeries_ReturnsSlope0_Intercept1()
        {
            double[] y = { 1, 1, 1, 1, 1 };
            var fit = LeastSquares.Fit1(y);
            Assert.That(fit.Slope,     Is.EqualTo(0.0).Within(Tol), "Slope should be 0.0 for constant series");
            Assert.That(fit.Intercept, Is.EqualTo(1.0).Within(Tol), "Intercept should be 1.0 for constant series");
        }

        /// <summary>n=1 edge case: returns slope=0, intercept=y[0].</summary>
        [Test]
        public void Fit1_SingleElement_ReturnsSafeDefaults()
        {
            double[] y = { 42.5 };
            var fit = LeastSquares.Fit1(y);
            Assert.That(fit.Slope,     Is.EqualTo(0.0).Within(Tol));
            Assert.That(fit.Intercept, Is.EqualTo(42.5).Within(Tol));
        }

        /// <summary>n=0 edge case: returns slope=0, intercept=0.</summary>
        [Test]
        public void Fit1_EmptyArray_ReturnsSafeDefaults()
        {
            double[] y = { };
            var fit = LeastSquares.Fit1(y);
            Assert.That(fit.Slope,     Is.EqualTo(0.0).Within(Tol));
            Assert.That(fit.Intercept, Is.EqualTo(0.0).Within(Tol));
        }

        /// <summary>
        /// Explicit x array: x=[0,1,2,3,4], y=[2,4,6,8,10]: slope=2, intercept=2.
        /// numpy.polyfit([0,1,2,3,4],[2,4,6,8,10],1) = [2.0, 2.0].
        /// </summary>
        [Test]
        public void Fit1_ExplicitX_MatchesNumpyPolyfit()
        {
            double[] x = { 0, 1, 2, 3, 4 };
            double[] y = { 2, 4, 6, 8, 10 };
            var fit = LeastSquares.Fit1(x, y);
            Assert.That(fit.Slope,     Is.EqualTo(2.0).Within(Tol));
            Assert.That(fit.Intercept, Is.EqualTo(2.0).Within(Tol));
        }
    }
}

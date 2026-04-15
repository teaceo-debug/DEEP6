// LeastSquares: hand-rolled 1st-order polynomial fit (slope, intercept).
//
// Python reference: numpy.polyfit(x, y, 1) — closed form for degree=1.
// Consumers: DELT-10 (CVD polyfit divergence), EXH-05 (CVD slope), TRAP-05 (CVD trend reversal).
//
// Numerical stability (RESEARCH.md §Pattern 4):
//   For n=2..20 bars (typical window), sxx fits exactly in double precision.
//   For integer x = 0..n-1, denominator = n*sxx - sx*sx is always >= 1 when n >= 2.
//   Guard: n < 2 returns slope=0, intercept=y[0].
//
// CRITICAL: No NinjaTrader.* using directives.

using System;
using System.Collections.Generic;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Math
{
    /// <summary>
    /// Hand-rolled 1st-order ordinary least squares, matching numpy.polyfit(x, y, 1).
    ///
    /// Formula:
    ///   slope     = (n*sxy - sx*sy) / (n*sxx - sx*sx)
    ///   intercept = (sy - slope*sx) / n
    /// where x = 0, 1, 2, ..., n-1 (same as numpy arange(n)).
    ///
    /// Python reference: numpy.polyfit(x, y, 1) — QR decomposition internally,
    ///   but matches closed form to 14 significant figures for n &lt;= 20. [VERIFIED: RESEARCH.md §Pattern 4]
    /// </summary>
    public static class LeastSquares
    {
        /// <summary>Result of a 1st-order polynomial fit.</summary>
        public struct Fit
        {
            public double Slope;
            public double Intercept;
        }

        /// <summary>
        /// Fit y values with implicit x = 0, 1, ..., n-1 (the common case for time series).
        ///
        /// Matches numpy.polyfit(numpy.arange(len(y)), y, 1).
        /// Returns Slope=0, Intercept=y[0] for n &lt; 2.
        /// </summary>
        public static Fit Fit1(IReadOnlyList<double> y)
        {
            int n = y.Count;
            if (n < 2) return new Fit { Slope = 0.0, Intercept = n > 0 ? y[0] : 0.0 };

            // x = 0, 1, ..., n-1 — use closed-form sums to avoid floating-point accumulation
            // sum(i)    = n*(n-1)/2
            // sum(i^2)  = n*(n-1)*(2n-1)/6
            double sx  = (double)n * (n - 1) * 0.5;
            double sxx = (double)n * (n - 1) * (2 * n - 1) / 6.0;

            double sy = 0.0, sxy = 0.0;
            for (int i = 0; i < n; i++)
            {
                sy  += y[i];
                sxy += i * y[i];
            }

            double denom = n * sxx - sx * sx;
            // denom cannot be 0 for integer x = 0..n-1 with n >= 2.
            // Guard against degenerate edge cases anyway.
            if (System.Math.Abs(denom) < 1e-12)
                return new Fit { Slope = 0.0, Intercept = sy / n };

            double slope     = (n * sxy - sx * sy) / denom;
            double intercept = (sy - slope * sx) / n;
            return new Fit { Slope = slope, Intercept = intercept };
        }

        /// <summary>
        /// Fit y values with explicit x array. Must have x.Length == y.Length.
        /// Returns Slope=0, Intercept=y[0] for n &lt; 2.
        /// </summary>
        public static Fit Fit1(double[] x, double[] y)
        {
            if (x == null || y == null) throw new ArgumentNullException();
            int n = System.Math.Min(x.Length, y.Length);
            if (n < 2) return new Fit { Slope = 0.0, Intercept = n > 0 ? y[0] : 0.0 };

            double sx = 0, sy = 0, sxy = 0, sxx = 0;
            for (int i = 0; i < n; i++)
            {
                sx  += x[i];
                sy  += y[i];
                sxy += x[i] * y[i];
                sxx += x[i] * x[i];
            }

            double denom = n * sxx - sx * sx;
            if (System.Math.Abs(denom) < 1e-12)
                return new Fit { Slope = 0.0, Intercept = sy / n };

            double slope     = (n * sxy - sx * sy) / denom;
            double intercept = (sy - slope * sx) / n;
            return new Fit { Slope = slope, Intercept = intercept };
        }
    }
}

// Wasserstein.cs: 1D Wasserstein-1 (Earth Mover's) distance.
//
// Python reference: scipy.stats.wasserstein_distance
//   Used by ENG-03 (CounterSpoofDetector) to measure DOM distribution shift.
//
// Algorithm (RESEARCH.md §ENG-03 Wasserstein port):
//   Given u_weights[] and v_weights[] (both length N, non-negative):
//     1. Normalize to PMF: u_pmf[i] = u_weights[i] / sum(u_weights)
//     2. Compute CDF difference: CDF_diff[i] = cumsum(u_pmf)[i] - cumsum(v_pmf)[i]
//     3. W1 = sum(|CDF_diff[i]|) for i in 0..N-1
//   This matches scipy.wasserstein_distance(positions, positions, u_weights, v_weights)
//   where positions = [0, 1, ..., N-1]. [CITED: RESEARCH.md §ENG-03 line ~483]
//
// Python guard match:
//   Python counter_spoof.py guards prev_sum == 0 → w1 = 0 and curr_sum == 0 → w1 = 0.
//   This file returns 0.0 whenever either input sums to 0. [VERIFIED: RESEARCH.md §Pitfall 5]
//
// CRITICAL: No NinjaTrader.* using directives.

using System;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6.Math
{
    /// <summary>
    /// 1D Wasserstein-1 (Earth Mover's Distance) for uniform position arrays.
    ///
    /// Python reference: scipy.stats.wasserstein_distance (counter_spoof.py ENG-03)
    /// Used by CounterSpoofDetector to quantify DOM bid/ask distribution shift.
    /// </summary>
    public static class Wasserstein
    {
        /// <summary>
        /// Compute 1D Wasserstein-1 distance between two weight distributions
        /// over positions [0, 1, ..., min(u.Length, v.Length) - 1].
        ///
        /// Returns 0.0 if either array sums to 0 (matches Python guard for empty DOM snapshots).
        ///
        /// Matches scipy.stats.wasserstein_distance to numerical precision for n &lt;= 40.
        /// </summary>
        /// <param name="u">First weight distribution (e.g. prior DOM bid sizes, non-negative).</param>
        /// <param name="v">Second weight distribution (e.g. current DOM bid sizes, non-negative).</param>
        public static double Distance(double[] u, double[] v)
        {
            if (u == null || v == null) return 0.0;
            int n = System.Math.Min(u.Length, v.Length);
            if (n == 0) return 0.0;

            double sumU = 0.0, sumV = 0.0;
            for (int i = 0; i < n; i++) { sumU += u[i]; sumV += v[i]; }

            // Guard: matches Python counter_spoof.py lines 128-140.
            // If either distribution is empty (all-zero DOM), W1 is undefined → return 0.
            if (sumU == 0.0 || sumV == 0.0) return 0.0;

            double w1 = 0.0, cdfU = 0.0, cdfV = 0.0;
            for (int i = 0; i < n; i++)
            {
                cdfU += u[i] / sumU;
                cdfV += v[i] / sumV;
                w1   += System.Math.Abs(cdfU - cdfV);
            }
            return w1;
        }
    }
}

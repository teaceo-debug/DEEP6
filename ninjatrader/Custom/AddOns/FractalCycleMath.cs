#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.AddOns;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
#endregion

namespace NinjaTrader.NinjaScript.AddOns
{
    public static class FractalCycleMath
    {
        // -- Williams Fractals (Trading Chaos, 1995) -----------------------
        // A bar at chronological index `probe` is an UP fractal of strength N
        // when it strictly exceeds N values on either side. Williams' classic
        // is N=2 (5-bar fractal). Larger N â†’ more selective swings.
        // Arrays are chronological: arr[0] = oldest, arr[length-1] = newest.
        
        public static bool IsUpFractalChrono(double[] highs, int probe, int n)
        {
            if (highs == null) return false;
            if (probe < n || probe + n >= highs.Length) return false;
            double pivot = highs[probe];
            for (int i = 1; i <= n; i++)
            {
                if (highs[probe - i] >= pivot) return false;
                if (highs[probe + i] >= pivot) return false;
            }
            return true;
        }
        
        public static bool IsDownFractalChrono(double[] lows, int probe, int n)
        {
            if (lows == null) return false;
            if (probe < n || probe + n >= lows.Length) return false;
            double pivot = lows[probe];
            for (int i = 1; i <= n; i++)
            {
                if (lows[probe - i] <= pivot) return false;
                if (lows[probe + i] <= pivot) return false;
            }
            return true;
        }
        
        // -- Dreiss Choppiness Index (CTCR 1992) ---------------------------
        //   CI = 100 * log10( sum(TR, N) / (Highest(High, N) - Lowest(Low, N)) ) / log10(N)
        //   > 61.8 â†’ consolidating; < 38.2 â†’ trending.
        
        public static double DreissChoppiness(double[] trueRanges, double highestHigh, double lowestLow, int n)
        {
            if (n < 2) return double.NaN;
            if (trueRanges == null || trueRanges.Length < n) return double.NaN;
            double trSum = 0;
            for (int i = 0; i < n; i++) trSum += trueRanges[i];
            double range = highestHigh - lowestLow;
            if (range <= 0 || trSum <= 0) return double.NaN;
            return 100.0 * Math.Log10(trSum / range) / Math.Log10(n);
        }
        
        public enum ChopRegime { Trending = -1, Transitional = 0, Consolidating = 1, Unknown = 2 }
        
        public static ChopRegime ClassifyChoppiness(double ci)
        {
            if (double.IsNaN(ci)) return ChopRegime.Unknown;
            if (ci > 61.8) return ChopRegime.Consolidating;
            if (ci < 38.2) return ChopRegime.Trending;
            return ChopRegime.Transitional;
        }
        
        // -- Hurst Exponent â€” Rescaled Range (Hurst 1951; Mandelbrot/Wallis 1969) --
        //   H â‰ˆ 0.5  â†’ random walk
        //   H > 0.5  â†’ persistent / trending
        //   H < 0.5  â†’ anti-persistent / mean-reverting
        
        public static double HurstRS(double[] series, int minChunk = 8, int maxChunk = -1)
        {
            if (series == null) return double.NaN;
            int N = series.Length;
            if (N < 16) return double.NaN;
            if (maxChunk <= 0) maxChunk = N / 2;
            if (maxChunk < minChunk) return double.NaN;
            
            var logN  = new List<double>();
            var logRS = new List<double>();
            
            for (int chunk = minChunk; chunk <= maxChunk; chunk *= 2)
            {
                int numChunks = N / chunk;
                if (numChunks < 1) break;
                double rsSum = 0;
                int counted = 0;
                for (int c = 0; c < numChunks; c++)
                {
                    double mean = 0;
                    int baseIdx = c * chunk;
                    for (int i = 0; i < chunk; i++) mean += series[baseIdx + i];
                    mean /= chunk;
                    
                    double cumDev = 0, maxDev = double.MinValue, minDev = double.MaxValue;
                    double sumSq = 0;
                    for (int i = 0; i < chunk; i++)
                    {
                        double d = series[baseIdx + i] - mean;
                        cumDev += d;
                        if (cumDev > maxDev) maxDev = cumDev;
                        if (cumDev < minDev) minDev = cumDev;
                        sumSq += d * d;
                    }
                    double R = maxDev - minDev;
                    double S = Math.Sqrt(sumSq / chunk);
                    if (R > 0 && S > 0) { rsSum += R / S; counted++; }
                }
                if (counted == 0) continue;
                double avgRS = rsSum / counted;
                logN.Add(Math.Log(chunk));
                logRS.Add(Math.Log(avgRS));
            }
            
            if (logN.Count < 2) return double.NaN;
            
            double sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
            int m = logN.Count;
            for (int i = 0; i < m; i++)
            {
                sumX  += logN[i];
                sumY  += logRS[i];
                sumXY += logN[i] * logRS[i];
                sumX2 += logN[i] * logN[i];
            }
            double denom = m * sumX2 - sumX * sumX;
            if (Math.Abs(denom) < 1e-12) return double.NaN;
            return (m * sumXY - sumX * sumY) / denom;
        }
        
        // -- Dominant Cycle Period â€” autocorrelation lag search -----------
        public static int DominantCyclePeriod(double[] returns, int minLag, int maxLag)
        {
            if (returns == null) return -1;
            int N = returns.Length;
            if (N < maxLag + 2) return -1;
            
            double mean = 0;
            for (int i = 0; i < N; i++) mean += returns[i];
            mean /= N;
            
            double var0 = 0;
            for (int i = 0; i < N; i++) { double d = returns[i] - mean; var0 += d * d; }
            var0 /= N;
            if (var0 <= 0) return -1;
            
            int bestLag = -1;
            double bestAcf = double.MinValue;
            for (int lag = minLag; lag <= maxLag; lag++)
            {
                double cov = 0;
                int countPairs = N - lag;
                for (int i = 0; i < countPairs; i++)
                    cov += (returns[i] - mean) * (returns[i + lag] - mean);
                cov /= countPairs;
                double acf = cov / var0;
                if (acf > bestAcf) { bestAcf = acf; bestLag = lag; }
            }
            return bestLag;
        }
        
        // -- Stats helpers ------------------------------------------------
        public static double Median(double[] arr)
        {
            if (arr == null || arr.Length == 0) return double.NaN;
            var copy = (double[])arr.Clone();
            Array.Sort(copy);
            int m = copy.Length / 2;
            return (copy.Length % 2 == 1) ? copy[m] : 0.5 * (copy[m - 1] + copy[m]);
        }
        
        public static double StdDev(double[] arr)
        {
            if (arr == null || arr.Length < 2) return double.NaN;
            double mean = 0;
            for (int i = 0; i < arr.Length; i++) mean += arr[i];
            mean /= arr.Length;
            double s = 0;
            for (int i = 0; i < arr.Length; i++) { double d = arr[i] - mean; s += d * d; }
            return Math.Sqrt(s / (arr.Length - 1));
        }
    }
}

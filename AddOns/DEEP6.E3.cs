#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
using System.Windows.Threading;
using SharpDX.Direct2D1;
using SharpDX.DirectWrite;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;
using WBrush  = System.Windows.Media.SolidColorBrush;
using WColor  = System.Windows.Media.Color;
using WColors = System.Windows.Media.Colors;
using WFont   = System.Windows.Media.FontFamily;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class DEEP6
    {
        private struct LgEntry { public DateTime ts; public int lv; public bool bid; }

        #region E3 Private Fields
        private double _w1, _spSc; private string _spSt = "---"; private int _spEvt;
        private const int LG_CAP = 1024;
        private readonly LgEntry[] _pLgBuf = new LgEntry[LG_CAP];
        private int _pLgHead, _pLgCount;
        #endregion

        #region E3 CounterSpoof
        private void RunE3()
        {
            if (_iLong.Count < 5) return;
            QueueStats(_iLong, out double mL, out double sL);
            double mS, sS;
            if (_iShort.Count > 1) QueueStats(_iShort, out mS, out sS);
            else { mS = mL; sS = sL; }
            _w1 = Math.Abs(mS - mL) + Math.Abs(sS - sL);
            // Evict stale large-order entries from circular buffer (no RemoveAll — O(1) per entry)
            DateTime cutoff = DateTime.Now.AddSeconds(-10);
            while (_pLgCount > 0)
            {
                int tail = (_pLgHead - _pLgCount + LG_CAP) % LG_CAP;
                if (_pLgBuf[tail].ts < cutoff) _pLgCount--;
                else break;
            }
            double w1n = Math.Min(_w1 / 0.8, 1.0), spn = Math.Min(_spEvt / 5.0, 1.0);
            _spSc = Math.Min((w1n * 0.6 + spn * 0.4) * MX_SP, MX_SP);
            _spSt = _w1.ToString("0.00") + (_w1 < SpooW1 ? " OK" : " !");
        }
        private void ChkSpoof(int lv, bool bid)
        {
            var cw = TimeSpan.FromMilliseconds(SpooCancelMs);
            DateTime now = DateTime.Now;
            // Search circular buffer for matching large order within cancel window
            for (int i = 0; i < _pLgCount; i++)
            {
                int idx = (_pLgHead - _pLgCount + i + LG_CAP) % LG_CAP;
                ref LgEntry e = ref _pLgBuf[idx];
                if (e.lv == lv && e.bid == bid && (now - e.ts) < cw)
                {
                    _spEvt++;
                    // Remove by swapping with tail and decrementing count
                    int tail = (_pLgHead - _pLgCount + LG_CAP) % LG_CAP;
                    _pLgBuf[idx] = _pLgBuf[tail];
                    _pLgCount--;
                    break;
                }
            }
        }
        // Zero-allocation mean/std using foreach over Queue<double> — no ToArray, no LINQ
        private static void QueueStats(Queue<double> q, out double mean, out double std)
        {
            int n = q.Count;
            if (n == 0) { mean = 0; std = 0; return; }
            double sum = 0;
            foreach (double v in q) sum += v;
            mean = sum / n;
            if (n < 2) { std = 0; return; }
            double ssq = 0;
            foreach (double v in q) ssq += (v - mean) * (v - mean);
            std = Math.Sqrt(ssq / (n - 1));
        }
        #endregion
    }
}

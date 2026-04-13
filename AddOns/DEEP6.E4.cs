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
        #region E4 Private Fields
        private int _icBull, _icBear; private double _icSc; private int _icDir; private string _icSt = "---";
        private struct TrEntry { public DateTime ts; public double px; public bool buy; }
        private const int TR_CAP = 1024;
        private readonly TrEntry[] _pTrBuf = new TrEntry[TR_CAP];
        private int _pTrHead, _pTrCount;
        #endregion

        #region E4 Iceberg
        private void RunE4(double px, double qty, bool isAsk)
        {
            bool buy = !isAsk;
            int lv = buy ? LvPx(px, false) : LvPx(px, true);
            double disp = lv >= 0 ? (buy ? _aV[lv] : _bV[lv]) : 0;
            if (disp > 0 && qty > disp * 1.5)
            {
                if (buy) { _icBull++; _icSt = "BULL @" + px.ToString("0.00"); }
                else     { _icBear++; _icSt = "BEAR @" + px.ToString("0.00"); }
            }
            // Synthetic iceberg: check circular buffer for matching recent trade (no RemoveAll)
            DateTime now = DateTime.Now;
            TimeSpan iceWin = TimeSpan.FromMilliseconds(IceMs);
            for (int i = 0; i < _pTrCount; i++)
            {
                int idx = (_pTrHead - _pTrCount + i + TR_CAP) % TR_CAP;
                ref TrEntry t = ref _pTrBuf[idx];
                if ((now - t.ts) > iceWin) continue;           // stale — skip (FIFO, so break is unsafe; continue is correct)
                if (Math.Abs(t.px - px) < TickSize * 0.5 && t.buy == buy)
                { if (buy) _icBull++; else _icBear++; break; }
            }
            // Add current trade to circular buffer
            _pTrBuf[_pTrHead] = new TrEntry { ts = now, px = px, buy = buy };
            _pTrHead = (_pTrHead + 1) % TR_CAP;
            if (_pTrCount < TR_CAP) _pTrCount++;
            // Evict entries older than IceMs from the tail
            TimeSpan cutoff = TimeSpan.FromMilliseconds(IceMs);
            while (_pTrCount > 0)
            {
                int tail = (_pTrHead - _pTrCount + TR_CAP) % TR_CAP;
                if ((now - _pTrBuf[tail].ts) > cutoff) _pTrCount--;
                else break;
            }
            int tot = _icBull + _icBear;
            if (tot > 0)
            { double im = (double)(_icBull - _icBear) / tot;
              _icSc = Math.Abs(im) * MX_IC; _icDir = Math.Sign(_icBull - _icBear); }
        }
        private int LvPx(double px, bool bid)
        { for (int i = 0; i < DDEPTH; i++) if (Math.Abs((bid ? _bP[i] : _aP[i]) - px) < TickSize * 0.5) return i; return -1; }
        #endregion
    }
}

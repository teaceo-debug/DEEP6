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
        #region E2 Private Fields
        private readonly double[] _bV = new double[10], _aV = new double[10];
        private readonly double[] _bP = new double[10], _aP = new double[10];
        private double _imb, _imbEma, _pUp, _trSc; private int _trDir; private string _trSt = "---";
        private readonly Queue<double> _iLong = new Queue<double>(62), _iShort = new Queue<double>(12);
        #endregion

        #region E2 Trespass
        private void RunE2()
        {
            int lvs = Math.Min(DomDepth, DDEPTH); double sb=0, sa=0;
            for (int k=0; k<lvs; k++) { double w=Math.Exp(-Lambda*k); sb+=w*_bV[k]; sa+=w*_aV[k]; }
            double den = sb+sa; _imb = den>0 ? (sb-sa)/den : 0.0;
            double a = 2.0/(TressEma+1);
            _imbEma = _imbEma==0 ? _imb : _imbEma*(1-a)+_imb*a;
            _pUp = 1.0/(1.0+Math.Exp(-LBeta*_imbEma));
            _trSc = Math.Abs(_imbEma)*MX_TR;
            _trDir = _imbEma>0.05 ? +1 : _imbEma<-0.05 ? -1 : 0;
            _trSt = _imbEma.ToString("+0.00;-0.00;+0.00");
            _iLong.Enqueue(_imb);  if (_iLong.Count>SpooLong)  _iLong.Dequeue();
            _iShort.Enqueue(_imb); if (_iShort.Count>SpooShort) _iShort.Dequeue();
        }
        #endregion
    }
}

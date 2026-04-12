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
        #region E5 Private Fields
        private double _pBull = .5, _pBear = .5, _miSc; private int _miDir; private string _miSt = "---";
        #endregion

        #region E5 Micro
        private void RunE5()
        {
            double lF=_fpDir==+1?.75:_fpDir==-1?.25:.5;
            double lT=_trDir==+1?_pUp:_trDir==-1?1-_pUp:.5;
            double lI=_icDir==+1?.70:_icDir==-1?.30:.5;
            double lC=_cvd>0?.65:_cvd<0?.35:.5;
            double pBu=.5*lF*lT*lI*lC, pBe=.5*(1-lF)*(1-lT)*(1-lI)*(1-lC);
            double Z=pBu+pBe; _pBull=Z>0?pBu/Z:.5; _pBear=1-_pBull;
            _miSc=Math.Abs(_pBull-.5)*2.0*MX_MI; _miDir=_pBull>.5?+1:-1;
            _miSt="L:"+(int)Math.Round(_pBull*100)+" S:"+(int)Math.Round(_pBear*100);
        }
        #endregion
    }
}

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
        private readonly List<(DateTime ts, double px, bool buy)> _pTr = new List<(DateTime, double, bool)>();
        #endregion

        #region E4 Iceberg
        private void RunE4(double px, double qty, bool isAsk)
        {
            bool buy=!isAsk; int lv=buy?LvPx(px,false):LvPx(px,true);
            double disp=lv>=0?(buy?_aV[lv]:_bV[lv]):0;
            if (disp>0&&qty>disp*1.5)
            { if(buy){_icBull++;_icSt="BULL @"+px.ToString("0.00");}
              else   {_icBear++;_icSt="BEAR @"+px.ToString("0.00");} }
            _pTr.RemoveAll(t=>(DateTime.Now-t.ts).TotalMilliseconds>IceMs);
            foreach (var t in _pTr)
                if (Math.Abs(t.px-px)<TickSize*0.5&&t.buy==buy){if(buy)_icBull++;else _icBear++;break;}
            _pTr.Add((DateTime.Now,px,buy));
            int tot=_icBull+_icBear;
            if(tot>0){double im=(double)(_icBull-_icBear)/tot;_icSc=Math.Abs(im)*MX_IC;_icDir=Math.Sign(_icBull-_icBear);}
        }
        private int LvPx(double px,bool bid)
        { for(int i=0;i<DDEPTH;i++)if(Math.Abs((bid?_bP[i]:_aP[i])-px)<TickSize*0.5)return i;return -1;}
        #endregion
    }
}

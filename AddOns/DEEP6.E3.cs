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
        #region E3 Private Fields
        private double _w1, _spSc; private string _spSt = "---"; private int _spEvt;
        private readonly List<(DateTime ts, int lv, bool bid)> _pLg = new List<(DateTime, int, bool)>();
        #endregion

        #region E3 CounterSpoof
        private void RunE3()
        {
            if (_iLong.Count < 5) return;
            double mL=_iLong.Average(), mS=_iShort.Count>0?_iShort.Average():mL;
            double sL=Std(_iLong), sS=_iShort.Count>1?Std(_iShort):sL;
            _w1 = Math.Abs(mS-mL)+Math.Abs(sS-sL);
            _pLg.RemoveAll(o=>(DateTime.Now-o.ts).TotalSeconds>10);
            double w1n=Math.Min(_w1/0.8,1.0), spn=Math.Min(_spEvt/5.0,1.0);
            _spSc = Math.Min((w1n*0.6+spn*0.4)*MX_SP, MX_SP);
            _spSt = _w1.ToString("0.00")+(_w1<SpooW1 ? " OK" : " !");
        }
        private void ChkSpoof(int lv, bool bid)
        { var cw=TimeSpan.FromMilliseconds(SpooCancelMs);
          var m=_pLg.FirstOrDefault(o=>o.lv==lv&&o.bid==bid&&(DateTime.Now-o.ts)<cw);
          if (m.ts!=default){_spEvt++;_pLg.Remove(m);} }
        private static double Std(IEnumerable<double> v)
        { var a=v.ToArray(); if(a.Length<2)return 0; double m=a.Average();
          return Math.Sqrt(a.Sum(x=>(x-m)*(x-m))/(a.Length-1)); }
        #endregion
    }
}

#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
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
        #region E7 Private Fields
        private double[] _kSt = {0,0}; private double[,] _kP = {{1,0},{0,1}};
        private double _kVel, _mlSc; private string _mlSt = "---";
        private readonly Queue<double> _mlH = new Queue<double>(21);
        #endregion

        #region E7 ML Quality
        private void RunE7()
        {
            if (CurrentBar<5) return;
            double z=Close[0],dt=1.0;
            double p00=_kP[0,0]+dt*(_kP[1,0]+_kP[0,1])+dt*dt*_kP[1,1]+.01;
            double p01=_kP[0,1]+dt*_kP[1,1],p10=_kP[1,0]+dt*_kP[1,1],p11=_kP[1,1]+.001;
            double xP0=_kSt[0]+_kSt[1]*dt,xP1=_kSt[1];
            double R=!double.IsNaN(_emaRng)&&_emaRng>0?_emaRng*.1:1.0;
            double S=p00+R,k0=p00/S,k1=p10/S,inn=z-xP0;
            _kSt[0]=xP0+k0*inn;_kSt[1]=xP1+k1*inn;
            _kP[0,0]=(1-k0)*p00;_kP[0,1]=(1-k0)*p01;_kP[1,0]=p10-k1*p00;_kP[1,1]=p11-k1*p01;
            _kVel=_kSt[1];
            double[] w={.28,.22,.18,.12,-.10,.15,.08,.12};
            double[] x={_imbEma,_fpSc/MX_FP,_icSc/MX_IC,_pBull,Math.Min(_w1/.8,1.0),
                Math.Min(Math.Abs(_cvd)/(Math.Max(!double.IsNaN(_emaVol)?_emaVol:1,1)*20),1.0),
                GexReg==GexRegime.NegativeAmplifying?1.0:0.0,
                Math.Max(Math.Min(_kVel/(TickSize*10),1.0),-1.0)};
            double dot = 0.0;
            for (int i = 0; i < w.Length; i++) dot += w[i] * x[i];
            double logit = dot + 0.5;
            double qP = 1.0 / (1.0 + Math.Exp(-logit));
            _mlSc=qP*10; _mlH.Enqueue(qP); if(_mlH.Count>20)_mlH.Dequeue();
            double bsl;
            if (_mlH.Count > 0)
            {
                double sum = 0.0;
                foreach (double v in _mlH) sum += v;
                bsl = sum / _mlH.Count;
            }
            else bsl = qP;
            double dev=bsl>0?(qP-bsl)/bsl*100:0;
            _mlSt="P="+qP.ToString("0.00")+(dev>=0?"+":"")+dev.ToString("0")+"%";
        }
        #endregion
    }
}

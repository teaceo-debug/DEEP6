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
        #region E1 Private Fields
        private double _fpSc, _fpDir; private string _fpSt = "QUIET";
        private double _cvd, _emaVol = double.NaN, _emaRng = double.NaN;
        private int _stkTier; private bool _stkBull;
        private readonly Queue<double> _dQ = new Queue<double>(6);
        private NinjaTrader.NinjaScript.Indicators.EMA _ema20;
        #endregion

        #region E1 Footprint
        private void RunE1()
        {
            _fpSc = 0; _fpDir = 0; _fpSt = "QUIET"; _stkTier = 0;
            bool isV = BarsArray[0].BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            var vb = isV ? BarsArray[0].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType : null;
            double delta = 0, vol = Volume[0];
            if (vb != null) { var V = vb.Volumes[CurrentBar]; delta = V.BarDelta; vol = V.TotalVolume; }
            _dQ.Enqueue(delta); if (_dQ.Count > 5) _dQ.Dequeue();
            double cumD = _dQ.Sum(), rng = High[0]-Low[0];
            _cvd += delta;
            _emaVol = double.IsNaN(_emaVol) ? vol : _emaVol*0.95+vol*0.05;
            _emaRng = double.IsNaN(_emaRng) ? rng : _emaRng*0.93+rng*0.07;
            double bTop = Math.Max(Open[0],Close[0]), bBot = Math.Min(Open[0],Close[0]);
            double uwV = rng>0 ? vol*(High[0]-bTop)/rng : 0;
            double lwV = rng>0 ? vol*(bBot-Low[0])/rng  : 0;
            double uwPct = vol>0 ? uwV/vol*100 : 0, lwPct = vol>0 ? lwV/vol*100 : 0;
            double eff = AbsorbWickMin * (_emaRng>0 && rng/_emaRng>1.5 ? 1.2 : 1.0);
            double uwR = uwV>0 ? Math.Abs(delta*0.1)/uwV : 1;
            double lwR = lwV>0 ? Math.Abs(delta*0.1)/lwV : 1;
            if (lwV>0 && lwPct>=eff && lwR<AbsorbDeltaMax) { _fpSc+=15; _fpDir=+1; _fpSt="ABSORBT"; }
            else if (uwV>0 && uwPct>=eff && uwR<AbsorbDeltaMax) { _fpSc+=15; _fpDir=-1; _fpSt="ABSORBB"; }

            if (vb != null)
            {
                int bMax=0, sMax=0, bSt=0, sSt=0;
                try
                { for (double p=Low[0]; p<High[0]; p+=TickSize)
                  { double ask=vb.Volumes[CurrentBar].GetAskVolumeForPrice(p+TickSize);
                    double bid=vb.Volumes[CurrentBar].GetBidVolumeForPrice(p);
                    if (ask>0 && bid>0)
                    { double r=ask/bid;
                      if (r>=ImbRatio)      { bSt++; bMax=Math.Max(bMax,bSt); sSt=0; }
                      else if(1/r>=ImbRatio){ sSt++; sMax=Math.Max(sMax,sSt); bSt=0; }
                      else { bSt=0; sSt=0; } } } }
                catch { }
                if (bMax>=StkT1) { _fpSc+=8; if(_fpDir>=0)_fpDir=+1; _stkBull=true; }
                if (sMax>=StkT1) { _fpSc+=8; if(_fpDir<=0)_fpDir=-1; _stkBull=false; }
                int mx = _stkBull ? bMax : sMax;
                _stkTier = mx>=StkT3 ? 3 : mx>=StkT2 ? 2 : mx>=StkT1 ? 1 : 0;
                try
                { if (vb.Volumes[CurrentBar].GetBidVolumeForPrice(Low[0])==0)  { _fpSc+=6; if(_fpDir==0)_fpDir=+1; }
                  if (vb.Volumes[CurrentBar].GetAskVolumeForPrice(High[0])==0) { _fpSc+=6; if(_fpDir==0)_fpDir=-1; } }
                catch { }
            }
            if (CurrentBar>5)
            { if (Close[0]<Close[5]&&cumD>0) { _fpSc+=7; if(_fpDir==0)_fpDir=+1; }
              if (Close[0]>Close[5]&&cumD<0) { _fpSc+=7; if(_fpDir==0)_fpDir=-1; } }
            if (!double.IsNaN(_emaVol)&&_emaVol>0)
            { double cr=Math.Abs(_cvd)/(_emaVol*20); _fpSc+=Math.Min(cr,1.0)*5;
              if (_fpDir==0) _fpDir = _cvd>0 ? +1 : -1; }
            _fpSc = Math.Min(_fpSc, MX_FP);
        }
        #endregion
    }
}

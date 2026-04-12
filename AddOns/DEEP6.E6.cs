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
        #region E6 Private Fields (session context state)
        private double _sVN, _sVD, _sVR, _vwap = double.NaN, _vsd, _vah, _val;
        private double _ibH = double.NaN, _ibL = double.NaN;
        private bool _ibDone, _ibConf; private IbType _ibTyp = IbType.Normal; private DateTime _ibEnd;
        private double _dPoc = double.NaN, _pPoc = double.NaN; private int _pocMB; private bool _pocMU;
        private DayType _dayTyp = DayType.Unknown; private DateTime _sOpen; private double _oPx;
        private double _iHi = double.NaN, _iLo = double.NaN;
        private double _vpSc; private bool _dexFired; private int _dexDir; private string _dexSt = "---";
        private VwapZone _vwapZ = VwapZone.AtVwap;
        #endregion

        #region E6 VP+CTX + DEX-ARRAY
        private void RunE6()
        {
            _vpSc=0; _dexFired=false; _dexDir=0; _dexSt="---";
            bool isV=BarsArray[0].BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            if (CurrentBar>=DexLB&&isV)
            { var vb=BarsArray[0].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
              if (vb!=null)
              { int bA=0,rA=0; double mn=!double.IsNaN(_emaVol)?_emaVol*0.05:100;
                for(int i=0;i<DexLB;i++){double d=vb.Volumes[CurrentBar-i].BarDelta;if(d>mn)bA++;else if(d<-mn)rA++;}
                if(bA==DexLB){_dexFired=true;_dexDir=+1;_dexSt="FIRED";_vpSc+=8;}
                else if(rA==DexLB){_dexFired=true;_dexDir=-1;_dexSt="FIRED";_vpSc+=8;} } }
            if (!double.IsNaN(_vwap)&&_vsd>0)
            { double prox=VwapProxTks*TickSize;
              if(Math.Abs(Close[0]-_vah)<prox||Math.Abs(Close[0]-_val)<prox)_vpSc+=8;
              else if(Math.Abs(Close[0]-_vwap)<prox*.5)_vpSc+=5; }
            if (_ibDone){_vpSc+=Close[0]>_ibH||Close[0]<_ibL?6:2;if(_ibConf)_vpSc+=2;}
            if (_pocMB>=5)_vpSc+=5;
            switch(GexReg){case GexRegime.NegativeAmplifying:_vpSc+=4;break;case GexRegime.NegativeStable:_vpSc+=2;break;}
            if(_stkTier==3)_vpSc+=6;else if(_stkTier==2)_vpSc+=4;else if(_stkTier==1)_vpSc+=2;
            _vpSc=Math.Min(_vpSc,MX_VP);
        }
        #endregion
    }
}

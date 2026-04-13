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
        #region Event Handlers
        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1 || CurrentBar < BarsRequiredToPlot) return;
            if (Bars.IsFirstBarOfSession) SessionReset();
            UpdateSession();
            RunE1(); RunE3(); RunE5(); RunE6(); RunE7(); Scorer();
            Values[0][0] = _total; Values[1][0] = _imbEma;
            if (_sigTyp >= SignalType.TypeB && _lastSig != Time[0])
            { _lastSig = Time[0]; MakeSigLabel(); PushFeed(); }
            if (ShowLvls)  DrawLevels();
            if (ShowPanel) UpdatePanel();
        }

        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            if (e.Position >= DDEPTH) return;
            int lv = e.Position;
            if (e.MarketDataType == MarketDataType.Bid)
            {
                if (e.Operation != Operation.Remove)
                { _bP[lv] = e.Price; _bV[lv] = e.Volume;
                  if (e.Volume >= SpooQty && lv >= 2)
                  { _pLgBuf[_pLgHead] = new LgEntry { ts = DateTime.Now, lv = lv, bid = true };
                    _pLgHead = (_pLgHead + 1) % LG_CAP; if (_pLgCount < LG_CAP) _pLgCount++; } }
                else { ChkSpoof(lv, true); _bV[lv] = 0; }
            }
            else
            {
                if (e.Operation != Operation.Remove)
                { _aP[lv] = e.Price; _aV[lv] = e.Volume;
                  if (e.Volume >= SpooQty && lv >= 2)
                  { _pLgBuf[_pLgHead] = new LgEntry { ts = DateTime.Now, lv = lv, bid = false };
                    _pLgHead = (_pLgHead + 1) % LG_CAP; if (_pLgCount < LG_CAP) _pLgCount++; } }
                else { ChkSpoof(lv, false); _aV[lv] = 0; }
            }
            RunE2();
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        { if (e.MarketDataType == MarketDataType.Last) RunE4(e.Price, e.Volume, e.IsAsk); }
        #endregion

        #region Session Context
        private void SessionReset()
        {
            _sVN = _sVD = _sVR = 0; _vwap = Close[0]; _vsd = 0;
            _ibH = High[0]; _ibL = Low[0]; _ibDone = _ibConf = false;
            _sOpen = Time[0]; _oPx = Open[0]; _ibEnd = _sOpen.AddMinutes(IbMins);
            _dPoc = _pPoc = double.NaN; _pocMB = 0;
            _dayTyp = DayType.Unknown; _iHi = High[0]; _iLo = Low[0];
            _cvd = 0; _dexFired = false; _icBull = _icBear = 0;
        }

        private void UpdateSession()
        {
            double mid = (High[0]+Low[0]+Close[0])/3.0, v = Volume[0];
            _sVN += mid*v; _sVD += v;
            if (_sVD > 0)
            { _vwap = _sVN/_sVD; _sVR += v*Math.Pow(mid-_vwap,2);
              _vsd = Math.Sqrt(_sVR/_sVD); _vah = _vwap+_vsd; _val = _vwap-_vsd; }
            _iHi = double.IsNaN(_iHi) ? High[0] : Math.Max(_iHi, High[0]);
            _iLo = double.IsNaN(_iLo) ? Low[0]  : Math.Min(_iLo, Low[0]);
            if (!_ibDone && Time[0] < _ibEnd)
            { _ibH = Math.Max(_ibH, High[0]); _ibL = Math.Min(_ibL, Low[0]); }
            else if (!_ibDone)
            { _ibDone = true;
              double r = _ibH-_ibL, a = AvgIbTks*TickSize;
              _ibTyp = r > a*1.3 ? IbType.Wide : r < a*0.7 ? IbType.Narrow : IbType.Normal; }
            if (_ibDone && !_ibConf && (Time[0]-_ibEnd).TotalMinutes > 30) _ibConf = true;

            bool isV = BarsArray[0].BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            if (isV)
            { var vb = BarsArray[0].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
              if (vb != null)
              { double cp = vb.Volumes[CurrentBar].PointOfControl;
                if (!double.IsNaN(_pPoc))
                { if      (cp > _pPoc+TickSize*0.5) { _pocMB = _pocMU ? _pocMB+1 : 1; _pocMU = true; }
                  else if (cp < _pPoc-TickSize*0.5) { _pocMB = !_pocMU ? _pocMB+1 : 1; _pocMU = false; }
                  else _pocMB = 0; }
                _dPoc = cp; _pPoc = cp; } }

            if (_dayTyp == DayType.Unknown && (Time[0]-_sOpen).TotalMinutes >= 30)
            { double m = Close[0]-_oPx;
              _dayTyp = m > TickSize*12 ? DayType.TrendBull :
                        m < -TickSize*12 ? DayType.TrendBear : DayType.BalanceDay; }

            if (_vsd > 0)
            { double d = Close[0]-_vwap;
              _vwapZ = d > 2*_vsd ? VwapZone.Above2Sd : d > _vsd ? VwapZone.Above1Sd :
                       d > 0.25*_vsd ? VwapZone.AboveVwap : d > -0.25*_vsd ? VwapZone.AtVwap :
                       d > -_vsd ? VwapZone.BelowVwap : d > -2*_vsd ? VwapZone.Below1Sd : VwapZone.Below2Sd; }
        }
        #endregion
    }
}

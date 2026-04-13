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
        #region Render Private Fields
        private SharpDX.Direct2D1.Brush _dxG, _dxR, _dxGo, _dxW, _dxGr, _dxO, _dxT, _dxC, _dxP, _dxBg, _dxCB, _dxCS, _dxBd;
        private SharpDX.DirectWrite.TextFormat _fC, _fS, _fL;
        private SharpDX.DirectWrite.Factory _dwF;
        private bool _dxOk;
        #endregion

        #region SharpDX Rendering
        protected override void OnRender(ChartControl cc, ChartScale cs)
        {
            base.OnRender(cc, cs);
            if (!_dxOk) InitDX();
            if (ShowFp)      RenderFP(cc, cs);
            if (ShowSigBox)  RenderSigBoxes(cc, cs);
            if (ShowStk)     RenderStk(cc, cs);
        }
        protected override void OnRenderTargetChanged() { DisposeDX(); }

        private void InitDX()
        {
            if (RenderTarget==null) return;
            try
            {
                SharpDX.Direct2D1.Brush B(float r,float g,float b,float a=1f)
                    =>new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,new SharpDX.Color4(r,g,b,a));
                _dxG  = B(0f,1f,.53f);    _dxR  = B(1f,.25f,.25f); _dxGo = B(1f,.84f,0f);
                _dxW  = B(.88f,.94f,1f,.9f); _dxGr = B(.5f,.56f,.7f,.8f);
                _dxO  = B(1f,.58f,0f);    _dxT  = B(0f,.83f,.67f); _dxC  = B(.35f,.78f,.98f);
                _dxP  = B(.61f,.35f,.71f); _dxBg = B(.04f,.05f,.09f,.92f);
                _dxCB = B(0f,.31f,.16f,.65f); _dxCS = B(.31f,0f,0f,.65f);
                _dxBd = B(1f,.84f,0f,.9f);
                _dwF  = new SharpDX.DirectWrite.Factory();
                _fC   = new TextFormat(_dwF,"Consolas",8f){WordWrapping=WordWrapping.NoWrap};
                _fS   = new TextFormat(_dwF,"Consolas",7f){WordWrapping=WordWrapping.NoWrap};
                _fL   = new TextFormat(_dwF,"Consolas",9f){WordWrapping=WordWrapping.NoWrap,FontWeight=SharpDX.DirectWrite.FontWeight.Bold};
                _dxOk = true;
            }
            catch { _dxOk=false; }
        }

        private void DisposeDX()
        {
            _dxOk=false;
            void D<T>(ref T x) where T:class,IDisposable{if(x!=null){try{x.Dispose();}catch{}x=null;}}
            D(ref _dxG);D(ref _dxR);D(ref _dxGo);D(ref _dxW);D(ref _dxGr);D(ref _dxO);
            D(ref _dxT);D(ref _dxC);D(ref _dxP);D(ref _dxBg);D(ref _dxCB);D(ref _dxCS);D(ref _dxBd);
            D(ref _fC);D(ref _fS);D(ref _fL);D(ref _dwF);
        }

        private static string FV(double v)=>v>=1000?(v/1000).ToString("0.0")+"K":v.ToString("0");
        private string FC(double p){int w=(int)p;string s=(w%100).ToString();return s.Length==1?"0"+s:s;}

        private void RenderFP(ChartControl cc, ChartScale cs)
        {
            if (!_dxOk||RenderTarget==null) return;
            bool isV=BarsArray[0].BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            if (!isV) return;
            var vb=BarsArray[0].BarsType as NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
            if (vb==null) return;
            int first=ChartBars.FromIndex, last=Math.Min(CurrentBar,ChartBars.ToIndex);
            for (int bi=first; bi<=last; bi++)
            {
                float xL=(float)cc.GetXByBarIndex(ChartBars,bi);
                float bW=(float)cc.GetBarPaintWidth(ChartBars)-1f;
                if (bW<4) continue;
                double hi=Highs[0].GetValueAt(bi), lo=Lows[0].GetValueAt(bi);
                double poc=vb.Volumes[bi].PointOfControl;
                long   del=vb.Volumes[bi].BarDelta;
                for (double price=lo; price<=hi+TickSize*.1; price+=TickSize)
                {
                    float yT=(float)cs.GetYByValue(price+TickSize), yB=(float)cs.GetYByValue(price);
                    float cH=yB-yT; if (cH<2f) continue;
                    double bid=0, ask=0;
                    try{bid=vb.Volumes[bi].GetBidVolumeForPrice(price);
                        ask=vb.Volumes[bi].GetAskVolumeForPrice(price);}catch{continue;}
                    if (bid<MinCellVol&&ask<MinCellVol) continue;
                    bool isPoc=Math.Abs(price-poc)<TickSize*.5;
                    bool buyI=ask>0&&bid>0&&ask/bid>=ImbRatio;
                    bool selI=ask>0&&bid>0&&bid/ask>=ImbRatio;
                    if (buyI)
                    { float al=Math.Min((float)((ask/Math.Max(bid,1))/ImbRatio-1)*.5f+.3f,.85f);
                      var b=new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,new SharpDX.Color4(0f,.35f+al*.1f,.18f,al));
                      RenderTarget.FillRectangle(new SharpDX.RectangleF(xL,yT,bW,cH),b);b.Dispose();}
                    else if (selI)
                    { float al=Math.Min((float)((bid/Math.Max(ask,1))/ImbRatio-1)*.5f+.3f,.85f);
                      var b=new SharpDX.Direct2D1.SolidColorBrush(RenderTarget,new SharpDX.Color4(.35f+al*.1f,0f,0f,al));
                      RenderTarget.FillRectangle(new SharpDX.RectangleF(xL,yT,bW,cH),b);b.Dispose();}
                    if (isPoc) RenderTarget.DrawLine(new SharpDX.Vector2(xL,yT),new SharpDX.Vector2(xL,yB),_dxBd,2f);
                    if (cH>=8f&&bW>=26f)
                    { float cW=bW/3f;
                      string bs=bid>0?FV(bid):"", pr=FC(price), as_=ask>0?FV(ask):"";
                      if(bs.Length>0)RenderTarget.DrawText(bs,_fC,new SharpDX.RectangleF(xL+1,yT,cW-1,cH),buyI?_dxG:_dxGr,DrawTextOptions.Clip);
                      if(pr.Length>0)RenderTarget.DrawText(pr,_fS,new SharpDX.RectangleF(xL+cW,yT,cW,cH),_dxGr,DrawTextOptions.Clip);
                      if(as_.Length>0)RenderTarget.DrawText(as_,_fC,new SharpDX.RectangleF(xL+cW*2,yT,cW-1,cH),selI?_dxR:_dxGr,DrawTextOptions.Clip);}
                }
                if (ShowDelta)
                { float dy=(float)cs.GetYByValue(lo)+2f;
                  string ds=del>=0?"Δ +"+del.ToString("N0"):"Δ "+del.ToString("N0");
                  RenderTarget.DrawText(ds,_fS,new SharpDX.RectangleF(xL,dy,bW+55,12f),del>0?_dxG:_dxR,DrawTextOptions.Clip);}
            }
        }

        private void RenderSigBoxes(ChartControl cc, ChartScale cs)
        {
            if (!_dxOk||RenderTarget==null) return;
            foreach (var s in _feed.Take(5))
            {
                int bIdx=ChartBars.GetBarIdxByTime(cc,s.ts);
                if (bIdx<ChartBars.FromIndex||bIdx>ChartBars.ToIndex) continue;
                float xL=(float)cc.GetXByBarIndex(ChartBars,bIdx);
                double basePx=s.d==+1?Lows[0].GetValueAt(bIdx)-TickSize*9:Highs[0].GetValueAt(bIdx)+TickSize*9;
                float yBase=(float)cs.GetYByValue(basePx);
                float boxW=140f,boxH=48f;
                float yTop=s.d==+1?yBase-boxH:yBase;
                RenderTarget.FillRectangle(new SharpDX.RectangleF(xL-2,yTop,boxW,boxH),_dxBg);
                var bb=s.t==SignalType.TypeA?_dxBd:_dxGo;
                RenderTarget.DrawRectangle(new SharpDX.RectangleF(xL-2,yTop,boxW,boxH),bb,1.5f);
                string l1=(s.t==SignalType.TypeA?"TYPE A":"TYPE B")+" · "+((int)Math.Round(s.s))+"pts";
                string l2=s.l; string l3=s.ts.ToString("HH:mm")+(s.d==+1?" ▲":s.d==-1?" ▼":" -");
                RenderTarget.DrawText(l1,_fL,new SharpDX.RectangleF(xL,yTop+3,boxW-4,17f),s.t==SignalType.TypeA?_dxG:_dxGo,DrawTextOptions.Clip);
                RenderTarget.DrawText(l2,_fS,new SharpDX.RectangleF(xL,yTop+20,boxW-4,13f),_dxW,DrawTextOptions.Clip);
                RenderTarget.DrawText(l3,_fS,new SharpDX.RectangleF(xL,yTop+33,boxW-4,12f),_dxGr,DrawTextOptions.Clip);
            }
        }

        private void RenderStk(ChartControl cc, ChartScale cs)
        {
            if (!_dxOk||RenderTarget==null||_stkTier==0) return;
            float xC=(float)cc.GetXByBarIndex(ChartBars,CurrentBar)+(float)cc.GetBarPaintWidth(ChartBars)/2f;
            float yM=_stkBull?(float)cs.GetYByValue(Low[0])+15f:(float)cs.GetYByValue(High[0])-15f;
            var tv=new[]{new SharpDX.Vector2(xC,_stkBull?yM-9f:yM+9f),
                         new SharpDX.Vector2(xC-6f,_stkBull?yM+3f:yM-3f),
                         new SharpDX.Vector2(xC+6f,_stkBull?yM+3f:yM-3f)};
            for(int i=0;i<3;i++)RenderTarget.DrawLine(tv[i],tv[(i+1)%3],_dxO,1.5f);
            RenderTarget.DrawText("STKt"+_stkTier,_fS,
                new SharpDX.RectangleF(xC-16f,_stkBull?yM+5f:yM-19f,34f,13f),_dxO,DrawTextOptions.Clip);
        }
        #endregion
    }
}

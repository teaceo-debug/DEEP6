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
        #region Scorer Private Fields
        private double _total; private int _sigDir; private SignalType _sigTyp = SignalType.Quiet;
        private string _sigLbl = ""; private DateTime _lastSig = DateTime.MinValue;
        private readonly List<(DateTime ts, SignalType t, int d, string l, double s)> _feed
            = new List<(DateTime, SignalType, int, string, double)>();
        #endregion

        #region Scorer
        private void Scorer()
        {
            int[] dirs={(int)_fpDir,_trDir,0,_icDir,_miDir,_dexDir,0};
            int bE=dirs.Count(d=>d==+1),rE=dirs.Count(d=>d==-1);
            bool ok=Math.Max(bE,rE)>=MinAgree;
            _sigDir=bE>rE?+1:rE>bE?-1:0;
            double raw=_fpSc+_trSc+_spSc+_icSc+_miSc+_vpSc+_mlSc;
            int tot=bE+rE; double ar=tot>0?(double)Math.Max(bE,rE)/tot:0;
            _total=ok?Math.Min(raw*Math.Max(ar,.7),100):0;
            _sigTyp=_total>=TypeAMin?SignalType.TypeA:_total>=TypeBMin?SignalType.TypeB:_total>=50?SignalType.TypeC:SignalType.Quiet;
            var p=new List<string>();
            if(_fpSc>=12&&(int)_fpDir==_sigDir)p.Add("ABSORB");
            if(_trSc>=10&&_trDir==_sigDir)p.Add("TRESS");
            if(_icSc>=8 &&_icDir==_sigDir)p.Add("ICE");
            if(_vpSc>=10)p.Add("LVN");
            if(_dexFired&&_dexDir==_sigDir)p.Add("DEX");
            _sigLbl=string.Join("·",p);
        }
        #endregion

        #region Chart Labels & Price Levels
        private void MakeSigLabel()
        {
            string ts=_sigTyp==SignalType.TypeA?"TYPE A":"TYPE B";
            int pts=(int)Math.Round(_total);
            string dir=_sigDir==+1?"▲":_sigDir==-1?"▼":"-";
            string lbl=ts+" · "+pts+"pts\n"+_sigLbl+"\n"+Time[0].ToString("HH:mm")+" "+dir;
            double y=_sigDir==+1?Low[0]-TickSize*6:High[0]+TickSize*6;
            var c=_sigTyp==SignalType.TypeA?WColor.FromRgb(0,255,135):WColor.FromRgb(255,215,0);
            Draw.Text(this,"D6_"+CurrentBar,true,lbl,0,y,0,new WBrush(c),
                new SimpleFont("Consolas",8),TextAlignment.Center,
                new WBrush(WColor.FromArgb(120,16,12,0)),new WBrush(WColor.FromArgb(180,c.R,c.G,c.B)),80);
        }

        private void PushFeed()
        {
            _feed.Insert(0,(_lastSig,_sigTyp,_sigDir,_sigLbl,_total));
            if(_feed.Count>12)_feed.RemoveAt(_feed.Count-1);
        }

        private void DrawLevels()
        {
            Action<string,string,double,WColor,DashStyleHelper,int> HL=(id,lbl,px,c,ds,w)=>{
                Draw.HorizontalLine(this,id,true,px,new WBrush(WColor.FromArgb(110,c.R,c.G,c.B)),ds,w);
                Draw.Text(this,id+"_l",true,lbl,-5,px,0,new WBrush(c),new SimpleFont("Consolas",7),
                    TextAlignment.Right,Brushes.Transparent,Brushes.Transparent,0);};
            if(!double.IsNaN(_vwap)) HL("d6v","VWAP "+_vwap.ToString("0.00"),_vwap,WColor.FromArgb(90,255,255,255),DashStyleHelper.Solid,1);
            if(!double.IsNaN(_vah))  HL("d6va","VWAP+1s "+_vah.ToString("0.00"),_vah,WColor.FromRgb(130,130,130),DashStyleHelper.Dash,1);
            if(!double.IsNaN(_val))  HL("d6vl","VWAP-1s "+_val.ToString("0.00"),_val,WColor.FromRgb(130,130,130),DashStyleHelper.Dash,1);
            if(_ibDone){HL("d6ih","IBH "+_ibH.ToString("0.00"),_ibH,WColor.FromRgb(0,212,170),DashStyleHelper.DashDot,1);HL("d6il","IBL "+_ibL.ToString("0.00"),_ibL,WColor.FromRgb(0,212,170),DashStyleHelper.DashDot,1);}
            if(!double.IsNaN(_dPoc))HL("d6pc","DEV POC "+_dPoc.ToString("0.00"),_dPoc,WColor.FromRgb(255,149,0),DashStyleHelper.Dot,1);
            if(GexHvl>0)  HL("d6gh","GEX HVL "+GexHvl.ToString("0.00"),GexHvl,WColor.FromRgb(255,215,0),DashStyleHelper.Solid,2);
            if(CallWall>0)HL("d6cw","CALL WALL "+CallWall.ToString("0.00"),CallWall,WColor.FromRgb(155,89,182),DashStyleHelper.Solid,1);
            if(PutWall>0) HL("d6pw","PUT WALL "+PutWall.ToString("0.00"),PutWall,WColor.FromRgb(231,76,60),DashStyleHelper.Solid,1);
            if(GammaFlip>0)HL("d6gf","GAMMA FLIP "+GammaFlip.ToString("0.00"),GammaFlip,WColor.FromRgb(200,200,100),DashStyleHelper.Dash,1);
            if(PdVah>0)   HL("d6pv","pdVAH "+PdVah.ToString("0.00"),PdVah,WColor.FromRgb(90,200,250),DashStyleHelper.Solid,1);
            if(PdVal>0)   HL("d6pl","pdVAL "+PdVal.ToString("0.00"),PdVal,WColor.FromRgb(90,200,250),DashStyleHelper.Solid,1);
            if(PdPoc>0)   HL("d6pp","pdPOC "+PdPoc.ToString("0.00"),PdPoc,WColor.FromRgb(150,200,250),DashStyleHelper.Dot,1);
        }
        #endregion
    }
}

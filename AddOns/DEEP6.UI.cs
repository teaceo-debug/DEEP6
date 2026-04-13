#region Using declarations
using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
using NinjaTrader.Gui.Chart;
using WBrush  = System.Windows.Media.SolidColorBrush;
using WColor  = System.Windows.Media.Color;
using WFont   = System.Windows.Media.FontFamily;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class DEEP6
    {
        #region WPF Fields
        // Header
        private Border _hBdr, _pBdr, _tabBdr, _panelRoot;
        private Label _hPrc, _hPct, _hDT, _hIBT, _hGR, _hVZ, _hSP, _hTR, _hCV;
        private Ellipse _domDot;
        // Pills
        private Label _pTrend, _pIbConf, _pGamma, _pPocMig, _pVwapPoc;
        // Right panel DEEP6 tab
        private Canvas _gauge;
        private Label _lblST, _lblSD;
        private ProgressBar _pbFP, _pbTR, _pbSP, _pbIC, _pbMI, _pbVP;
        private Label _ptFP, _ptTR, _ptSP, _ptIC, _ptMI, _ptVP;
        private Ellipse _dFP, _dTR, _dSP, _dIC, _dDX, _dMI, _dCV, _dGX, _dML;
        private Label _vFP, _vTR, _vSP, _vIC, _vDX, _vMI, _vCV, _vGX, _vML;
        private StackPanel _feedPnl, _gexPnl, _lvlPnl, _logPnl;
        private Label _gexRegLbl;
        #endregion

        #region WPF UI Construction
        private void BuildUI()
        {
            if (ShowHeader) BuildHeader();
            if (ShowPills)  BuildPills();
            BuildTabBar();
            if (ShowPanel)  BuildPanel();
        }

        // ── Header Bar ─────────────────────────────────────────────────────
        private void BuildHeader()
        {
            var win=Window.GetWindow(ChartControl); if(win==null)return;
            var grid=FindGrid(win); if(grid==null)return;
            grid.RowDefinitions.Insert(0,new RowDefinition{Height=new GridLength(46)});
            foreach(UIElement el in grid.Children){int r=Grid.GetRow(el);Grid.SetRow(el,r+1);}
            var bdr=new Border{Background=new WBrush(WColor.FromRgb(13,15,30)),
                BorderBrush=new WBrush(WColor.FromRgb(25,30,55)),BorderThickness=new Thickness(0,0,0,1)};
            _hBdr=bdr;
            var sp=new StackPanel{Orientation=Orientation.Vertical};
            // Row 1
            var r1=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(8,3,8,0)};
            r1.Children.Add(Lbl("DEEP6",13,WColor.FromRgb(0,212,170),true));
            r1.Children.Add(Lbl(" "+VER,9,WColor.FromRgb(80,90,120)));
            r1.Children.Add(Lbl("  NQ1! ",12,WColor.FromRgb(200,210,255)));
            _hPrc=Lbl("---",17,WColor.FromRgb(230,240,255),true);r1.Children.Add(_hPrc);
            _hPct=Lbl("",11,WColor.FromRgb(0,255,135));r1.Children.Add(_hPct);
            sp.Children.Add(r1);
            // Row 2
            var r2=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(8,1,8,3)};
            _hDT =HC(r2,"DAY TYPE","---"); _hIBT=HC(r2,"IB TIER","---");
            _hGR =HC(r2,"GEX REGIME","---"); _hVZ=HC(r2,"VWAP ZONE","---");
            _hSP =HC(r2,"SPOOF","---"); _hTR=HC(r2,"TRESPASS","---"); _hCV=HC(r2,"CVD","---");
            var ds=new StackPanel{Orientation=Orientation.Horizontal,VerticalAlignment=VerticalAlignment.Center,Margin=new Thickness(10,0,0,0)};
            _domDot=new Ellipse{Width=8,Height=8,Fill=new WBrush(WColor.FromRgb(57,211,83)),Margin=new Thickness(0,0,4,0),VerticalAlignment=VerticalAlignment.Center};
            ds.Children.Add(_domDot);ds.Children.Add(Lbl("DOM LIVE",8,WColor.FromRgb(57,211,83)));r2.Children.Add(ds);
            sp.Children.Add(r2); bdr.Child=sp;
            Grid.SetRow(bdr,0); Grid.SetColumnSpan(bdr,Math.Max(grid.ColumnDefinitions.Count,1));
            grid.Children.Add(bdr);
        }
        private Label HC(StackPanel p,string lbl,string val)
        { var col=new StackPanel{Orientation=Orientation.Vertical,Margin=new Thickness(0,0,14,0),VerticalAlignment=VerticalAlignment.Center};
          col.Children.Add(new Label{Content=lbl,FontSize=7,Foreground=new WBrush(WColor.FromRgb(70,80,110)),Padding=new Thickness(0),FontFamily=new WFont("Consolas")});
          var vl=new Label{Content=val,FontSize=9,FontWeight=FontWeights.Bold,Foreground=new WBrush(WColor.FromRgb(200,210,230)),Padding=new Thickness(0),FontFamily=new WFont("Consolas")};
          col.Children.Add(vl);p.Children.Add(col);return vl;}

        // ── Status Pills ───────────────────────────────────────────────────
        private void BuildPills()
        {
            var win=Window.GetWindow(ChartControl); if(win==null)return;
            var grid=FindGrid(win); if(grid==null)return;
            int ir=ShowHeader?1:0;
            grid.RowDefinitions.Insert(ir,new RowDefinition{Height=new GridLength(26)});
            foreach(UIElement el in grid.Children){int r=Grid.GetRow(el);if(el!=_hBdr&&r>=ir)Grid.SetRow(el,r+1);}
            var bdr=new Border{Background=new WBrush(WColor.FromRgb(8,10,20)),
                BorderBrush=new WBrush(WColor.FromRgb(20,25,45)),BorderThickness=new Thickness(0,0,0,1),
                Padding=new Thickness(6,3,6,3)};
            _pBdr=bdr;
            var wp=new WrapPanel{Orientation=Orientation.Horizontal};
            _pTrend   =Pill(wp,"TREND BULL",  WColor.FromRgb(11,61,30),  WColor.FromRgb(0,255,135));
                        Pill(wp,"IB",          WColor.FromRgb(26,30,53),  WColor.FromRgb(128,144,192));
            _pIbConf  =Pill(wp,"NARROW*C",    WColor.FromRgb(13,53,53),  WColor.FromRgb(0,212,170));
                        Pill(wp,"GEX",         WColor.FromRgb(26,30,53),  WColor.FromRgb(128,144,192));
            _pGamma   =Pill(wp,"NEG GAMMA",   WColor.FromRgb(61,11,11),  WColor.FromRgb(255,68,68));
                        Pill(wp,"DEV POC",     WColor.FromRgb(26,30,53),  WColor.FromRgb(128,144,192));
            _pPocMig  =Pill(wp,"MIGRATING",   WColor.FromRgb(61,40,0),   WColor.FromRgb(255,149,0));
                        Pill(wp,"VWAP-POC",    WColor.FromRgb(26,30,53),  WColor.FromRgb(128,144,192));
            _pVwapPoc =Pill(wp,"0 tks",       WColor.FromRgb(13,37,53),  WColor.FromRgb(90,200,250));
            bdr.Child=wp; Grid.SetRow(bdr,ir);
            Grid.SetColumnSpan(bdr,Math.Max(grid.ColumnDefinitions.Count,1));
            grid.Children.Add(bdr);
        }
        private Label Pill(WrapPanel p,string t,WColor bg,WColor fg)
        { var b=new Border{Background=new WBrush(bg),BorderBrush=new WBrush(WColor.FromArgb(100,fg.R,fg.G,fg.B)),BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(3),Padding=new Thickness(6,1,6,1),Margin=new Thickness(2,1,2,1)};
          var l=new Label{Content=t,FontSize=8,FontWeight=FontWeights.Bold,Foreground=new WBrush(fg),Padding=new Thickness(0),FontFamily=new WFont("Consolas")};
          b.Child=l;p.Children.Add(b);return l;}

        // ── Left Tab Bar ───────────────────────────────────────────────────
        private void BuildTabBar()
        { var tb=new Border{Width=52,Background=new WBrush(WColor.FromRgb(8,9,15)),
              BorderBrush=new WBrush(WColor.FromRgb(20,25,45)),BorderThickness=new Thickness(0,0,1,0),
              HorizontalAlignment=HorizontalAlignment.Left,VerticalAlignment=VerticalAlignment.Stretch};
          _tabBdr=tb;
          var sp=new StackPanel{Orientation=Orientation.Vertical};
          foreach(var t in new[]{"IN","3 MIN","5 MIN","FOOT-\nPRINT","VOL\nPROF","VWAP\n+-2s","GEX\nLVLS","IB\nLVLS","SIGS"})
          { bool act=t.StartsWith("FOOT");
            var btn=new System.Windows.Controls.Button{Content=new TextBlock{Text=t,TextAlignment=TextAlignment.Center,TextWrapping=TextWrapping.Wrap,FontSize=7,FontFamily=new WFont("Consolas"),LineHeight=10},
                Height=44,Margin=new Thickness(0),Background=new WBrush(act?WColor.FromRgb(10,14,24):WColor.FromRgb(8,9,15)),
                Foreground=act?new WBrush(WColor.FromRgb(0,255,135)):new WBrush(WColor.FromRgb(74,80,112)),
                BorderBrush=act?new WBrush(WColor.FromRgb(0,255,135)):Brushes.Transparent,
                BorderThickness=new Thickness(2,0,0,0),Padding=new Thickness(4)};
            sp.Children.Add(btn);sp.Children.Add(new Separator{Height=1,Background=new WBrush(WColor.FromRgb(16,20,36))});}
          tb.Child=sp;if(ChartControl.Controls!=null)ChartControl.Controls.Add(tb);}

        // ── Right Panel ────────────────────────────────────────────────────
        private void BuildPanel()
        {
            var root=new Border{Width=234,Background=new WBrush(WColor.FromArgb(248,10,12,22)),
                BorderBrush=new WBrush(WColor.FromRgb(22,28,50)),BorderThickness=new Thickness(1,0,0,0),
                HorizontalAlignment=HorizontalAlignment.Right,VerticalAlignment=VerticalAlignment.Stretch};
            _panelRoot=root;
            var main=new StackPanel{Orientation=Orientation.Vertical};
            // Tab header row
            var tabRow=new StackPanel{Orientation=Orientation.Horizontal,Background=new WBrush(WColor.FromRgb(8,10,20))};
            foreach(var t in new[]{"DEEP6","GEX","LEVELS","LOG"})
            { bool a=t=="DEEP6";
              tabRow.Children.Add(new Label{Content=t,FontSize=9,FontWeight=FontWeights.Bold,
                  Padding=new Thickness(10,5,10,4),FontFamily=new WFont("Consolas"),
                  Foreground=a?new WBrush(WColor.FromRgb(0,255,135)):new WBrush(WColor.FromRgb(80,90,120)),
                  BorderBrush=a?new WBrush(WColor.FromRgb(0,255,135)):Brushes.Transparent,
                  BorderThickness=new Thickness(0,0,0,a?2:0)});}
            main.Children.Add(tabRow);main.Children.Add(HR());
            // ── DEEP6 tab content
            var d6=new StackPanel{Orientation=Orientation.Vertical};
            // Gauge
            var gr=new Grid{Margin=new Thickness(8,8,8,4)};
            gr.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
            gr.ColumnDefinitions.Add(new ColumnDefinition{Width=GridLength.Auto});
            _gauge=new Canvas{Width=80,Height=80};DrawGauge(0,WColor.FromRgb(0,255,135));
            Grid.SetColumn(_gauge,1);gr.Children.Add(_gauge);
            var si=new StackPanel{VerticalAlignment=VerticalAlignment.Center};
            _lblST=Lbl("UNIFIED SCORE",8,WColor.FromRgb(60,70,110));
            _lblSD=Lbl("---",10,WColor.FromRgb(0,255,135),true);_lblSD.Margin=new Thickness(0,4,0,0);
            si.Children.Add(_lblST);si.Children.Add(_lblSD);Grid.SetColumn(si,0);gr.Children.Add(si);
            d6.Children.Add(gr);d6.Children.Add(HR());
            d6.Children.Add(SH("LAYER SCORES"));
            (_pbFP,_ptFP)=SBar(d6,"FOOTPRINT",MX_FP,WColor.FromRgb(0,255,135));
            (_pbTR,_ptTR)=SBar(d6,"TRESPASS", MX_TR,WColor.FromRgb(0,255,135));
            (_pbSP,_ptSP)=SBar(d6,"SPOOF",    MX_SP,WColor.FromRgb(0,255,135));
            (_pbIC,_ptIC)=SBar(d6,"ICEBERG",  MX_IC,WColor.FromRgb(255,105,180));
            (_pbMI,_ptMI)=SBar(d6,"MICRO",    MX_MI,WColor.FromRgb(0,255,135));
            (_pbVP,_ptVP)=SBar(d6,"VP+CTX",   MX_VP,WColor.FromRgb(255,215,0));
            d6.Children.Add(HR());d6.Children.Add(SH("LAYER STATUS"));
            (_dFP,_vFP)=SR(d6,"Footprint",     WColor.FromRgb(57,211,83));
            (_dTR,_vTR)=SR(d6,"Trespass",      WColor.FromRgb(57,211,83));
            (_dSP,_vSP)=SR(d6,"CounterSpoof",  WColor.FromRgb(57,211,83));
            (_dIC,_vIC)=SR(d6,"Iceberg",       WColor.FromRgb(255,105,180));
            (_dDX,_vDX)=SR(d6,"DEX-ARRAY",    WColor.FromRgb(90,200,250));
            (_dMI,_vMI)=SR(d6,"Microprobability",WColor.FromRgb(57,211,83));
            (_dCV,_vCV)=SR(d6,"CVD",           WColor.FromRgb(255,215,0));
            (_dGX,_vGX)=SR(d6,"GEX Regime",   WColor.FromRgb(255,215,0));
            (_dML,_vML)=SR(d6,"ML Sig Quality",WColor.FromRgb(255,215,0));
            d6.Children.Add(HR());d6.Children.Add(SH("SIGNAL FEED"));
            _feedPnl=new StackPanel{Margin=new Thickness(4,2,4,4)};
            d6.Children.Add(_feedPnl);
            main.Children.Add(d6);
            // ── GEX tab (collapsed by default)
            _gexPnl=new StackPanel{Margin=new Thickness(8,4,8,4),Visibility=Visibility.Collapsed};
            _gexPnl.Children.Add(SH("GEX REGIME"));
            _gexRegLbl=Lbl("---",11,WColor.FromRgb(0,255,135));_gexPnl.Children.Add(_gexRegLbl);
            _gexPnl.Children.Add(HR());_gexPnl.Children.Add(SH("OPTIONS LEVELS"));
            _gexPnl.Children.Add(Lbl("GEX HVL:   "+GexHvl.ToString("0.00"),9,WColor.FromRgb(255,215,0)));
            _gexPnl.Children.Add(Lbl("CALL WALL: "+CallWall.ToString("0.00"),9,WColor.FromRgb(155,89,182)));
            _gexPnl.Children.Add(Lbl("PUT WALL:  "+PutWall.ToString("0.00"),9,WColor.FromRgb(231,76,60)));
            _gexPnl.Children.Add(Lbl("GAMMA FLP: "+GammaFlip.ToString("0.00"),9,WColor.FromRgb(200,200,100)));
            main.Children.Add(_gexPnl);
            // ── LEVELS tab
            _lvlPnl=new StackPanel{Margin=new Thickness(8,4,8,4),Visibility=Visibility.Collapsed};
            _lvlPnl.Children.Add(SH("SESSION"));
            _lvlPnl.Children.Add(Lbl("VWAP: ---",9,WColor.FromRgb(220,220,220)));
            _lvlPnl.Children.Add(Lbl("VAH:  ---",9,WColor.FromRgb(180,180,180)));
            _lvlPnl.Children.Add(Lbl("VAL:  ---",9,WColor.FromRgb(180,180,180)));
            _lvlPnl.Children.Add(Lbl("DPOC: ---",9,WColor.FromRgb(255,149,0)));
            _lvlPnl.Children.Add(HR());_lvlPnl.Children.Add(SH("INITIAL BALANCE"));
            _lvlPnl.Children.Add(Lbl("IBH:  ---",9,WColor.FromRgb(0,212,170)));
            _lvlPnl.Children.Add(Lbl("IBL:  ---",9,WColor.FromRgb(0,212,170)));
            _lvlPnl.Children.Add(Lbl("Type: ---",9,WColor.FromRgb(0,212,170)));
            _lvlPnl.Children.Add(HR());_lvlPnl.Children.Add(SH("PREV DAY"));
            _lvlPnl.Children.Add(Lbl("pdVAH: "+PdVah.ToString("0.00"),9,WColor.FromRgb(90,200,250)));
            _lvlPnl.Children.Add(Lbl("pdVAL: "+PdVal.ToString("0.00"),9,WColor.FromRgb(90,200,250)));
            _lvlPnl.Children.Add(Lbl("pdPOC: "+PdPoc.ToString("0.00"),9,WColor.FromRgb(90,200,250)));
            main.Children.Add(_lvlPnl);
            // ── LOG tab
            _logPnl=new StackPanel{Margin=new Thickness(4,4,4,4),Visibility=Visibility.Collapsed};
            _logPnl.Children.Add(SH("EVENT LOG"));main.Children.Add(_logPnl);
            root.Child=main;if(ChartControl.Controls!=null)ChartControl.Controls.Add(root);
        }
        #endregion

        #region Panel Update
        private void UpdatePanel()
        {
            if (_panelRoot==null||ChartControl==null) return;
            ChartControl.Dispatcher.InvokeAsync(()=>
            {
                // Header
                if(_hPrc!=null)_hPrc.Content=Close.Count>0?Close[0].ToString("0.00"):"---";
                if(_hDT!=null){string dt=_dayTyp==DayType.TrendBull?"TREND BULL":_dayTyp==DayType.TrendBear?"TREND BEAR":_dayTyp==DayType.BalanceDay?"BALANCE":"---";_hDT.Content=dt;_hDT.Foreground=new WBrush(_dayTyp==DayType.TrendBull?WColor.FromRgb(0,255,135):_dayTyp==DayType.TrendBear?WColor.FromRgb(255,68,68):WColor.FromRgb(200,210,230));}
                if(_hIBT!=null)_hIBT.Content=_ibTyp.ToString().ToUpper();
                if(_hGR!=null){string g=GexReg==GexRegime.NegativeAmplifying?"NEGATIVE":GexReg==GexRegime.PositiveDampening?"POSITIVE":"NEUTRAL";_hGR.Content=g;_hGR.Foreground=new WBrush(GexReg==GexRegime.NegativeAmplifying?WColor.FromRgb(255,68,68):GexReg==GexRegime.PositiveDampening?WColor.FromRgb(0,255,135):WColor.FromRgb(200,210,230));}
                string zs=_vwapZ==VwapZone.Above2Sd?"+2s":_vwapZ==VwapZone.Above1Sd?"+1s":_vwapZ==VwapZone.AboveVwap?"ABOVE":_vwapZ==VwapZone.AtVwap?"AT":_vwapZ==VwapZone.BelowVwap?"BELOW":_vwapZ==VwapZone.Below1Sd?"-1s":"-2s";
                if(_hVZ!=null)_hVZ.Content=zs;
                if(_hSP!=null)_hSP.Content=_w1.ToString("0.00");
                if(_hTR!=null)_hTR.Content=_imbEma.ToString("+0.00;-0.00;+0.00");
                if(_hCV!=null)_hCV.Content=(_cvd>=0?"+":"")+_cvd.ToString("N0");
                // Pills
                if(_pTrend!=null)_pTrend.Content=_dayTyp==DayType.TrendBull?"TREND BULL":_dayTyp==DayType.TrendBear?"TREND BEAR":_dayTyp.ToString().ToUpper();
                if(_pIbConf!=null)_pIbConf.Content=_ibTyp.ToString().ToUpper()+(_ibConf?"*CONF":"");
                if(_pGamma!=null)_pGamma.Content=GexReg==GexRegime.NegativeAmplifying?"NEG GAMMA*AMP":GexReg==GexRegime.PositiveDampening?"POS GAMMA*DMP":"GEX NEUTRAL";
                if(_pPocMig!=null)_pPocMig.Content=_pocMB>0?"MIG "+(_pocMU?"▲":"▼")+" "+_pocMB+"B":"POC STABLE";
                if(_pVwapPoc!=null){double dist=!double.IsNaN(_vwap)&&!double.IsNaN(_dPoc)?Math.Abs(_vwap-_dPoc)/TickSize:0;string reg=dist>25?"TRENDING":dist>10?"DIVERGING":"BALANCED";_pVwapPoc.Content=(int)dist+"tks "+reg;}
                // Score gauge
                WColor gc=_total>=TypeAMin?WColor.FromRgb(0,255,135):_total>=TypeBMin?WColor.FromRgb(255,215,0):_total>=50?WColor.FromRgb(90,200,250):WColor.FromRgb(60,70,110);
                DrawGauge(_total,gc);
                if(_lblST!=null){_lblST.Content=_sigTyp==SignalType.TypeA?"TYPE A · TRIPLE CONFLUENCE":_sigTyp==SignalType.TypeB?"TYPE B · DOUBLE CONFLUENCE":_sigTyp==SignalType.TypeC?"TYPE C · SIGNAL":"UNIFIED SCORE";_lblST.Foreground=new WBrush(gc);}
                if(_lblSD!=null){string dd=_sigDir==+1?"LONG ▲":_sigDir==-1?"SHORT ▼":"---";_lblSD.Content=dd;_lblSD.Foreground=new WBrush(gc);}
                // Score bars
                SBr(_pbFP,_ptFP,_fpSc,MX_FP,WColor.FromRgb(0,255,135));
                SBr(_pbTR,_ptTR,_trSc,MX_TR,WColor.FromRgb(0,255,135));
                SBr(_pbSP,_ptSP,_spSc,MX_SP,WColor.FromRgb(0,255,135));
                SBr(_pbIC,_ptIC,_icSc,MX_IC,WColor.FromRgb(255,105,180));
                SBr(_pbMI,_ptMI,_miSc,MX_MI,WColor.FromRgb(0,255,135));
                SBr(_pbVP,_ptVP,_vpSc,MX_VP,WColor.FromRgb(255,215,0));
                // Status dots
                SD(_dFP,_vFP,_fpSc>5,_fpSt,WColor.FromRgb(57,211,83));
                SD(_dTR,_vTR,_trSc>5,_trSt,WColor.FromRgb(57,211,83));
                SD(_dSP,_vSP,true,_spSt,WColor.FromRgb(57,211,83));
                SD(_dIC,_vIC,_icSc>3,_icSt,WColor.FromRgb(255,105,180));
                SD(_dDX,_vDX,_dexFired,_dexSt,WColor.FromRgb(90,200,250));
                SD(_dMI,_vMI,_miSc>3,_miSt,WColor.FromRgb(57,211,83));
                double ck=_cvd/1000.0;SD(_dCV,_vCV,Math.Abs(_cvd)>500,(_cvd>=0?"+":"")+ck.ToString("0.0")+"K "+(_cvd>0?"▲":"▼"),WColor.FromRgb(255,215,0));
                string gxs=GexReg==GexRegime.NegativeAmplifying?"NEG AMP":GexReg==GexRegime.NegativeStable?"NEG STB":GexReg==GexRegime.PositiveDampening?"POS DMP":"NEUTRAL";
                SD(_dGX,_vGX,true,gxs,WColor.FromRgb(255,215,0));
                SD(_dML,_vML,_mlSc>4,_mlSt,WColor.FromRgb(255,215,0));
                // GEX tab
                if(_gexRegLbl!=null){_gexRegLbl.Content=gxs;_gexRegLbl.Foreground=new WBrush(GexReg==GexRegime.NegativeAmplifying?WColor.FromRgb(255,68,68):GexReg==GexRegime.PositiveDampening?WColor.FromRgb(0,255,135):WColor.FromRgb(200,210,230));}
                RefreshFeed();RefreshLog();
            });
        }

        private void DrawGauge(double score, WColor color)
        {
            if (_gauge==null) return; _gauge.Children.Clear();
            double cx=40,cy=40,r=32;
            _gauge.Children.Add(Arc(cx,cy,r,225,270,WColor.FromRgb(25,30,50),8));
            if(score>0)_gauge.Children.Add(Arc(cx,cy,r,225,score/100.0*270,color,6));
            var nl=new Label{Content=score>0?((int)Math.Round(score)).ToString():"---",FontSize=16,FontWeight=FontWeights.Bold,Foreground=new WBrush(color),Padding=new Thickness(0),FontFamily=new WFont("Consolas")};
            Canvas.SetLeft(nl,cx-18);Canvas.SetTop(nl,cy-12);_gauge.Children.Add(nl);
            var sl=new Label{Content="/100",FontSize=7,Foreground=new WBrush(WColor.FromRgb(80,90,120)),Padding=new Thickness(0),FontFamily=new WFont("Consolas")};
            Canvas.SetLeft(sl,cx-10);Canvas.SetTop(sl,cy+6);_gauge.Children.Add(sl);
        }
        private System.Windows.Shapes.Path Arc(double cx,double cy,double r,double sD,double sw,WColor c,double thick)
        { if(sw<=0)sw=.01;double s=(sD-90)*Math.PI/180,e=(sD+sw-90)*Math.PI/180;bool lg=sw>180;
          var fig=new System.Windows.Media.PathFigure{StartPoint=new Point(cx+r*Math.Cos(s),cy+r*Math.Sin(s)),IsClosed=false};
          fig.Segments.Add(new System.Windows.Media.ArcSegment(new Point(cx+r*Math.Cos(e),cy+r*Math.Sin(e)),new Size(r,r),0,lg,System.Windows.Media.SweepDirection.Clockwise,true));
          return new System.Windows.Shapes.Path{Data=new System.Windows.Media.PathGeometry(new[]{fig}),Stroke=new WBrush(c),StrokeThickness=thick,StrokeLineJoin=System.Windows.Media.PenLineJoin.Round,StrokeStartLineCap=System.Windows.Media.PenLineCap.Round,StrokeEndLineCap=System.Windows.Media.PenLineCap.Round};}

        private void RefreshFeed()
        { if(_feedPnl==null)return;_feedPnl.Children.Clear();
          foreach(var s in _feed.Take(7))
          { WColor tc=s.t==SignalType.TypeA?WColor.FromRgb(0,255,135):WColor.FromRgb(255,215,0);
            var b=new Border{Background=new WBrush(WColor.FromArgb(70,tc.R,tc.G,tc.B)),BorderBrush=new WBrush(WColor.FromArgb(200,tc.R,tc.G,tc.B)),BorderThickness=new Thickness(1),CornerRadius=new CornerRadius(3),Padding=new Thickness(4,2,4,2),Margin=new Thickness(0,1,0,1)};
            string ds=s.d==+1?"Bull ":s.d==-1?"Bear ":"";string ts=s.t==SignalType.TypeA?"TYPE A":"TYPE B";
            var row=new StackPanel{Orientation=Orientation.Horizontal};
            row.Children.Add(new Label{Content="["+ts+"]",FontSize=7.5,Padding=new Thickness(0,0,4,0),FontWeight=FontWeights.Bold,Foreground=new WBrush(tc),FontFamily=new WFont("Consolas")});
            row.Children.Add(new Label{Content=ds+s.l,FontSize=7.5,Padding=new Thickness(0),Foreground=new WBrush(WColor.FromRgb(180,190,210)),FontFamily=new WFont("Consolas")});
            row.Children.Add(new Label{Content=s.ts.ToString("HH:mm"),FontSize=7,Padding=new Thickness(4,0,0,0),Foreground=new WBrush(WColor.FromRgb(80,90,120)),FontFamily=new WFont("Consolas")});
            b.Child=row;_feedPnl.Children.Add(b);}}

        private void RefreshLog()
        { if(_logPnl==null||_feed.Count==0)return;
          if(_logPnl.Children.Count-1==_feed.Count)return;
          while(_logPnl.Children.Count>1)_logPnl.Children.RemoveAt(_logPnl.Children.Count-1);
          foreach(var s in _feed.Take(10))
          { string line=s.ts.ToString("HH:mm:ss")+"  "+(s.t==SignalType.TypeA?"TYPE A":"TYPE B")+"  "+(s.d==+1?"BULL":"BEAR")+"  "+((int)s.s)+"pts";
            var ll=Lbl(line,8,s.t==SignalType.TypeA?WColor.FromRgb(0,255,135):WColor.FromRgb(255,215,0));
            ll.Margin=new Thickness(0,1,0,1);_logPnl.Children.Add(ll);}}

        private void SBr(ProgressBar pb,Label l,double v,double mx,WColor c)
        {if(pb==null||l==null)return;pb.Maximum=mx;pb.Value=Math.Min(v,mx);pb.Foreground=new WBrush(c);l.Content=((int)Math.Round(v)).ToString();}
        private void SD(Ellipse dot,Label lbl,bool act,string txt,WColor c)
        {if(dot==null||lbl==null)return;dot.Fill=new WBrush(act?c:WColor.FromRgb(40,45,70));lbl.Content=txt;lbl.Foreground=new WBrush(act?WColor.FromRgb(200,210,230):WColor.FromRgb(80,90,120));}
        private void DisposeUI()
        { ChartControl?.Dispatcher.InvokeAsync(()=>{
            if(_panelRoot!=null&&ChartControl?.Controls!=null)ChartControl.Controls.Remove(_panelRoot);
            if(_tabBdr!=null&&ChartControl?.Controls!=null)ChartControl.Controls.Remove(_tabBdr);
            _panelRoot=null;_tabBdr=null;});}
        #endregion

        #region WPF Helpers
        private Label Lbl(string t,double fs,WColor c,bool bold=false)
            =>new Label{Content=t,FontSize=fs,Foreground=new WBrush(c),Padding=new Thickness(0),
                FontWeight=bold?FontWeights.Bold:FontWeights.Normal,
                VerticalAlignment=VerticalAlignment.Center,FontFamily=new WFont("Consolas")};
        private Border HR()=>new Border{Height=1,Margin=new Thickness(0,3,0,3),Background=new WBrush(WColor.FromRgb(18,23,40))};
        private Label SH(string t)=>new Label{Content=t,FontSize=8,FontWeight=FontWeights.Bold,
            Foreground=new WBrush(WColor.FromRgb(55,65,100)),Padding=new Thickness(8,3,4,2),FontFamily=new WFont("Consolas")};
        private (ProgressBar,Label) SBar(StackPanel p,string nm,double mx,WColor c)
        { var row=new Grid{Margin=new Thickness(8,1,8,1)};
          row.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(64)});
          row.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(1,GridUnitType.Star)});
          row.ColumnDefinitions.Add(new ColumnDefinition{Width=new GridLength(26)});
          var nl=Lbl(nm,7.5,WColor.FromRgb(120,130,160));Grid.SetColumn(nl,0);row.Children.Add(nl);
          var pb=new ProgressBar{Maximum=mx,Value=0,Height=6,VerticalAlignment=VerticalAlignment.Center,
              Margin=new Thickness(4,0,4,0),Foreground=new WBrush(c),Background=new WBrush(WColor.FromRgb(18,23,40)),BorderThickness=new Thickness(0)};
          Grid.SetColumn(pb,1);row.Children.Add(pb);
          var pt=Lbl("0",8,c,true);pt.HorizontalAlignment=HorizontalAlignment.Right;Grid.SetColumn(pt,2);row.Children.Add(pt);
          p.Children.Add(row);return(pb,pt);}
        private (Ellipse,Label) SR(StackPanel p,string nm,WColor c)
        { var row=new StackPanel{Orientation=Orientation.Horizontal,Margin=new Thickness(8,1,4,1)};
          var dot=new Ellipse{Width=7,Height=7,Fill=new WBrush(WColor.FromRgb(40,45,70)),Margin=new Thickness(0,0,5,0),VerticalAlignment=VerticalAlignment.Center};
          var nl=new Label{Content=nm,FontSize=7.5,Foreground=new WBrush(WColor.FromRgb(100,110,140)),Padding=new Thickness(0),Width=97,FontFamily=new WFont("Consolas"),VerticalAlignment=VerticalAlignment.Center};
          var vl=new Label{Content="---",FontSize=7.5,Foreground=new WBrush(WColor.FromRgb(130,140,170)),Padding=new Thickness(0),FontFamily=new WFont("Consolas"),VerticalAlignment=VerticalAlignment.Center};
          row.Children.Add(dot);row.Children.Add(nl);row.Children.Add(vl);p.Children.Add(row);return(dot,vl);}
        private static Grid FindGrid(DependencyObject parent)
        { if(parent==null)return null;
          int n=System.Windows.Media.VisualTreeHelper.GetChildrenCount(parent);
          for(int i=0;i<n;i++){var ch=System.Windows.Media.VisualTreeHelper.GetChild(parent,i);
              if(ch is Grid g)return g;var r=FindGrid(ch);if(r!=null)return r;}return null;}
        #endregion
    }
}

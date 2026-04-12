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

// ============================================================================
//  DEEP6  v1.0.0 — NinjaTrader 8 Indicator — COMPLETE BUILD
//  Seven-Layer Institutional-Grade Market Intelligence System
//
//  E1 FOOTPRINT  25pts  VolumetricBars absorption/exhaustion/imbalances
//  E2 TRESPASS   20pts  Gould & Bonart (2015) LOB queue imbalance
//  E3 SPOOF      15pts  Tao et al. (2020) Wasserstein + Do & Putniņš (2023)
//  E4 ICEBERG    15pts  Zotikov & Antonov (2021) CME iceberg detection
//  E5 MICRO      10pts  Bayesian directional probability (Naive Bayes)
//  E6 VP+CTX     15pts  DEX-ARRAY + VWAP/IB/GEX/POC context engine
//  E7 ML          —     Kalman filter + 8-feature quality classifier
//
//  UI: Header bar (10 cols) · Left tab bar (9 tabs) · 9 Status pills
//      SharpDX footprint cells (bid|price|ask + imbalance + POC + delta row)
//      TYPE A/B signal boxes on chart · STKt1/2/3 triangle markers
//      Right panel: DEEP6/GEX/LEVELS/LOG tabs with live data binding
//      15 price level lines: VWAP±1σ/2σ, IB H/L, DEV POC, GEX HVL,
//      Call/Put Wall, pdVAH/pdVAL
//
//  Requirements: NT8 lifetime license · Volumetric Bars (Order Flow+)
//                Rithmic Level 2 DOM (40+ levels) · Calculate = OnEachTick
// ============================================================================

namespace NinjaTrader.NinjaScript.Indicators
{
    #region Enums
    public enum GexRegime  { NegativeAmplifying, NegativeStable, PositiveDampening, Neutral }
    public enum DayType    { TrendBull, TrendBear, FadeBull, FadeBear, BalanceDay, Unknown }
    public enum IbType     { Wide, Normal, Narrow }
    public enum SignalType { Quiet, TypeC, TypeB, TypeA }
    public enum VwapZone   { Above2Sd, Above1Sd, AboveVwap, AtVwap, BelowVwap, Below1Sd, Below2Sd }
    #endregion

    public class DEEP6 : Indicator
    {
        #region Constants
        private const string VER   = "v1.0.0";
        private const double MX_FP = 25.0;
        private const double MX_TR = 20.0;
        private const double MX_SP = 15.0;
        private const double MX_IC = 15.0;
        private const double MX_MI = 10.0;
        private const double MX_VP = 15.0;
        private const int    DDEPTH = 10;
        #endregion

        #region Parameters
        // E1 Footprint
        [NinjaScriptProperty][Display(Name="Absorb Min Wick %",   Order=1,  GroupName="E1 Footprint")] public double AbsorbWickMin  { get; set; }
        [NinjaScriptProperty][Display(Name="Absorb Max |dv|/vol", Order=2,  GroupName="E1 Footprint")] public double AbsorbDeltaMax { get; set; }
        [NinjaScriptProperty][Display(Name="Imbalance Ratio",     Order=3,  GroupName="E1 Footprint")] public double ImbRatio       { get; set; }
        [NinjaScriptProperty][Display(Name="STK T1 levels",       Order=4,  GroupName="E1 Footprint")] public int    StkT1          { get; set; }
        [NinjaScriptProperty][Display(Name="STK T2 levels",       Order=5,  GroupName="E1 Footprint")] public int    StkT2          { get; set; }
        [NinjaScriptProperty][Display(Name="STK T3 levels",       Order=6,  GroupName="E1 Footprint")] public int    StkT3          { get; set; }
        [NinjaScriptProperty][Display(Name="Min cell volume",     Order=7,  GroupName="E1 Footprint")] public int    MinCellVol     { get; set; }
        // E2 Trespass
        [NinjaScriptProperty][Display(Name="DOM Depth levels",    Order=1,  GroupName="E2 Trespass")]  public int    DomDepth       { get; set; }
        [NinjaScriptProperty][Display(Name="Decay Lambda",        Order=2,  GroupName="E2 Trespass")]  public double Lambda         { get; set; }
        [NinjaScriptProperty][Display(Name="Logistic Beta",       Order=3,  GroupName="E2 Trespass")]  public double LBeta          { get; set; }
        [NinjaScriptProperty][Display(Name="Imbalance EMA Period",Order=4,  GroupName="E2 Trespass")]  public int    TressEma       { get; set; }
        // E3 CounterSpoof
        [NinjaScriptProperty][Display(Name="Long window ticks",   Order=1,  GroupName="E3 Spoof")]     public int    SpooLong       { get; set; }
        [NinjaScriptProperty][Display(Name="Short window ticks",  Order=2,  GroupName="E3 Spoof")]     public int    SpooShort      { get; set; }
        [NinjaScriptProperty][Display(Name="W1 Threshold",        Order=3,  GroupName="E3 Spoof")]     public double SpooW1         { get; set; }
        [NinjaScriptProperty][Display(Name="Large order qty",     Order=4,  GroupName="E3 Spoof")]     public int    SpooQty        { get; set; }
        [NinjaScriptProperty][Display(Name="Cancel window ms",    Order=5,  GroupName="E3 Spoof")]     public int    SpooCancelMs   { get; set; }
        // E4 Iceberg
        [NinjaScriptProperty][Display(Name="Refill window ms",    Order=1,  GroupName="E4 Iceberg")]   public int    IceMs          { get; set; }
        [NinjaScriptProperty][Display(Name="Lookback bars",       Order=2,  GroupName="E4 Iceberg")]   public int    IceLB          { get; set; }
        // E6 VP+CTX
        [NinjaScriptProperty][Display(Name="DEX Lookback bars",   Order=1,  GroupName="E6 VP+CTX")]    public int    DexLB          { get; set; }
        [NinjaScriptProperty][Display(Name="GEX Regime",          Order=2,  GroupName="E6 VP+CTX")]    public GexRegime GexReg      { get; set; }
        [NinjaScriptProperty][Display(Name="IB Minutes",          Order=3,  GroupName="E6 VP+CTX")]    public int    IbMins         { get; set; }
        [NinjaScriptProperty][Display(Name="Avg IB Range ticks",  Order=4,  GroupName="E6 VP+CTX")]    public int    AvgIbTks       { get; set; }
        [NinjaScriptProperty][Display(Name="VWAP Prox ticks",     Order=5,  GroupName="E6 VP+CTX")]    public int    VwapProxTks    { get; set; }
        // GEX Levels (user-supplied)
        [NinjaScriptProperty][Display(Name="GEX HVL",             Order=1,  GroupName="GEX Levels")]   public double GexHvl         { get; set; }
        [NinjaScriptProperty][Display(Name="Call Wall",           Order=2,  GroupName="GEX Levels")]   public double CallWall       { get; set; }
        [NinjaScriptProperty][Display(Name="Put Wall",            Order=3,  GroupName="GEX Levels")]   public double PutWall        { get; set; }
        [NinjaScriptProperty][Display(Name="Gamma Flip",          Order=4,  GroupName="GEX Levels")]   public double GammaFlip      { get; set; }
        [NinjaScriptProperty][Display(Name="Prev Day VAH",        Order=5,  GroupName="GEX Levels")]   public double PdVah          { get; set; }
        [NinjaScriptProperty][Display(Name="Prev Day VAL",        Order=6,  GroupName="GEX Levels")]   public double PdVal          { get; set; }
        [NinjaScriptProperty][Display(Name="Prev Day POC",        Order=7,  GroupName="GEX Levels")]   public double PdPoc          { get; set; }
        // Scoring
        [NinjaScriptProperty][Display(Name="TYPE A threshold",    Order=1,  GroupName="Scoring")]      public int    TypeAMin       { get; set; }
        [NinjaScriptProperty][Display(Name="TYPE B threshold",    Order=2,  GroupName="Scoring")]      public int    TypeBMin       { get; set; }
        [NinjaScriptProperty][Display(Name="Min engines agree",   Order=3,  GroupName="Scoring")]      public int    MinAgree       { get; set; }
        // Display
        [NinjaScriptProperty][Display(Name="Show footprint cells",Order=1,  GroupName="Display")]      public bool   ShowFp         { get; set; }
        [NinjaScriptProperty][Display(Name="Show delta row",      Order=2,  GroupName="Display")]      public bool   ShowDelta      { get; set; }
        [NinjaScriptProperty][Display(Name="Show STKt markers",   Order=3,  GroupName="Display")]      public bool   ShowStk        { get; set; }
        [NinjaScriptProperty][Display(Name="Show price levels",   Order=4,  GroupName="Display")]      public bool   ShowLvls       { get; set; }
        [NinjaScriptProperty][Display(Name="Show signal boxes",   Order=5,  GroupName="Display")]      public bool   ShowSigBox     { get; set; }
        [NinjaScriptProperty][Display(Name="Show header bar",     Order=6,  GroupName="Display")]      public bool   ShowHeader     { get; set; }
        [NinjaScriptProperty][Display(Name="Show status pills",   Order=7,  GroupName="Display")]      public bool   ShowPills      { get; set; }
        [NinjaScriptProperty][Display(Name="Show right panel",    Order=8,  GroupName="Display")]      public bool   ShowPanel      { get; set; }
        #endregion

        #region Private Fields
        // E1
        private double _fpSc, _fpDir; private string _fpSt = "QUIET";
        private double _cvd, _emaVol = double.NaN, _emaRng = double.NaN;
        private int _stkTier; private bool _stkBull;
        private readonly Queue<double> _dQ = new Queue<double>(6);
        private NinjaTrader.NinjaScript.Indicators.EMA _ema20;
        // E2
        private readonly double[] _bV = new double[10], _aV = new double[10];
        private readonly double[] _bP = new double[10], _aP = new double[10];
        private double _imb, _imbEma, _pUp, _trSc; private int _trDir; private string _trSt = "---";
        private readonly Queue<double> _iLong = new Queue<double>(62), _iShort = new Queue<double>(12);
        // E3
        private double _w1, _spSc; private string _spSt = "---"; private int _spEvt;
        private readonly List<(DateTime ts, int lv, bool bid)> _pLg = new List<(DateTime, int, bool)>();
        // E4
        private int _icBull, _icBear; private double _icSc; private int _icDir; private string _icSt = "---";
        private readonly List<(DateTime ts, double px, bool buy)> _pTr = new List<(DateTime, double, bool)>();
        // E5
        private double _pBull = .5, _pBear = .5, _miSc; private int _miDir; private string _miSt = "---";
        // E6
        private double _sVN, _sVD, _sVR, _vwap = double.NaN, _vsd, _vah, _val;
        private double _ibH = double.NaN, _ibL = double.NaN;
        private bool _ibDone, _ibConf; private IbType _ibTyp = IbType.Normal; private DateTime _ibEnd;
        private double _dPoc = double.NaN, _pPoc = double.NaN; private int _pocMB; private bool _pocMU;
        private DayType _dayTyp = DayType.Unknown; private DateTime _sOpen; private double _oPx;
        private double _iHi = double.NaN, _iLo = double.NaN;
        private double _vpSc; private bool _dexFired; private int _dexDir; private string _dexSt = "---";
        private VwapZone _vwapZ = VwapZone.AtVwap;
        // E7
        private double[] _kSt = {0,0}; private double[,] _kP = {{1,0},{0,1}};
        private double _kVel, _mlSc; private string _mlSt = "---";
        private readonly Queue<double> _mlH = new Queue<double>(21);
        // Scorer
        private double _total; private int _sigDir; private SignalType _sigTyp = SignalType.Quiet;
        private string _sigLbl = ""; private DateTime _lastSig = DateTime.MinValue;
        private readonly List<(DateTime ts, SignalType t, int d, string l, double s)> _feed
            = new List<(DateTime, SignalType, int, string, double)>();
        // SharpDX
        private SharpDX.Direct2D1.Brush _dxG, _dxR, _dxGo, _dxW, _dxGr, _dxO, _dxT, _dxC, _dxP, _dxBg, _dxCB, _dxCS, _dxBd;
        private SharpDX.DirectWrite.TextFormat _fC, _fS, _fL;
        private SharpDX.DirectWrite.Factory _dwF;
        private bool _dxOk;
        // WPF — header
        private Border _hBdr, _pBdr, _tabBdr, _panelRoot;
        private Label _hPrc, _hPct, _hDT, _hIBT, _hGR, _hVZ, _hSP, _hTR, _hCV;
        private Ellipse _domDot;
        // WPF — pills
        private Label _pTrend, _pIbConf, _pGamma, _pPocMig, _pVwapPoc;
        // WPF — right panel DEEP6 tab
        private Canvas _gauge;
        private Label _lblST, _lblSD;
        private ProgressBar _pbFP, _pbTR, _pbSP, _pbIC, _pbMI, _pbVP;
        private Label _ptFP, _ptTR, _ptSP, _ptIC, _ptMI, _ptVP;
        private Ellipse _dFP, _dTR, _dSP, _dIC, _dDX, _dMI, _dCV, _dGX, _dML;
        private Label _vFP, _vTR, _vSP, _vIC, _vDX, _vMI, _vCV, _vGX, _vML;
        private StackPanel _feedPnl, _gexPnl, _lvlPnl, _logPnl;
        private Label _gexRegLbl;
        #endregion

        #region OnStateChange
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 v1.0.0 -- Seven-layer institutional orderflow intelligence for NQ";
                Name = "DEEP6"; Calculate = Calculate.OnEachTick; IsOverlay = true;
                DisplayInDataBox = false; IsAutoScale = false; BarsRequiredToPlot = 25;
                IsSuspendedWhileInactive = false;
                // E1
                AbsorbWickMin = 30; AbsorbDeltaMax = 0.12; ImbRatio = 1.5;
                StkT1 = 3; StkT2 = 5; StkT3 = 7; MinCellVol = 0;
                // E2
                DomDepth = 5; Lambda = 0.5; LBeta = 2.5; TressEma = 5;
                // E3
                SpooLong = 60; SpooShort = 10; SpooW1 = 0.4; SpooQty = 500; SpooCancelMs = 500;
                // E4
                IceMs = 250; IceLB = 10;
                // E6
                DexLB = 3; GexReg = GexRegime.Neutral; IbMins = 60; AvgIbTks = 30; VwapProxTks = 8;
                // GEX levels
                GexHvl = 0; CallWall = 0; PutWall = 0; GammaFlip = 0;
                PdVah = 0; PdVal = 0; PdPoc = 0;
                // Scoring
                TypeAMin = 80; TypeBMin = 65; MinAgree = 4;
                // Display
                ShowFp = true; ShowDelta = true; ShowStk = true; ShowLvls = true;
                ShowSigBox = true; ShowHeader = true; ShowPills = true; ShowPanel = true;
                AddPlot(Brushes.Transparent, "Score");
                AddPlot(Brushes.Transparent, "Trespass");
            }
            else if (State == State.Configure)
                AddDataSeries(BarsPeriodType.Minute, 1);
            else if (State == State.DataLoaded)
            {
                _ema20 = EMA(20);
                bool v = BarsArray[0].BarsType is NinjaTrader.NinjaScript.BarsTypes.VolumetricBarsType;
                Print("[DEEP6] Loaded. Volumetric=" + v + " Instrument=" + Instrument.FullName);
            }
            else if (State == State.Realtime)
                ChartControl?.Dispatcher.InvokeAsync(BuildUI);
            else if (State == State.Terminated)
            {
                DisposeUI();
                DisposeDX();
            }
        }
        #endregion

        #region Event Handlers
        protected override void OnBarUpdate()
        {
            if (BarsInProgress == 1 || CurrentBar < BarsRequiredToPlot) return;
            if (Bars.IsFirstBarOfSession) SessionReset();
            UpdateSession();
            RunE1(); RunE5(); RunE6(); RunE7(); Scorer();
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
                  if (e.Volume >= SpooQty && lv >= 2) _pLg.Add((DateTime.Now, lv, true)); }
                else { ChkSpoof(lv, true); _bV[lv] = 0; }
            }
            else
            {
                if (e.Operation != Operation.Remove)
                { _aP[lv] = e.Price; _aV[lv] = e.Volume;
                  if (e.Volume >= SpooQty && lv >= 2) _pLg.Add((DateTime.Now, lv, false)); }
                else { ChkSpoof(lv, false); _aV[lv] = 0; }
            }
            RunE2(); RunE3();
        }

        protected override void OnMarketData(MarketDataEventArgs e)
        { if (e.MarketDataType == MarketDataType.Last) RunE4(e.Price, e.Volume, e.IsAsk); }

        protected override void OnRender(ChartControl cc, ChartScale cs)
        {
            base.OnRender(cc, cs);
            if (!_dxOk) InitDX();
            if (ShowFp)      RenderFP(cc, cs);
            if (ShowSigBox)  RenderSigBoxes(cc, cs);
            if (ShowStk)     RenderStk(cc, cs);
        }
        protected override void OnRenderTargetChanged() { DisposeDX(); }
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

        #region E2 Trespass
        private void RunE2()
        {
            int lvs = Math.Min(DomDepth, DDEPTH); double sb=0, sa=0;
            for (int k=0; k<lvs; k++) { double w=Math.Exp(-Lambda*k); sb+=w*_bV[k]; sa+=w*_aV[k]; }
            double den = sb+sa; _imb = den>0 ? (sb-sa)/den : 0.0;
            double a = 2.0/(TressEma+1);
            _imbEma = _imbEma==0 ? _imb : _imbEma*(1-a)+_imb*a;
            _pUp = 1.0/(1.0+Math.Exp(-LBeta*_imbEma));
            _trSc = Math.Abs(_imbEma)*MX_TR;
            _trDir = _imbEma>0.05 ? +1 : _imbEma<-0.05 ? -1 : 0;
            _trSt = _imbEma.ToString("+0.00;-0.00;+0.00");
            _iLong.Enqueue(_imb);  if (_iLong.Count>SpooLong)  _iLong.Dequeue();
            _iShort.Enqueue(_imb); if (_iShort.Count>SpooShort) _iShort.Dequeue();
        }
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
            double logit=w.Zip(x,(a,b)=>a*b).Sum()+.5,qP=1.0/(1.0+Math.Exp(-logit));
            _mlSc=qP*10; _mlH.Enqueue(qP); if(_mlH.Count>20)_mlH.Dequeue();
            double bsl=_mlH.Count>0?_mlH.Average():qP,dev=bsl>0?(qP-bsl)/bsl*100:0;
            _mlSt="P="+qP.ToString("0.00")+(dev>=0?"+":"")+dev.ToString("0")+"%";
        }
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
            string lbl=ts+" · "+pts+"pts
"+_sigLbl+"
"+Time[0].ToString("HH:mm")+" "+dir;
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

        #region SharpDX Rendering
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
          foreach(var t in new[]{"IN","3 MIN","5 MIN","FOOT-
PRINT","VOL
PROF","VWAP
+-2s","GEX
LVLS","IB
LVLS","SIGS"})
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

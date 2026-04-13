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
//  DEEP6  v2.0.0 — NinjaTrader 8 Indicator — DECOMPOSED BUILD
//  Seven-Layer Institutional-Grade Market Intelligence System
//
//  Engine logic lives in AddOns/DEEP6.*.cs partial class files:
//    DEEP6.Core.cs     — Event handlers, session context
//    DEEP6.E1.cs       — E1 Footprint (absorption/exhaustion/imbalances)
//    DEEP6.E2.cs       — E2 Trespass (DOM queue imbalance)
//    DEEP6.E3.cs       — E3 CounterSpoof (Wasserstein + cancel detection)
//    DEEP6.E4.cs       — E4 Iceberg (native + synthetic detection)
//    DEEP6.E5.cs       — E5 Micro (Bayesian directional probability)
//    DEEP6.E6.cs       — E6 VP+CTX (DEX-ARRAY + VWAP/IB/GEX/POC)
//    DEEP6.E7.cs       — E7 ML Quality (Kalman + logistic classifier)
//    DEEP6.Scorer.cs   — Scoring + signal classification
//    DEEP6.Render.cs   — SharpDX footprint/signal/STKt rendering
//    DEEP6.UI.cs       — WPF overlay (header/pills/tabs/panel)
//
//  This facade file contains ONLY:
//    - Using declarations
//    - Enums
//    - Constants + Parameters
//    - OnStateChange lifecycle
//    - Plot declarations
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

    public partial class DEEP6 : Indicator
    {
        #region Constants
        private const string VER   = "v2.0.0";
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

        #region OnStateChange
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "DEEP6 v2.0.0 -- Seven-layer institutional orderflow intelligence for NQ";
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
    }
}

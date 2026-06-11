#region Using declarations
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.ComponentModel.DataAnnotations;
using System.Windows.Media;
using System.Xml.Serialization;
using NinjaTrader.Cbi;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.Gui.Tools;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.AddOns;
using NinjaTrader.NinjaScript.DrawingTools;
using SharpDX;
#endregion

namespace NinjaTrader.NinjaScript.Indicators
{
    // -----------------------------------------------------------------
    // (3) FairValueZone
    //     Volatility-adjusted rolling band; width modulated by Dreiss CI.
    // -----------------------------------------------------------------
    public class FairValueZone : Indicator
    {
        private ATR atr;
        private Series<double> zoneTop;
        private Series<double> zoneMid;
        private Series<double> zoneBot;
        private Series<double> zoneAlpha;
        private Series<double> zoneCI;
        
        private SharpDX.Direct2D1.Brush dxFill;
        private SharpDX.Direct2D1.Brush dxBorder;
        private SharpDX.Direct2D1.Brush dxMid;
        
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"Volatility-adjusted fair-value zone. Width = ATR * mult, modulated by Dreiss Choppiness Index. Opacity scales with chop regime so consolidation zones render solid and trending zones render faint.";
                Name = "FairValueZone";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                
                LookbackBars   = 20;
                AtrMultiplier  = 1.5;
                MinAlpha       = 0.10f;
                MaxAlpha       = 0.40f;
                ShowMidline    = true;
                ShowBorders    = false;
                
                ZoneFillColor   = Brushes.Yellow;
                ZoneBorderColor = Brushes.Goldenrod;
                MidlineColor    = Brushes.DarkOrange;
                
                AddPlot(new Stroke(Brushes.Goldenrod, DashStyleHelper.Dot, 1),
                        PlotStyle.Line, "Top");
                AddPlot(new Stroke(Brushes.DarkOrange, DashStyleHelper.Solid, 1),
                        PlotStyle.Line, "Mid");
                AddPlot(new Stroke(Brushes.Goldenrod, DashStyleHelper.Dot, 1),
                        PlotStyle.Line, "Bot");
            }
            else if (State == State.DataLoaded)
            {
                atr       = ATR(LookbackBars);
                zoneTop   = new Series<double>(this);
                zoneMid   = new Series<double>(this);
                zoneBot   = new Series<double>(this);
                zoneAlpha = new Series<double>(this);
                zoneCI    = new Series<double>(this);
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }
        
        protected override void OnBarUpdate()
        {
            if (CurrentBar < LookbackBars + 2)
                return;
            
            double[] tr  = new double[LookbackBars];
            double[] cls = new double[LookbackBars];
            double hi = double.MinValue, lo = double.MaxValue;
            for (int i = 0; i < LookbackBars; i++)
            {
                tr[i]  = TR(i);
                cls[i] = Close[i];
                if (High[i] > hi) hi = High[i];
                if (Low[i]  < lo) lo = Low[i];
            }
            double ci = FractalCycleMath.DreissChoppiness(tr, hi, lo, LookbackBars);
            zoneCI[0] = double.IsNaN(ci) ? 50.0 : ci;
            
            double ciClamped   = Math.Max(0.0, Math.Min(100.0, zoneCI[0]));
            double widthFactor = 0.7 + 0.7 * (ciClamped / 100.0);
            
            double width = atr[0] * AtrMultiplier * widthFactor;
            double midPx = FractalCycleMath.Median(cls);
            
            zoneMid[0]   = midPx;
            zoneTop[0]   = midPx + width / 2.0;
            zoneBot[0]   = midPx - width / 2.0;
            zoneAlpha[0] = MinAlpha + (MaxAlpha - MinAlpha) * (ciClamped / 100.0);
            
            Top[0] = zoneTop[0];
            Mid[0] = zoneMid[0];
            Bot[0] = zoneBot[0];
        }
        
        private double TR(int barsAgo)
        {
            if (barsAgo >= CurrentBar) return High[barsAgo] - Low[barsAgo];
            double prevClose = Close[barsAgo + 1];
            return Math.Max(High[barsAgo] - Low[barsAgo],
                   Math.Max(Math.Abs(High[barsAgo] - prevClose),
                            Math.Abs(Low[barsAgo]  - prevClose)));
        }
        
        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;
            try
            {
                dxFill   = ZoneFillColor.ToDxBrush(RenderTarget);
                dxBorder = ZoneBorderColor.ToDxBrush(RenderTarget);
                dxMid    = MidlineColor.ToDxBrush(RenderTarget);
            }
            catch (Exception ex)
            {
                Print("FairValueZone OnRenderTargetChanged: " + ex.Message);
            }
        }
        
        private void DisposeDx()
        {
            if (dxFill   != null) { dxFill.Dispose();   dxFill   = null; }
            if (dxBorder != null) { dxBorder.Dispose(); dxBorder = null; }
            if (dxMid    != null) { dxMid.Dispose();    dxMid    = null; }
        }
        
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (CurrentBar < LookbackBars + 2 || dxFill == null || RenderTarget == null || ChartBars == null)
            {
                base.OnRender(chartControl, chartScale);
                return;
            }
            
            int firstBar = ChartBars.FromIndex;
            int lastBar  = ChartBars.ToIndex;
            if (firstBar < LookbackBars + 1) firstBar = LookbackBars + 1;
            if (lastBar  > CurrentBar)       lastBar  = CurrentBar;
            
            for (int b = firstBar; b <= lastBar; b++)
            {
                double t   = zoneTop.GetValueAt(b);
                double bot = zoneBot.GetValueAt(b);
                double a   = zoneAlpha.GetValueAt(b);
                if (double.IsNaN(t) || double.IsNaN(bot)) continue;
                if (t <= bot) continue;
                
                float xL = chartControl.GetXByBarIndex(ChartBars, b);
                float xR;
                if (b < lastBar)
                    xR = chartControl.GetXByBarIndex(ChartBars, b + 1);
                else
                    xR = xL + (float)chartControl.BarWidth + 1f;
                
                float yT = chartScale.GetYByValue(t);
                float yB = chartScale.GetYByValue(bot);
                
                dxFill.Opacity = (float)a;
                RenderTarget.FillRectangle(
                    new SharpDX.RectangleF(xL, Math.Min(yT, yB), Math.Max(1f, xR - xL), Math.Abs(yB - yT)),
                    dxFill);
                
                if (ShowBorders)
                {
                    RenderTarget.DrawLine(new Vector2(xL, yT), new Vector2(xR, yT), dxBorder, 1f);
                    RenderTarget.DrawLine(new Vector2(xL, yB), new Vector2(xR, yB), dxBorder, 1f);
                }
                
                if (ShowMidline)
                {
                    double mid = zoneMid.GetValueAt(b);
                    if (!double.IsNaN(mid))
                    {
                        float yM = chartScale.GetYByValue(mid);
                        RenderTarget.DrawLine(new Vector2(xL, yM), new Vector2(xR, yM), dxMid, 1f);
                    }
                }
            }
            dxFill.Opacity = 1.0f;
            base.OnRender(chartControl, chartScale);
        }
        
        // ----- Plot accessors (NT8 standard pattern) -----
        [Browsable(false)][XmlIgnore] public Series<double> Top { get { return Values[0]; } }
        [Browsable(false)][XmlIgnore] public Series<double> Mid { get { return Values[1]; } }
        [Browsable(false)][XmlIgnore] public Series<double> Bot { get { return Values[2]; } }
        
        // ----- Public read-only API -----
        public double CurrentChoppiness { get { return zoneCI != null && CurrentBar >= 0 ? zoneCI[0] : double.NaN; } }
        public FractalCycleMath.ChopRegime CurrentRegime
        {
            get { return FractalCycleMath.ClassifyChoppiness(CurrentChoppiness); }
        }
        
        #region Properties
        [NinjaScriptProperty]
        [Range(2, 500)]
        [Display(Name="Lookback Bars", Description="Window for ATR, median center, and Dreiss Choppiness.", Order=1, GroupName="1. Zone")]
        public int LookbackBars { get; set; }
        
        [NinjaScriptProperty]
        [Range(0.1, 10.0)]
        [Display(Name="ATR Multiplier", Description="Base width = ATR * this; choppiness applies an additional 0.7â€“1.4 factor.", Order=2, GroupName="1. Zone")]
        public double AtrMultiplier { get; set; }
        
        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name="Min Alpha", Description="Opacity in pure-trend regime (CI=0).", Order=3, GroupName="1. Zone")]
        public float MinAlpha { get; set; }
        
        [NinjaScriptProperty]
        [Range(0.0, 1.0)]
        [Display(Name="Max Alpha", Description="Opacity in pure-chop regime (CI=100).", Order=4, GroupName="1. Zone")]
        public float MaxAlpha { get; set; }
        
        [NinjaScriptProperty]
        [Display(Name="Show Midline", Order=1, GroupName="2. Visual")]
        public bool ShowMidline { get; set; }
        
        [NinjaScriptProperty]
        [Display(Name="Show Borders", Order=2, GroupName="2. Visual")]
        public bool ShowBorders { get; set; }
        
        [XmlIgnore][Display(Name="Zone Fill Color",   Order=1, GroupName="3. Colors")]
        public Brush ZoneFillColor   { get; set; }
        [Browsable(false)] public string ZoneFillColorSerialize   { get { return Serialize.BrushToString(ZoneFillColor);   } set { ZoneFillColor   = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Zone Border Color", Order=2, GroupName="3. Colors")]
        public Brush ZoneBorderColor { get; set; }
        [Browsable(false)] public string ZoneBorderColorSerialize { get { return Serialize.BrushToString(ZoneBorderColor); } set { ZoneBorderColor = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Midline Color",     Order=3, GroupName="3. Colors")]
        public Brush MidlineColor    { get; set; }
        [Browsable(false)] public string MidlineColorSerialize    { get { return Serialize.BrushToString(MidlineColor);    } set { MidlineColor    = Serialize.StringToBrush(value); } }
        #endregion
    }
}

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
    // (1) WaveCycleEngine
    //     Williams-fractal pivot detection, cycle bar counting,
    //     peakâ†’peak and troughâ†’trough aggregation rows.
    // -----------------------------------------------------------------
    public class WaveCycleEngine : Indicator
    {
        public class Pivot
        {
            public int      BarIdx;
            public DateTime Time;
            public double   Price;
            public bool     IsHigh;
            public bool     IsClosed;
            public int      CycleBars;
            public int      Ordinal;
        }
        
        private List<Pivot> highs;
        private List<Pivot> lows;
        private double avgPeakCycle;
        private double avgTroughCycle;
        
        private SharpDX.Direct2D1.Brush dxPeakAgg;
        private SharpDX.Direct2D1.Brush dxTroughAgg;
        private SharpDX.DirectWrite.TextFormat aggTextFmt;
        private SharpDX.DirectWrite.TextFormat avgTextFmt;
        
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"Pivot/cycle engine on Williams Fractals: detects N-bar swing highs/lows, tracks open/closed state, counts bars between same-type pivots, renders peak-peak and trough-trough aggregation rows.";
                Name = "WaveCycleEngine";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = false;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                
                PivotStrength       = 3;
                AvgCycleLookback    = 10;
                ShowPivotMarkers    = true;
                ShowAggregationRows = true;
                ShowOpenClosedTags  = true;
                LabelOffsetTicks    = 6;
                
                PeakAggColor     = Brushes.OrangeRed;
                TroughAggColor   = Brushes.LimeGreen;
                PivotMarkerColor = Brushes.Yellow;
                HighLabelColor   = Brushes.OrangeRed;
                LowLabelColor    = Brushes.LimeGreen;
            }
            else if (State == State.Configure)
            {
                highs = new List<Pivot>();
                lows  = new List<Pivot>();
            }
            else if (State == State.DataLoaded)
            {
                highs.Clear();
                lows.Clear();
            }
            else if (State == State.Terminated)
            {
                DisposeDx();
            }
        }
        
        protected override void OnBarUpdate()
        {
            if (CurrentBar < PivotStrength * 2 + 2) return;
            
            int win = PivotStrength * 2 + 1;
            double[] hi = new double[win];
            double[] lo = new double[win];
            for (int i = 0; i < win; i++)
            {
                int barsAgo = win - 1 - i;
                hi[i] = High[barsAgo];
                lo[i] = Low[barsAgo];
            }
            int probe = PivotStrength;
            
            bool isHigh = FractalCycleMath.IsUpFractalChrono(hi, probe, PivotStrength);
            bool isLow  = FractalCycleMath.IsDownFractalChrono(lo, probe, PivotStrength);
            
            if (isHigh) RecordPivot(true,  PivotStrength, hi[probe]);
            if (isLow)  RecordPivot(false, PivotStrength, lo[probe]);
            
            UpdatePivotStates();
        }
        
        private void RecordPivot(bool isHigh, int barsAgoOffset, double price)
        {
            int barIdx = CurrentBar - barsAgoOffset;
            var list = isHigh ? highs : lows;
            
            if (list.Count > 0 && list[list.Count - 1].BarIdx == barIdx) return;
            
            int cycleBars = list.Count > 0 ? barIdx - list[list.Count - 1].BarIdx : 0;
            var p = new Pivot
            {
                BarIdx    = barIdx,
                Time      = Time[barsAgoOffset],
                Price     = price,
                IsHigh    = isHigh,
                IsClosed  = false,
                CycleBars = cycleBars,
                Ordinal   = list.Count + 1
            };
            list.Add(p);
            
            if (isHigh) RecomputeAvgCycle(highs, ref avgPeakCycle);
            else        RecomputeAvgCycle(lows,  ref avgTroughCycle);
            
            DrawPivotLabel(p);
            
            if (ShowPivotMarkers)
            {
                string tag = (isHigh ? "VBH_" : "VBL_") + barIdx;
                Draw.VerticalLine(this, tag, barsAgoOffset, PivotMarkerColor,
                                  DashStyleHelper.Solid, 1);
            }
        }
        
        private void DrawPivotLabel(Pivot p)
        {
            string tag = (p.IsHigh ? "H_" : "L_") + p.BarIdx;
            string state = p.IsClosed ? "closed" : "open";
            string text;
            double yPrice;
            Brush color;
            
            if (p.IsHigh)
            {
                text = ShowOpenClosedTags
                    ? string.Format("{0}\nH\n{1}", p.CycleBars, state)
                    : string.Format("{0} H", p.CycleBars);
                yPrice = p.Price + LabelOffsetTicks * TickSize;
                color  = HighLabelColor;
            }
            else
            {
                text = ShowOpenClosedTags
                    ? string.Format("L\n{0}\n{1}", p.CycleBars, state)
                    : string.Format("L {0}", p.CycleBars);
                yPrice = p.Price - LabelOffsetTicks * TickSize;
                color  = LowLabelColor;
            }
            int barsAgo = CurrentBar - p.BarIdx;
            Draw.Text(this, tag, text, barsAgo, yPrice, color);
        }
        
        // open/closed semantics:
        //   high pivot is "closed" once a subsequent bar Closes ABOVE its price
        //   low  pivot is "closed" once a subsequent bar Closes BELOW its price
        private void UpdatePivotStates()
        {
            for (int i = 0; i < highs.Count; i++)
            {
                if (!highs[i].IsClosed && Close[0] > highs[i].Price)
                {
                    highs[i].IsClosed = true;
                    DrawPivotLabel(highs[i]);
                }
            }
            for (int i = 0; i < lows.Count; i++)
            {
                if (!lows[i].IsClosed && Close[0] < lows[i].Price)
                {
                    lows[i].IsClosed = true;
                    DrawPivotLabel(lows[i]);
                }
            }
        }
        
        private void RecomputeAvgCycle(List<Pivot> list, ref double target)
        {
            if (list.Count < 2) { target = 0; return; }
            int n = Math.Min(AvgCycleLookback, list.Count - 1);
            double sum = 0;
            int counted = 0;
            for (int i = list.Count - 1; i >= list.Count - n && i > 0; i--)
            {
                sum += list[i].CycleBars;
                counted++;
            }
            target = counted > 0 ? sum / counted : 0;
        }
        
        public override void OnRenderTargetChanged()
        {
            DisposeDx();
            if (RenderTarget == null) return;
            try
            {
                dxPeakAgg   = PeakAggColor.ToDxBrush(RenderTarget);
                dxTroughAgg = TroughAggColor.ToDxBrush(RenderTarget);
                aggTextFmt = new SharpDX.DirectWrite.TextFormat(
                    NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", 11)
                {
                    TextAlignment = SharpDX.DirectWrite.TextAlignment.Center,
                    ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Near
                };
                avgTextFmt = new SharpDX.DirectWrite.TextFormat(
                    NinjaTrader.Core.Globals.DirectWriteFactory, "Arial", 11)
                {
                    TextAlignment = SharpDX.DirectWrite.TextAlignment.Trailing,
                    ParagraphAlignment = SharpDX.DirectWrite.ParagraphAlignment.Near
                };
            }
            catch (Exception ex)
            {
                Print("WaveCycleEngine OnRenderTargetChanged error: " + ex.Message);
            }
        }
        
        private void DisposeDx()
        {
            if (dxPeakAgg   != null) { dxPeakAgg.Dispose();   dxPeakAgg   = null; }
            if (dxTroughAgg != null) { dxTroughAgg.Dispose(); dxTroughAgg = null; }
            if (aggTextFmt  != null) { aggTextFmt.Dispose();  aggTextFmt  = null; }
            if (avgTextFmt  != null) { avgTextFmt.Dispose();  avgTextFmt  = null; }
        }
        
        protected override void OnRender(ChartControl chartControl, ChartScale chartScale)
        {
            if (!ShowAggregationRows) return;
            if (highs == null || lows == null) return;
            if (RenderTarget == null || ChartPanel == null || ChartBars == null) return;
            if (dxPeakAgg == null || dxTroughAgg == null) return;
            
            float chartTop = (float)ChartPanel.Y + 4;
            float chartBot = (float)(ChartPanel.Y + ChartPanel.H) - 22;
            
            DrawAggRow(chartControl, highs, chartTop, dxPeakAgg, true);
            DrawAggRow(chartControl, lows,  chartBot, dxTroughAgg, false);
            
            float canvasRight = (float)(ChartPanel.X + ChartPanel.W) - 8;
            DrawAvgLabel(canvasRight, chartTop,
                         "avg cycle " + Math.Round(avgPeakCycle), dxPeakAgg);
            DrawAvgLabel(canvasRight, chartBot - 2,
                         "avg cycle " + Math.Round(avgTroughCycle), dxTroughAgg);
        }
        
        private void DrawAggRow(ChartControl cc, List<Pivot> list,
                                 float yLine, SharpDX.Direct2D1.Brush brush, bool labelAbove)
        {
            for (int i = 1; i < list.Count; i++)
            {
                var prev = list[i - 1];
                var curr = list[i];
                
                float xL = cc.GetXByBarIndex(ChartBars, prev.BarIdx);
                float xR = cc.GetXByBarIndex(ChartBars, curr.BarIdx);
                if (float.IsNaN(xL) || float.IsNaN(xR)) continue;
                if (xR < ChartPanel.X || xL > ChartPanel.X + ChartPanel.W) continue;
                
                RenderTarget.DrawLine(new Vector2(xL, yLine), new Vector2(xR, yLine), brush, 1.5f);
                
                float xMid  = (xL + xR) / 2f;
                float textY = labelAbove ? yLine + 2 : yLine - 16;
                
                using (var layout = new SharpDX.DirectWrite.TextLayout(
                    NinjaTrader.Core.Globals.DirectWriteFactory,
                    curr.CycleBars.ToString(), aggTextFmt, 60, 16))
                {
                    RenderTarget.DrawTextLayout(new Vector2(xMid - 30, textY), layout, brush);
                }
            }
        }
        
        private void DrawAvgLabel(float xRight, float y, string text, SharpDX.Direct2D1.Brush brush)
        {
            using (var layout = new SharpDX.DirectWrite.TextLayout(
                NinjaTrader.Core.Globals.DirectWriteFactory,
                text, avgTextFmt, 180, 16))
            {
                RenderTarget.DrawTextLayout(new Vector2(xRight - 180, y), layout, brush);
            }
        }
        
        // ----- Public read-only API for downstream consumers -----
        public new IReadOnlyList<Pivot> Highs      { get { return highs; } }
        public new IReadOnlyList<Pivot> Lows       { get { return lows;  } }
        public IReadOnlyList<Pivot> PivotHighs     { get { return highs; } }
        public IReadOnlyList<Pivot> PivotLows      { get { return lows;  } }
        public double               AvgPeakCycle   { get { return avgPeakCycle;   } }
        public double               AvgTroughCycle { get { return avgTroughCycle; } }
        
        #region Properties
        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name="Pivot Strength", Description="Bars left/right required to confirm a pivot (Williams N).", Order=1, GroupName="1. Wave-Cycle")]
        public int PivotStrength { get; set; }
        
        [NinjaScriptProperty]
        [Range(2, 100)]
        [Display(Name="Avg Cycle Lookback", Description="Recent cycles to average.", Order=2, GroupName="1. Wave-Cycle")]
        public int AvgCycleLookback { get; set; }
        
        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name="Label Offset Ticks", Order=3, GroupName="1. Wave-Cycle")]
        public int LabelOffsetTicks { get; set; }
        
        [NinjaScriptProperty]
        [Display(Name="Show Pivot Markers",     Order=1, GroupName="2. Visual")]
        public bool ShowPivotMarkers    { get; set; }
        [NinjaScriptProperty]
        [Display(Name="Show Aggregation Rows",  Order=2, GroupName="2. Visual")]
        public bool ShowAggregationRows { get; set; }
        [NinjaScriptProperty]
        [Display(Name="Show Open/Closed Tags",  Order=3, GroupName="2. Visual")]
        public bool ShowOpenClosedTags  { get; set; }
        
        [XmlIgnore][Display(Name="Peak Agg Color",     Order=1, GroupName="3. Colors")]
        public Brush PeakAggColor    { get; set; }
        [Browsable(false)] public string PeakAggColorSerialize    { get { return Serialize.BrushToString(PeakAggColor);    } set { PeakAggColor    = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Trough Agg Color",   Order=2, GroupName="3. Colors")]
        public Brush TroughAggColor  { get; set; }
        [Browsable(false)] public string TroughAggColorSerialize  { get { return Serialize.BrushToString(TroughAggColor);  } set { TroughAggColor  = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Pivot Marker Color", Order=3, GroupName="3. Colors")]
        public Brush PivotMarkerColor{ get; set; }
        [Browsable(false)] public string PivotMarkerColorSerialize{ get { return Serialize.BrushToString(PivotMarkerColor);} set { PivotMarkerColor= Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="High Label Color",   Order=4, GroupName="3. Colors")]
        public Brush HighLabelColor  { get; set; }
        [Browsable(false)] public string HighLabelColorSerialize  { get { return Serialize.BrushToString(HighLabelColor);  } set { HighLabelColor  = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Low Label Color",    Order=5, GroupName="3. Colors")]
        public Brush LowLabelColor   { get; set; }
        [Browsable(false)] public string LowLabelColorSerialize   { get { return Serialize.BrushToString(LowLabelColor);   } set { LowLabelColor   = Serialize.StringToBrush(value); } }
        #endregion
    }
}

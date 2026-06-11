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
    // (2) CeilingFloorPivots
    //     Ceiling = highest unclosed swing high in lookback.
    //     Floor   = lowest  unclosed swing low  in lookback.
    //     PML     = midpoint of Ceiling and Floor.
    // -----------------------------------------------------------------
    public class CeilingFloorPivots : Indicator
    {
        private class SwingPivot
        {
            public int     BarIdx;
            public double  Price;
            public bool    IsHigh;
            public bool    IsClosed;
        }
        
        private List<SwingPivot> highs;
        private List<SwingPivot> lows;
        private SwingPivot ceiling;
        private SwingPivot floor;
        private HashSet<string> drawnTags;
        
        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = @"Ceiling / Floor / PML reference levels from Williams-fractal swing pivots. Levels project from anchor pivot to right edge; restyled when closed-through.";
                Name = "CeilingFloorPivots";
                Calculate = Calculate.OnBarClose;
                IsOverlay = true;
                DisplayInDataBox = true;
                DrawOnPricePanel = true;
                PaintPriceMarkers = true;
                ScaleJustification = NinjaTrader.Gui.Chart.ScaleJustification.Right;
                IsSuspendedWhileInactive = true;
                
                PivotStrength    = 3;
                PivotsLookback   = 8;
                ShowAllOpenPivots= true;
                ShowPML          = true;
                
                CeilingColor = Brushes.OrangeRed;
                FloorColor   = Brushes.LimeGreen;
                PMLColor     = Brushes.DarkOrange;
                ClosedColor  = Brushes.Gray;
                LineWidth    = 2;
            }
            else if (State == State.Configure)
            {
                highs = new List<SwingPivot>();
                lows  = new List<SwingPivot>();
                drawnTags = new HashSet<string>();
            }
            else if (State == State.DataLoaded)
            {
                highs.Clear();
                lows.Clear();
                drawnTags.Clear();
                ceiling = null;
                floor   = null;
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
            
            if (FractalCycleMath.IsUpFractalChrono(hi, probe, PivotStrength))
                AddSwing(true,  PivotStrength, hi[probe]);
            if (FractalCycleMath.IsDownFractalChrono(lo, probe, PivotStrength))
                AddSwing(false, PivotStrength, lo[probe]);
            
            UpdateClosedStates();
            RecomputeCeilingFloor();
            RedrawAll();
        }
        
        private void AddSwing(bool isHigh, int barsAgoOffset, double price)
        {
            int barIdx = CurrentBar - barsAgoOffset;
            var list = isHigh ? highs : lows;
            if (list.Count > 0 && list[list.Count - 1].BarIdx == barIdx) return;
            list.Add(new SwingPivot { BarIdx = barIdx, Price = price, IsHigh = isHigh, IsClosed = false });
        }
        
        private void UpdateClosedStates()
        {
            for (int i = 0; i < highs.Count; i++)
                if (!highs[i].IsClosed && Close[0] > highs[i].Price) highs[i].IsClosed = true;
            for (int i = 0; i < lows.Count; i++)
                if (!lows[i].IsClosed && Close[0] < lows[i].Price) lows[i].IsClosed = true;
        }
        
        private void RecomputeCeilingFloor()
        {
            ceiling = SelectExtreme(highs, true);
            floor   = SelectExtreme(lows,  false);
        }
        
        private SwingPivot SelectExtreme(List<SwingPivot> list, bool wantHighest)
        {
            if (list == null || list.Count == 0) return null;
            int start = Math.Max(0, list.Count - PivotsLookback);
            
            SwingPivot bestOpen = null, bestAny = null;
            for (int i = start; i < list.Count; i++)
            {
                var p = list[i];
                if (bestAny == null
                    || (wantHighest  && p.Price > bestAny.Price)
                    || (!wantHighest && p.Price < bestAny.Price))
                    bestAny = p;
                if (!p.IsClosed)
                {
                    if (bestOpen == null
                        || (wantHighest  && p.Price > bestOpen.Price)
                        || (!wantHighest && p.Price < bestOpen.Price))
                        bestOpen = p;
                }
            }
            return bestOpen ?? bestAny;
        }
        
        private void RedrawAll()
        {
            // Incremental redraw: Draw.* with a stable tag updates the existing object
            // in place; only tags that fell out of the lookback window get removed.
            // (RemoveDrawObjects() wiping every bar threw "Collection was modified"
            // while the chart enumerated the draw-objects collection.)
            HashSet<string> desired = new HashSet<string>();

            if (ShowAllOpenPivots)
            {
                int startH = Math.Max(0, highs.Count - PivotsLookback);
                for (int i = startH; i < highs.Count; i++)  DrawLevelRay(highs[i], "H_" + highs[i].BarIdx, desired);
                int startL = Math.Max(0, lows.Count - PivotsLookback);
                for (int i = startL; i < lows.Count; i++)   DrawLevelRay(lows[i],  "L_" + lows[i].BarIdx, desired);
            }
            else
            {
                if (ceiling != null) DrawLevelRay(ceiling, "Ceiling", desired);
                if (floor   != null) DrawLevelRay(floor,   "Floor", desired);
            }

            if (ShowPML && ceiling != null && floor != null)
            {
                double pml = 0.5 * (ceiling.Price + floor.Price);
                int anchorBars = CurrentBar - Math.Min(ceiling.BarIdx, floor.BarIdx);
                Draw.Ray(this, "PML", false, anchorBars, pml, 0, pml,
                         PMLColor, DashStyleHelper.Dash, LineWidth);
                Draw.Text(this, "PML_lbl", "PML " + pml.ToString("F2"),
                          0, pml + 2 * TickSize, PMLColor);
                desired.Add("PML");
                desired.Add("PML_lbl");
            }

            foreach (string tag in drawnTags)
                if (!desired.Contains(tag))
                    RemoveDrawObject(tag);
            drawnTags = desired;
        }

        private void DrawLevelRay(SwingPivot p, string tagSuffix, HashSet<string> desired)
        {
            int anchorBars = CurrentBar - p.BarIdx;
            string tag = (p.IsHigh ? "Ceil_" : "Flr_") + tagSuffix;
            Brush color = p.IsClosed ? ClosedColor : (p.IsHigh ? CeilingColor : FloorColor);
            DashStyleHelper style = p.IsClosed ? DashStyleHelper.Dot : DashStyleHelper.Solid;

            Draw.Ray(this, tag, false, anchorBars, p.Price, 0, p.Price, color, style, LineWidth);

            string lbl = (p.IsClosed ? "closed " : "open ") + p.Price.ToString("F2");
            Draw.Text(this, tag + "_lbl", lbl, 0,
                      p.Price + (p.IsHigh ? 1 : -1) * 3 * TickSize, color);
            desired.Add(tag);
            desired.Add(tag + "_lbl");
        }
        
        // ----- Public read-only API -----
        public double CeilingPrice { get { return ceiling != null ? ceiling.Price : double.NaN; } }
        public double FloorPrice   { get { return floor   != null ? floor.Price   : double.NaN; } }
        public double PMLPrice
        {
            get
            {
                if (ceiling == null || floor == null) return double.NaN;
                return 0.5 * (ceiling.Price + floor.Price);
            }
        }
        
        #region Properties
        [NinjaScriptProperty]
        [Range(1, 50)]
        [Display(Name="Pivot Strength", Description="Bars left/right to confirm a swing.", Order=1, GroupName="1. Pivots")]
        public int PivotStrength { get; set; }
        
        [NinjaScriptProperty]
        [Range(1, 100)]
        [Display(Name="Pivots Lookback", Description="Consider the last N highs / N lows when picking Ceiling and Floor.", Order=2, GroupName="1. Pivots")]
        public int PivotsLookback { get; set; }
        
        [NinjaScriptProperty]
        [Display(Name="Show All Open Pivots", Description="If true, draw a ray for every pivot in the lookback window. If false, only Ceiling + Floor.", Order=3, GroupName="1. Pivots")]
        public bool ShowAllOpenPivots { get; set; }
        
        [NinjaScriptProperty]
        [Display(Name="Show PML", Order=4, GroupName="1. Pivots")]
        public bool ShowPML { get; set; }
        
        [NinjaScriptProperty]
        [Range(1, 6)]
        [Display(Name="Line Width", Order=1, GroupName="2. Visual")]
        public int LineWidth { get; set; }
        
        [XmlIgnore][Display(Name="Ceiling Color", Order=1, GroupName="3. Colors")]
        public Brush CeilingColor { get; set; }
        [Browsable(false)] public string CeilingColorSerialize { get { return Serialize.BrushToString(CeilingColor); } set { CeilingColor = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Floor Color",   Order=2, GroupName="3. Colors")]
        public Brush FloorColor   { get; set; }
        [Browsable(false)] public string FloorColorSerialize   { get { return Serialize.BrushToString(FloorColor);   } set { FloorColor   = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="PML Color",     Order=3, GroupName="3. Colors")]
        public Brush PMLColor     { get; set; }
        [Browsable(false)] public string PMLColorSerialize     { get { return Serialize.BrushToString(PMLColor);     } set { PMLColor     = Serialize.StringToBrush(value); } }
        
        [XmlIgnore][Display(Name="Closed Color",  Order=4, GroupName="3. Colors")]
        public Brush ClosedColor  { get; set; }
        [Browsable(false)] public string ClosedColorSerialize  { get { return Serialize.BrushToString(ClosedColor);  } set { ClosedColor  = Serialize.StringToBrush(value); } }
        #endregion
    }
}

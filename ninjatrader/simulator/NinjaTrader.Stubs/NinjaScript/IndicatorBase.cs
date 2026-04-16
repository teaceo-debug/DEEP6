// IndicatorBase — base class for NinjaScript indicators.
// Provides AddPlot, Values[], IsOverlay, indicator-specific properties.

using System;
using System.Collections.Generic;
using NinjaTrader.Data;

namespace NinjaTrader.NinjaScript
{
    public class Plot
    {
        public string Name { get; set; }
        public System.Windows.Media.Brush Brush { get; set; }
        public int Width { get; set; } = 1;
        public PlotStyle PlotStyle { get; set; } = PlotStyle.Line;
    }

    public enum PlotStyle { Line, Bar, Dot, Hash, Square, TriangleDown, TriangleUp, Cross, HLine, Block }

    public abstract class IndicatorBase : NinjaScriptBase
    {
        private readonly List<Plot> _plots = new();
        private readonly List<DataSeries<double>> _values = new();

        // ── Indicator properties ──
        public string Name { get; set; } = "";
        public string Description { get; set; } = "";
        public void ForceRefresh() { } // NT8: request chart redraw
        public bool IsOverlay { get; set; } = true;
        public bool IsSuspendedWhileInactive { get; set; }
        public bool DisplayInDataBox { get; set; } = true;
        public bool DrawOnPricePanel { get; set; } = true;
        public bool DrawHorizontalGridLines { get; set; } = true;
        public bool DrawVerticalGridLines { get; set; } = true;
        public bool PaintPriceMarkers { get; set; } = true;
        public Calculate Calculate { get; set; } = Calculate.OnBarClose;
        public ScaleJustification ScaleJustification { get; set; } = ScaleJustification.Right;
        public int BarsRequiredToPlot { get; set; } = 20;
        public MaximumBarsLookBack MaximumBarsLookBack { get; set; } = MaximumBarsLookBack.TwoHundredFiftySix;

        // ── Plot management ──
        public void AddPlot(System.Windows.Media.Brush brush, string name)
        {
            _plots.Add(new Plot { Name = name, Brush = brush });
            _values.Add(new DataSeries<double>());
        }

        public void AddPlot(PlotStyle style, System.Windows.Media.Brush brush, string name, int width = 1)
        {
            _plots.Add(new Plot { Name = name, Brush = brush, PlotStyle = style, Width = width });
            _values.Add(new DataSeries<double>());
        }

        /// <summary>Indexed access to plot values — Values[plotIndex][barsAgo].</summary>
        public DataSeries<double>[] Values => _values.ToArray();

        public DataSeries<double> Value
        {
            get
            {
                if (_values.Count == 0) { _values.Add(new DataSeries<double>()); }
                return _values[0];
            }
        }

        /// <summary>Cache indicator for reuse (NT8 pattern).</summary>
        protected T CacheIndicator<T>(T indicator, ISeries<double> input, ref T[] cache) where T : IndicatorBase
        {
            if (cache == null)
                cache = new T[] { indicator };
            else
            {
                var newCache = new T[cache.Length + 1];
                Array.Copy(cache, newCache, cache.Length);
                newCache[cache.Length] = indicator;
                cache = newCache;
            }
            return indicator;
        }
    }
}

// Partial class stubs for the NT8 generated-code regions.
namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class Indicator : NinjaTrader.Gui.NinjaScript.IndicatorRenderBase { }
}

namespace NinjaTrader.NinjaScript.MarketAnalyzerColumns
{
    public partial class MarketAnalyzerColumn : NinjaTrader.Gui.NinjaScript.MarketAnalyzerColumnBase { }
}

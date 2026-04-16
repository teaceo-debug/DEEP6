// NinjaTrader.Gui stubs — Chart, NinjaScript render bases, Serialize helper.

namespace NinjaTrader.Gui
{
    /// <summary>
    /// NT8 Serialize helper — converts WPF Brushes to/from string for XML persistence.
    /// In the simulator, these are no-ops that round-trip via color string.
    /// </summary>
    public static class Serialize
    {
        public static string BrushToString(System.Windows.Media.Brush brush)
        {
            if (brush is System.Windows.Media.SolidColorBrush scb)
            {
                var c = scb.Color;
                return $"#{c.A:X2}{c.R:X2}{c.G:X2}{c.B:X2}";
            }
            return "#FF000000";
        }

        public static System.Windows.Media.Brush StringToBrush(string value)
        {
            if (string.IsNullOrEmpty(value) || value.Length < 7)
                return new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0, 0, 0));
            try
            {
                byte a = 255, r, g, b;
                if (value.Length == 9) // #AARRGGBB
                {
                    a = System.Convert.ToByte(value.Substring(1, 2), 16);
                    r = System.Convert.ToByte(value.Substring(3, 2), 16);
                    g = System.Convert.ToByte(value.Substring(5, 2), 16);
                    b = System.Convert.ToByte(value.Substring(7, 2), 16);
                }
                else // #RRGGBB
                {
                    r = System.Convert.ToByte(value.Substring(1, 2), 16);
                    g = System.Convert.ToByte(value.Substring(3, 2), 16);
                    b = System.Convert.ToByte(value.Substring(5, 2), 16);
                }
                return new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromArgb(a, r, g, b));
            }
            catch
            {
                return new System.Windows.Media.SolidColorBrush(System.Windows.Media.Color.FromRgb(0, 0, 0));
            }
        }
    }
}

namespace NinjaTrader.Gui.Chart
{
    public class ChartControl
    {
        public int BarsBack { get; set; } = 256;
        public NinjaTrader.Cbi.Instrument Instrument { get; set; } = new NinjaTrader.Cbi.Instrument();
        public event System.Windows.Input.MouseButtonEventHandler MouseDown;
        public ChartBars[] ChartBars => new ChartBars[0];
        public NinjaTrader.Gui.Chart.ChartPanel[] ChartPanels => new ChartPanel[0];

        // NT8 chart coordinate methods
        public int GetBarPaintWidth(ChartBars chartBars) => 10;
        public int GetXByBarIndex(ChartBars chartBars, int barIndex) => barIndex * 12;
        public int GetSlotIndexByTime(System.DateTime time) => 0;

        // Fire mousedown for test purposes
        internal void FireMouseDown(object sender, System.Windows.Input.MouseButtonEventArgs e)
        {
            MouseDown?.Invoke(sender, e);
        }
    }

    public class ChartBars
    {
        public int FromIndex { get; set; }
        public int ToIndex { get; set; }
        public int Count { get; set; }
        public NinjaTrader.Data.Bars Bars { get; set; }
    }

    public class ChartScale
    {
        public float GetYByValue(double price) => (float)(20000.0 - price);
        public double GetValueByY(float y) => 20000.0 - y;
        public float MaxMinusMin => 100f;
        public int Height { get; set; } = 800;
        public int Width { get; set; } = 1200;
        public double MinValue { get; set; } = 18900.0;
        public double MaxValue { get; set; } = 19100.0;
        public float GetPixelsForDistance(double distance) => (float)(distance * 4.0);
    }

    public class ChartPanel
    {
        public int X { get; set; }
        public int Y { get; set; }
        public int W { get; set; } = 1200;
        public int H { get; set; } = 800;
    }

    /// <summary>ChartAnchor — represents a point on the chart (bar + price).</summary>
    public class ChartAnchor
    {
        public int BarsAgo { get; set; }
        public double Price { get; set; }
        public System.DateTime Time { get; set; }
        public System.Windows.Point GetPoint(ChartControl cc, ChartPanel cp, ChartScale cs)
        {
            return new System.Windows.Point(0, cs.GetYByValue(Price));
        }
    }
}

namespace NinjaTrader.Gui.NinjaScript
{
    /// <summary>Base class for indicator rendering — what NT8's Indicator actually inherits from.</summary>
    public class IndicatorRenderBase : NinjaTrader.NinjaScript.IndicatorBase
    {
        public bool IsInHitTest { get; set; }
        public NinjaTrader.Gui.Chart.ChartBars ChartBars { get; set; }

        // NT8 OnRender signature — indicators override this
        protected virtual void OnRender(NinjaTrader.Gui.Chart.ChartControl chartControl, NinjaTrader.Gui.Chart.ChartScale chartScale) { }

        // NT8 OnChartPanelMouseDown — optional override for indicators
        protected virtual void OnChartPanelMouseDown(NinjaTrader.Gui.Chart.ChartControl chartControl,
            NinjaTrader.Gui.Chart.ChartPanel chartPanel, NinjaTrader.Gui.Chart.ChartScale chartScale,
            NinjaTrader.Gui.Chart.ChartAnchor dataPoint) { }
    }

    /// <summary>Base class for strategy rendering — what NT8's Strategy actually inherits from.</summary>
    public class StrategyRenderBase : NinjaTrader.NinjaScript.StrategyBase { }

    /// <summary>Stub for MarketAnalyzerColumnBase.</summary>
    public class MarketAnalyzerColumnBase
    {
        protected NinjaTrader.NinjaScript.Indicators.Indicator indicator = new();
        public NinjaTrader.Data.ISeries<double> Input { get; set; }
    }
}

namespace NinjaTrader.Gui.Tools
{
    // Placeholder — some indicators reference NinjaTrader.Gui.Tools types.
}

// Additional System.Drawing stubs for RectangleF
namespace System.Drawing
{
    public struct RectangleF
    {
        public float X, Y, Width, Height;
        public float Left => X;
        public float Top => Y;
        public float Right => X + Width;
        public float Bottom => Y + Height;
        public RectangleF(float x, float y, float w, float h) { X = x; Y = y; Width = w; Height = h; }
        public bool Contains(float px, float py) => px >= X && px <= X + Width && py >= Y && py <= Y + Height;
    }

    public struct PointF
    {
        public float X, Y;
        public PointF(float x, float y) { X = x; Y = y; }
    }
}

// WPF input stubs for ChartControl.MouseDown
namespace System.Windows.Input
{
    public delegate void MouseButtonEventHandler(object sender, MouseButtonEventArgs e);

    public class MouseButtonEventArgs : System.EventArgs
    {
        public double X { get; set; }
        public double Y { get; set; }
        public bool Handled { get; set; }
        public MouseButton ChangedButton { get; set; }
        public System.Windows.Point GetPosition(object relativeTo) => new System.Windows.Point(X, Y);
    }

    public enum MouseButton { Left, Middle, Right, XButton1, XButton2 }
}

namespace System.Windows
{
    public struct Point
    {
        public double X, Y;
        public Point(double x, double y) { X = x; Y = y; }
    }
}

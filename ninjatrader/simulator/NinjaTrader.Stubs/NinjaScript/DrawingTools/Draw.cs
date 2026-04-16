// NinjaTrader.NinjaScript.DrawingTools.Draw stubs — all Draw.* calls used by DEEP6.
// These are no-ops that log the draw call to the script's PrintLog.

namespace NinjaTrader.NinjaScript.DrawingTools
{
    public static class Draw
    {
        public static object TriangleUp(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null; // No-op in simulator
        }

        public static object TriangleDown(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object ArrowUp(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object ArrowDown(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Diamond(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Dot(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Text(NinjaScriptBase owner, string tag, string text, int barsAgo, double y, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Text(NinjaScriptBase owner, string tag, bool isAutoScale, int barsAgo, double y, int yPixelOffset,
            System.Windows.Media.Brush textBrush, NinjaTrader.Gui.Tools.SimpleFont font, System.Windows.TextAlignment alignment,
            System.Windows.Media.Brush outlineBrush, System.Windows.Media.Brush areaBrush, int areaOpacity)
        {
            return null;
        }

        public static object HorizontalLine(NinjaScriptBase owner, string tag, double price, System.Windows.Media.Brush brush, DashStyleHelper dashStyle, int width)
        {
            return null;
        }

        public static object HorizontalLine(NinjaScriptBase owner, string tag, double price, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Line(NinjaScriptBase owner, string tag, int startBarsAgo, double startY, int endBarsAgo, double endY, System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Rectangle(NinjaScriptBase owner, string tag, int startBarsAgo, double startY, int endBarsAgo, double endY,
            System.Windows.Media.Brush brush)
        {
            return null;
        }

        public static object Region(NinjaScriptBase owner, string tag, int startBarsAgo, int endBarsAgo, NinjaTrader.Data.ISeries<double> series1,
            NinjaTrader.Data.ISeries<double> series2, System.Windows.Media.Brush outlineBrush, System.Windows.Media.Brush areaBrush, int opacity)
        {
            return null;
        }

        public static void RemoveDrawObject(NinjaScriptBase owner, string tag) { }
    }

    public enum DashStyleHelper { Solid, Dash, DashDot, DashDotDot, Dot }
}

namespace NinjaTrader.Gui.Tools
{
    public class SimpleFont
    {
        public string Family { get; set; } = "Arial";
        public float Size { get; set; } = 12;
        public bool Bold { get; set; }
        public bool Italic { get; set; }

        public SimpleFont() { }
        public SimpleFont(string family, float size) { Family = family; Size = size; }

        public SharpDX.DirectWrite.TextFormat ToDirectWriteTextFormat() => new SharpDX.DirectWrite.TextFormat();
    }
}

namespace System.Windows
{
    public enum TextAlignment { Left, Right, Center, Justify }
}

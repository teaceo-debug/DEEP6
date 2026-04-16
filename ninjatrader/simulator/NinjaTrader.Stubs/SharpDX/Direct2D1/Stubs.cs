// SharpDX.Direct2D1 stubs — RenderTarget, Brush, SolidColorBrush, StrokeStyle, etc.
namespace SharpDX.Direct2D1
{
    public class Brush : DisposeBase { }

    public class SolidColorBrush : Brush
    {
        public RawColor4 Color { get; set; }
        public SolidColorBrush() { }
        public SolidColorBrush(RenderTarget rt, RawColor4 color) { Color = color; }
    }

    public class RenderTarget : DisposeBase
    {
        public void DrawLine(RawVector2 p0, RawVector2 p1, Brush brush, float strokeWidth = 1f, StrokeStyle style = null) { }
        public void DrawRectangle(RawRectangleF rect, Brush brush, float strokeWidth = 1f, StrokeStyle style = null) { }
        public void FillRectangle(RawRectangleF rect, Brush brush) { }
        public void DrawText(string text, SharpDX.DirectWrite.TextFormat fmt, RawRectangleF rect, Brush brush) { }
        public void DrawEllipse(Ellipse ellipse, Brush brush, float strokeWidth = 1f) { }
        public void FillEllipse(Ellipse ellipse, Brush brush) { }
        public void DrawTextLayout(RawVector2 origin, SharpDX.DirectWrite.TextLayout layout, Brush brush) { }
        public AntialiasMode AntialiasMode { get; set; }
    }

    public struct Ellipse
    {
        public RawVector2 Point;
        public float RadiusX, RadiusY;
        public Ellipse(RawVector2 p, float rx, float ry) { Point = p; RadiusX = rx; RadiusY = ry; }
    }

    public class StrokeStyle : DisposeBase
    {
        public StrokeStyle() { }
        public StrokeStyle(Factory factory, StrokeStyleProperties properties) { }
    }

    public class StrokeStyleProperties
    {
        public DashStyle DashStyle { get; set; }
    }

    public enum DashStyle { Solid, Dash, Dot, DashDot, DashDotDot, Custom }
    public enum AntialiasMode { PerPrimitive, Aliased }

    public class Factory : DisposeBase
    {
        public StrokeStyle CreateStrokeStyle(StrokeStyleProperties props) => new StrokeStyle();
    }
}

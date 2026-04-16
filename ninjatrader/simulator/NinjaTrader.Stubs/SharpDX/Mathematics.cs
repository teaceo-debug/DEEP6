// SharpDX mathematics stubs — enough for DEEP6Footprint.cs OnRender to compile.
// Includes implicit conversions that the real SharpDX provides.
namespace SharpDX
{
    public struct RawRectangleF
    {
        public float Left, Top, Right, Bottom;
        public RawRectangleF(float l, float t, float r, float b) { Left = l; Top = t; Right = r; Bottom = b; }

        // Implicit conversion from System.Drawing.RectangleF
        public static implicit operator RawRectangleF(System.Drawing.RectangleF r)
            => new RawRectangleF(r.X, r.Y, r.X + r.Width, r.Y + r.Height);
    }

    public struct RawVector2
    {
        public float X, Y;
        public RawVector2(float x, float y) { X = x; Y = y; }

        // Implicit conversion from Vector2
        public static implicit operator RawVector2(Vector2 v) => new RawVector2(v.X, v.Y);
    }

    public struct RawColor4
    {
        public float Red, Green, Blue, Alpha;
        public RawColor4(float r, float g, float b, float a) { Red = r; Green = g; Blue = b; Alpha = a; }
    }

    public struct Vector2
    {
        public float X, Y;
        public Vector2(float x, float y) { X = x; Y = y; }
    }

    public struct Size2F
    {
        public float Width, Height;
        public Size2F(float w, float h) { Width = w; Height = h; }
    }

    public class DisposeBase : System.IDisposable
    {
        public bool IsDisposed { get; protected set; }
        public void Dispose() { IsDisposed = true; }
    }
}

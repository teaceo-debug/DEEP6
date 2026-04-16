// Minimal WPF stubs — System.Windows.Media types used by NinjaScript indicators.
// On macOS these don't exist; provide BCL-only implementations.

namespace System.Windows.Media
{
    public struct Color
    {
        public byte A, R, G, B;
        public static Color FromRgb(byte r, byte g, byte b) => new Color { A = 255, R = r, G = g, B = b };
        public static Color FromArgb(byte a, byte r, byte g, byte b) => new Color { A = a, R = r, G = g, B = b };
    }

    public class Brush
    {
        public bool CanFreeze => true;
        public bool IsFrozen { get; private set; }
        public void Freeze() { IsFrozen = true; }
        public virtual Brush Clone() => (Brush)MemberwiseClone();

        // Extension-method target for NT8's ToDxBrush
        public SharpDX.Direct2D1.SolidColorBrush ToDxBrush(SharpDX.Direct2D1.RenderTarget rt)
        {
            return new SharpDX.Direct2D1.SolidColorBrush();
        }
    }

    public class SolidColorBrush : Brush
    {
        public Color Color { get; set; }
        public SolidColorBrush() { }
        public SolidColorBrush(Color c) { Color = c; }
        public override Brush Clone() => new SolidColorBrush(Color);
    }

    public static class Brushes
    {
        public static SolidColorBrush Transparent => new SolidColorBrush(Color.FromArgb(0, 0, 0, 0));
        public static SolidColorBrush White => new SolidColorBrush(Color.FromRgb(255, 255, 255));
        public static SolidColorBrush Black => new SolidColorBrush(Color.FromRgb(0, 0, 0));
        public static SolidColorBrush Red => new SolidColorBrush(Color.FromRgb(255, 0, 0));
        public static SolidColorBrush Green => new SolidColorBrush(Color.FromRgb(0, 128, 0));
        public static SolidColorBrush Blue => new SolidColorBrush(Color.FromRgb(0, 0, 255));
        public static SolidColorBrush Yellow => new SolidColorBrush(Color.FromRgb(255, 255, 0));
        public static SolidColorBrush Cyan => new SolidColorBrush(Color.FromRgb(0, 255, 255));
        public static SolidColorBrush Magenta => new SolidColorBrush(Color.FromRgb(255, 0, 255));
        public static SolidColorBrush OrangeRed => new SolidColorBrush(Color.FromRgb(255, 69, 0));
        public static SolidColorBrush SlateGray => new SolidColorBrush(Color.FromRgb(112, 128, 144));
        public static SolidColorBrush DodgerBlue => new SolidColorBrush(Color.FromRgb(30, 144, 255));
        public static SolidColorBrush LimeGreen => new SolidColorBrush(Color.FromRgb(50, 205, 50));
        public static SolidColorBrush Gray => new SolidColorBrush(Color.FromRgb(128, 128, 128));
        public static SolidColorBrush DarkGray => new SolidColorBrush(Color.FromRgb(169, 169, 169));
    }
}

// Minimal Xml serialization stubs
namespace System.Xml.Serialization
{
    [AttributeUsage(AttributeTargets.Property | AttributeTargets.Field)]
    public class XmlIgnoreAttribute : Attribute { }
}

// ComponentModel stubs for [Browsable(false)]
namespace System.ComponentModel
{
    [AttributeUsage(AttributeTargets.All)]
    public class BrowsableAttribute : Attribute
    {
        public bool Browsable { get; }
        public BrowsableAttribute(bool browsable) { Browsable = browsable; }
    }

    [AttributeUsage(AttributeTargets.All)]
    public class DisplayNameAttribute : Attribute
    {
        public string DisplayName { get; }
        public DisplayNameAttribute(string name) { DisplayName = name; }
    }
}

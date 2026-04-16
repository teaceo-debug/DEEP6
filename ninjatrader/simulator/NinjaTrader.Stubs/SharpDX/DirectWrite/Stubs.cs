// SharpDX.DirectWrite stubs — TextFormat, TextLayout used by OnRender.
namespace SharpDX.DirectWrite
{
    public class Factory : DisposeBase
    {
        public TextFormat CreateTextFormat(string familyName, float fontSize) => new TextFormat();
        public TextFormat CreateTextFormat(string familyName, FontWeight weight, FontStyle style, float fontSize) => new TextFormat();
    }

    public class TextFormat : DisposeBase
    {
        public TextFormat() { }
        // NT8 pattern: new TextFormat(factory, "FontFamily", size)
        public TextFormat(Factory factory, string familyName, float fontSize) { }
        // Extended: new TextFormat(factory, "FontFamily", weight, style, size)
        public TextFormat(Factory factory, string familyName, FontWeight weight, FontStyle style, float fontSize) { }

        public TextAlignment TextAlignment { get; set; }
        public ParagraphAlignment ParagraphAlignment { get; set; }
        public WordWrapping WordWrapping { get; set; }
    }

    public class TextLayout : DisposeBase
    {
        public TextMetrics Metrics => new TextMetrics();
        public TextLayout(Factory factory, string text, TextFormat format, float maxWidth, float maxHeight) { }
    }

    public struct TextMetrics
    {
        public float Width, Height, Left, Top;
    }

    public enum TextAlignment { Leading, Trailing, Center, Justified }
    public enum ParagraphAlignment { Near, Far, Center }
    public enum WordWrapping { Wrap, NoWrap, Character, Word, EmergencyBreak }
    public enum FontWeight { Thin = 100, Normal = 400, Bold = 700 }
    public enum FontStyle { Normal, Oblique, Italic }
}

// NinjaTrader.Core stubs — FloatingPoint, Globals, Serialize.

namespace NinjaTrader.Core.FloatingPoint
{
    public static class FloatingPointExtensions
    {
        public static int ApproxCompare(this double a, double b)
        {
            const double epsilon = 0.000000001;
            if (a - b > epsilon) return 1;
            if (b - a > epsilon) return -1;
            return 0;
        }
    }
}

namespace NinjaTrader.Core
{
    public static class Globals
    {
        public static string UserDataDir => System.IO.Path.Combine(
            System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile),
            "Documents", "NinjaTrader 8");

        /// <summary>NT8's global Direct2D1 factory — used for creating StrokeStyles, etc.</summary>
        public static SharpDX.Direct2D1.Factory D2DFactory { get; } = new SharpDX.Direct2D1.Factory();

        /// <summary>NT8's global DirectWrite factory — used for creating TextFormats.</summary>
        public static SharpDX.DirectWrite.Factory DirectWriteFactory { get; } = new SharpDX.DirectWrite.Factory();
    }
}

#region Using declarations
using System.ComponentModel;
using System.Windows.Media;
using NinjaTrader.NinjaScript;
#endregion

namespace NinjaTrader.NinjaScript.Indicators.AIQ
{
    public enum AIQ_1Method
    {
        Default = 0
    }

    public enum AIQ_BANDSMethod
    {
        Default = 0
    }

    public class AIQ_1 : Indicator
    {
        [Browsable(false)] public string Company { get; set; }
        [Browsable(false)] public int Period { get; set; }
        [Browsable(false)] public double Phase { get; set; }
        [Browsable(false)] public AIQ_1Method Method { get; set; }
        [Browsable(false)] public int Step { get; set; }
        [Browsable(false)] public bool UseBetterFormula { get; set; }
        [Browsable(false)] public double PctAbove { get; set; }
        [Browsable(false)] public double PctBelow { get; set; }
        [Browsable(false)] public double dotSize { get; set; }
        [Browsable(false)] public double dotOpacity { get; set; }
        [Browsable(false)] public int lineWidth { get; set; }
        [Browsable(false)] public double lineOpacity { get; set; }
        [Browsable(false)] public double SPctAbove { get; set; }
        [Browsable(false)] public double SPctBelow { get; set; }
        [Browsable(false)] public int squareSize { get; set; }
        [Browsable(false)] public double squareOpacity { get; set; }
        [Browsable(false)] public Brush UpColor { get; set; }
        [Browsable(false)] public Brush DwnColor { get; set; }
        [Browsable(false)] public Brush UpDotColor { get; set; }
        [Browsable(false)] public Brush DwnDotColor { get; set; }
        [Browsable(false)] public Brush UpMainColor { get; set; }
        [Browsable(false)] public Brush DwnMainColor { get; set; }
        [Browsable(false)] public Brush UpSquareColor { get; set; }
        [Browsable(false)] public Brush DwnSquareColor { get; set; }
        [Browsable(false)] public Brush shadowColor { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "AIQ_1 Stub";
                Description = "Temporary compile shim for missing AIQ package.";
                IsOverlay = true;
            }
        }

        protected override void OnBarUpdate()
        {
        }
    }

    public class AIQ_BANDS : Indicator
    {
        [Browsable(false)] public string Company { get; set; }
        [Browsable(false)] public int Period { get; set; }
        [Browsable(false)] public double Phase { get; set; }
        [Browsable(false)] public AIQ_BANDSMethod Method { get; set; }
        [Browsable(false)] public int Step { get; set; }
        [Browsable(false)] public bool UseBetterFormula { get; set; }
        [Browsable(false)] public int AtrPeriod { get; set; }
        [Browsable(false)] public double AtrMultiplier { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "AIQ_BANDS Stub";
                Description = "Temporary compile shim for missing AIQ package.";
                IsOverlay = true;
            }
        }

        protected override void OnBarUpdate()
        {
        }
    }

    public class AIQ_SuperBands : Indicator
    {
        [Browsable(false)] public string Company { get; set; }
        [Browsable(false)] public int HalfLength_1 { get; set; }
        [Browsable(false)] public double BandsDeviations_1 { get; set; }
        [Browsable(false)] public int HalfLength_2 { get; set; }
        [Browsable(false)] public double BandsDeviations_2 { get; set; }
        [Browsable(false)] public bool enableTriangles { get; set; }
        [Browsable(false)] public bool enableLines { get; set; }
        [Browsable(false)] public bool enableTriangleAlerts { get; set; }
        [Browsable(false)] public string TriangleAlertSound { get; set; }
        [Browsable(false)] public bool enableLineAlerts { get; set; }
        [Browsable(false)] public string LineAlertSound { get; set; }
        [Browsable(false)] public bool OptimizeMainDeviation { get; set; }
        [Browsable(false)] public double MaxOutOfBandPercent { get; set; }
        [Browsable(false)] public bool FullRecalcEnabled { get; set; }
        [Browsable(false)] public int FullRecalcPeriod { get; set; }
        [Browsable(false)] public double PctAbove { get; set; }
        [Browsable(false)] public double PctBelow { get; set; }

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "AIQ_SuperBands Stub";
                Description = "Temporary compile shim for missing AIQ package.";
                IsOverlay = true;
            }
        }

        protected override void OnBarUpdate()
        {
        }
    }
}

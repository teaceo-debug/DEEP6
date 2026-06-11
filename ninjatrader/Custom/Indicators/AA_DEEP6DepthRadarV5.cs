// Visible root-level alias for the DEEP6 Depth Radar V5 renderer.
// Keep this side-by-side with NinjaTrader.NinjaScript.Indicators.DEEP6.DEEP6DepthRadarV5
// so the indicator is easy to find in NinjaTrader's Indicators dialog.

using NinjaTrader.NinjaScript.Indicators.DEEP6;

namespace NinjaTrader.NinjaScript.Indicators
{
    public class AA_DEEP6DepthRadarV5 : DEEP6DepthRadarV5
    {
        protected override void OnStateChange()
        {
            base.OnStateChange();
            if (State == State.SetDefaults)
            {
                Name = "AA_DEEP6DepthRadarV5";
                Description = "Visible alias for DEEP6 Depth Radar V5 schema-v2 MBO wall renderer.";
            }
        }
    }
}

// COMPILE TEST ONLY — DELETE AFTER PLAN 01 VALIDATION
// Verifies NT8 accepts AddOns/ partial class without : Indicator and without CS0101
using System;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.Indicators
{
    public partial class DEEP6
    {
        // Sentinel method — must not conflict with any existing method name
        private void _CompileTestSentinel() { }
    }
}

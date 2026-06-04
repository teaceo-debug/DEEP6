using System.Collections.Generic;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion;
using NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Legacy;

namespace NinjaTrader.NinjaScript.AddOns.DEEP6
{
    // Test-project compatibility shim: DEEP6Strategy's legacy path expects these types from the
    // indicator assembly namespace, but the net8 test project does not compile DEEP6Footprint.cs.

    public enum AbsorptionType
    {
        Classic,
        Passive,
        Stopping,
        EffortVsResult
    }

    public sealed class AbsorptionSignal
    {
        public AbsorptionType Kind;
        public int Direction;
        public double Price;
        public string Wick;
        public double Strength;
        public bool AtVaExtreme;
        public string Detail;
    }

    public sealed class AbsorptionConfig
    {
        public double AbsorbWickMin = 30.0;
        public double AbsorbDeltaMax = 0.12;
        public double PassiveExtremePct = 0.20;
        public double PassiveVolPct = 0.60;
        public double StopVolMult = 2.0;
        public double EvrVolMult = 1.5;
        public double EvrRangeCap = 0.30;
        public double VaExtremeTicks = 2.0;
        public double VaExtremeStrengthBonus = 0.15;
    }

    public static class AbsorptionDetector
    {
        public static List<AbsorptionSignal> Detect(
            FootprintBar bar,
            double atr,
            double volEma,
            AbsorptionConfig cfg,
            double? vah,
            double? val,
            double tickSize)
        {
            var results = LegacyAbsorptionBridge.Detect(bar, atr, volEma, cfg, vah, val, tickSize);
            var legacy = new List<AbsorptionSignal>(results.Length);
            foreach (var r in results)
            {
                if (!r.SignalId.StartsWith("ABS") || r.SignalId == "ABS-07")
                    continue;

                legacy.Add(new AbsorptionSignal
                {
                    Kind = AbsorptionType.Classic,
                    Direction = r.Direction,
                    Price = r.Direction < 0 ? bar.High : r.Direction > 0 ? bar.Low : bar.Close,
                    Wick = r.Direction < 0 ? "upper" : "lower",
                    Strength = r.Strength,
                    AtVaExtreme = r.Detail != null && (r.Detail.Contains("@VAH") || r.Detail.Contains("@VAL")),
                    Detail = r.Detail,
                });
            }
            return legacy;
        }
    }

    public enum ExhaustionType
    {
        ZeroPrint,
        ExhaustionPrint,
        ThinPrint,
        FatPrint,
        FadingMomentum,
        BidAskFade
    }

    public sealed class ExhaustionSignal
    {
        public ExhaustionType Kind;
        public int Direction;
        public double Price;
        public double Strength;
        public string Detail;
    }

    public sealed class ExhaustionConfig
    {
        public double ThinPct = 0.05;
        public double FatMult = 2.0;
        public double ExhaustWickMin = 35.0;
        public double FadeThreshold = 0.60;
        public int CooldownBars = 5;
        public bool DeltaGateEnabled = true;
        public double DeltaGateMinRatio = 0.10;
    }

    public sealed class ExhaustionDetector
    {
        private readonly NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector _inner;

        public ExhaustionDetector()
        {
            _inner = new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector();
        }

        public void ResetCooldowns() => _inner.ResetCooldowns();

        public List<ExhaustionSignal> Detect(FootprintBar bar, FootprintBar priorBar, int barIndex, double atr, ExhaustionConfig cfg)
        {
            var innerCfg = new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionConfig
            {
                ThinPct = cfg.ThinPct,
                FatMult = cfg.FatMult,
                ExhaustWickMin = cfg.ExhaustWickMin,
                FadeThreshold = cfg.FadeThreshold,
                CooldownBars = cfg.CooldownBars,
                DeltaGateEnabled = cfg.DeltaGateEnabled,
                DeltaGateMinRatio = cfg.DeltaGateMinRatio,
            };

            var inner = new NinjaTrader.NinjaScript.AddOns.DEEP6.Detectors.Exhaustion.ExhaustionDetector(innerCfg);
            var results = inner.Detect(bar, priorBar, barIndex, atr, innerCfg);
            var legacy = new List<ExhaustionSignal>(results.Count);
            foreach (var r in results)
            {
                legacy.Add(new ExhaustionSignal
                {
                    Kind = MapExhaustionType(r.Kind),
                    Direction = r.Direction,
                    Price = r.Price,
                    Strength = r.Strength,
                    Detail = r.Detail,
                });
            }
            return legacy;
        }

        private static ExhaustionType MapExhaustionType(Detectors.Exhaustion.ExhaustionType kind)
        {
            return kind switch
            {
                Detectors.Exhaustion.ExhaustionType.ZeroPrint => ExhaustionType.ZeroPrint,
                Detectors.Exhaustion.ExhaustionType.ExhaustionPrint => ExhaustionType.ExhaustionPrint,
                Detectors.Exhaustion.ExhaustionType.ThinPrint => ExhaustionType.ThinPrint,
                Detectors.Exhaustion.ExhaustionType.FatPrint => ExhaustionType.FatPrint,
                Detectors.Exhaustion.ExhaustionType.FadingMomentum => ExhaustionType.FadingMomentum,
                _ => ExhaustionType.BidAskFade,
            };
        }
    }
}
